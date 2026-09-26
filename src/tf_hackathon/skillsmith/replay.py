"""Replay: re-run a candidate's original task with the proposed skill attached, and judge it.

TrueForge has no API to delete a configured skill, so every replay borrows one reserved skill
registration (the replay slot): it points the slot at the proposal branch for the replay and
back at an inert target afterwards. Replays run one at a time so they never share the slot.
"""

import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from mcp.server.mcpserver.exceptions import ToolError

from tf_hackathon.skillsmith.trueforge import (
    SKILLSMITH_SOURCE,
    TrueForge,
    agent_spec,
    final_answer,
    first_user_message,
    model_calls,
    text_of,
    turn_tokens,
)

_slot_lock = threading.Lock()

JUDGE_INSTRUCTIONS = """You grade whether an agent's answer to a task is correct.
You are given the task, a reference answer that a teammate accepted after working through the
task, and a candidate answer. The candidate is correct when it reaches the same conclusion as
the reference: the same key numbers (allowing rounding) and no claim that contradicts it.
Wording, length and extra detail don't matter. Reply with JSON only."""

JUDGE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "replay_verdict",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "correct": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["correct", "reason"],
            "additionalProperties": False,
        },
    },
}


@dataclass
class Run:
    session_id: str
    turns: int
    model_calls: int
    tokens: int
    answer: str | None
    status: str = "done"  # done | paused | error | timed out


@dataclass
class ReplayResult:
    passed: bool
    correct: bool
    judge_reason: str
    original: Run
    replay: Run

    def markdown(self, skill: str, branch: str) -> str:
        o, r = self.original, self.replay
        verdict = "**Pass**" if self.passed else "**Fail**"
        why = (
            "correct answer in fewer turns" if self.passed
            else "answer judged incorrect" if not self.correct
            else "not fewer turns than the original"
        )
        status = "" if r.status == "done" else f"\n\nReplay ended {r.status}."
        return (
            f"{verdict}: {why}. Replayed `{skill}` from `{branch}`.\n\n"
            "| | Session | Turns | Model calls | Tokens |\n|---|---|---|---|---|\n"
            f"| Original | `{o.session_id}` | {o.turns} | {o.model_calls} | {o.tokens:,} |\n"
            f"| Replay | `{r.session_id}` | {r.turns} | {r.model_calls} | {r.tokens:,} |\n\n"
            f"Judge: {self.judge_reason}{status}"
        )


def replay_spec(original: dict, slot: str) -> dict:
    """The original agent, with only the replay slot as its skill and nobody to ask."""
    config = original.get("config") or {}
    return original | {
        "skills": [{"name": slot}],
        "config": config | {
            "sandbox": (config.get("sandbox") or {}) | {"enabled": True},
            "ask_user_questions": {"enabled": False},
        },
    }


def judge_spec(model: dict) -> dict:
    return {
        "model": model,
        "instructions": JUDGE_INSTRUCTIONS,
        "response_format": JUDGE_FORMAT,
        "config": {
            "sandbox": {"enabled": False},
            "ask_user_questions": {"enabled": False},
            "dynamic_sub_agents": {"enabled": False},
            "generative_ui": {"enabled": False},
        },
    }


def parse_verdict(text: str | None) -> tuple[bool, str]:
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        verdict = json.loads(match[0]) if match else None
    except json.JSONDecodeError:
        verdict = None
    if not isinstance(verdict, dict) or not isinstance(verdict.get("correct"), bool):
        return False, f"Judge gave no usable verdict: {(text or '')[:200]!r}"
    return verdict["correct"], str(verdict.get("reason", ""))


class Replayer:
    def __init__(self, tf: TrueForge, repo_url: str, skills_dir: str, slot: str,
                 timeout_s: float = 600, poll_s: float = 3,
                 sleep: Callable[[float], None] | None = None,
                 clock: Callable[[], float] | None = None):
        self.tf, self.repo_url, self.skills_dir, self.slot = tf, repo_url, skills_dir, slot
        self.timeout_s, self.poll_s = timeout_s, poll_s
        self.sleep, self.clock = sleep or time.sleep, clock or time.monotonic

    def _point_slot(self, ref: str, path: str, description: str) -> None:
        self.tf.upsert_skill({"type": "git", "name": self.slot, "url": self.repo_url,
                              "path": path, "ref": ref, "description": description})

    def _release_slot(self) -> None:
        self._point_slot("main", self.skills_dir,
                         "Internal to skillsmith replays. Do not attach to an agent.")

    def _run_once(self, spec: dict, message: str, metadata: dict[str, str]) -> tuple[dict, dict]:
        """Run one message to the end of its turn; returns (session, finished turn)."""
        session = self.tf.create_session(spec, {"source": SKILLSMITH_SOURCE} | metadata)
        turn = self.tf.start_turn(session["id"], message)
        deadline = self.clock() + self.timeout_s
        while turn["state"]["status"] == "running":
            if self.clock() >= deadline:
                self.tf.cancel_session(session["id"])
                return session, turn | {"state": {"status": "timed out"}}
            self.sleep(self.poll_s)
            turn = self.tf.get_turn(session["id"], turn["id"])
        return session, turn

    def _summarise(self, session_id: str, turns: list[dict], status: str = "done") -> Run:
        events = self.tf.session_events(session_id)
        return Run(session_id, len(turns), model_calls(events),
                   sum(turn_tokens(t) for t in turns), final_answer(events), status)

    def replay(self, session_id: str, skill: str, branch: str) -> ReplayResult:
        original_session = self.tf.get_session(session_id)
        original_events = self.tf.session_events(session_id)
        task = first_user_message(original_events)
        if task is None:
            raise ToolError(f"Session {session_id} has no user message to replay.")
        original = self._summarise(session_id, self.tf.list_turns(session_id))
        if original.answer is None:
            raise ToolError(f"Session {session_id} has no final answer to judge against.")
        spec = agent_spec(self.tf, original_session)

        with _slot_lock:
            self._point_slot(branch, f"{self.skills_dir}/{skill}",
                             f"Replay of proposed skill {skill} (skillsmith internal).")
            try:
                session, turn = self._run_once(
                    replay_spec(spec, self.slot), task,
                    {"kind": "replay", "replay_of": session_id, "skill": skill},
                )
            finally:
                self._release_slot()

        status = turn["state"]["status"]
        if status == "done" and turn["state"].get("required_actions"):
            status = "paused"  # waiting on an approval nobody will give during a replay
            self.tf.cancel_session(session["id"])
        replay = self._summarise(session["id"], [turn], status)
        if status == "error":
            replay.answer = None
            reason = f"Replay errored: {turn['state'].get('message', '')}"
            return ReplayResult(False, False, reason, original, replay)
        if replay.answer is None:
            return ReplayResult(False, False, f"Replay ended {status} with no answer.",
                                original, replay)

        correct, reason = self.judge(spec["model"], task, original.answer, replay.answer,
                                     session_id)
        passed = correct and status == "done" and replay.turns < original.turns
        return ReplayResult(passed, correct, reason, original, replay)

    def judge(self, model: dict, task: str, reference: str, candidate: str,
              session_id: str) -> tuple[bool, str]:
        prompt = (f"## Task\n{task}\n\n## Reference answer\n{reference}\n\n"
                  f"## Candidate answer\n{candidate}")
        session, turn = self._run_once(judge_spec(model), prompt,
                                       {"kind": "replay-judge", "replay_of": session_id})
        if turn["state"]["status"] != "done":
            return False, f"Judge session {session['id']} ended {turn['state']['status']}."
        output = turn["state"].get("output") or {}
        return parse_verdict(text_of(output.get("content")))
