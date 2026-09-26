import itertools

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from tf_hackathon.skillsmith import server
from tf_hackathon.skillsmith.config import Config
from tf_hackathon.skillsmith.replay import Replayer, parse_verdict, replay_spec
from tf_hackathon.skillsmith.state import State

ACME_OPS = {
    "model": {"name": "openai/gpt-5.2"},
    "instructions": "You help the team investigate acme-app.",
    "mcp_servers": [{"name": "acme-app"}],
    "skills": [{"name": "some-published-skill"}],
    "config": {"sandbox": {"enabled": False}, "iteration_limit": 40},
}

TASK = "What's the checkout-api error rate over the last 6h?"


def user(text):
    return {"type": "turn.created", "input": [{"type": "user.message", "content": text}]}


def agent(text=None, thread="main"):
    return {"type": "model.message", "content": text, "thread_id": thread, "tool_calls": []}


# Alice's session: the naive answer, pushback, then the retry-aware answer.
ORIGINAL_EVENTS = [
    user(TASK), agent(None), agent("It's 31%."),
    user("That counts retries. Only the final attempt should count."),
    agent(None), agent(None, thread="sub_1"), agent("You're right: 4.2% of requests failed."),
]


def done(turn_id, answer, tokens, required_actions=()):
    return {"id": turn_id, "state": {
        "status": "done", "output": {"type": "model.message", "content": answer},
        "required_actions": list(required_actions), "metrics": {"total_tokens": tokens}}}


class FakeTrueForge:
    """Just enough of TrueForge's HTTP API, recording what skillsmith asked for."""

    def __init__(self, replay_answer="4.2% of requests failed (retries excluded).",
                 verdict='{"correct": true, "reason": "Same 4.2% figure."}',
                 polls_before_done=2, replay_actions=(), agent_type="reference"):
        self.skill_upserts, self.sessions, self.started, self.cancelled = [], {}, [], []
        self.replay_answer, self.verdict = replay_answer, verdict
        self.polls_before_done, self.replay_actions = polls_before_done, replay_actions
        self.ids = itertools.count(1)
        agent_ref = ({"type": "reference", "id": "agent_1", "name": "acme-ops"}
                     if agent_type == "reference" else {"type": "inline", "spec": ACME_OPS})
        self.sessions["orig"] = {"id": "orig", "agent": agent_ref, "metadata": {}}
        self.events = {"orig": ORIGINAL_EVENTS}
        self.turns = {"orig": [done("t1", "It's 31%.", 9000), done("t2", "4.2%", 12000)]}

    def get_session(self, sid):
        return self.sessions[sid]

    def get_agent(self, agent_id):
        assert agent_id == "agent_1"
        return {"id": agent_id, "name": "acme-ops", "manifest": ACME_OPS}

    def session_events(self, sid):
        return self.events.get(sid, [])

    def list_turns(self, sid):
        return self.turns[sid]

    def upsert_skill(self, manifest):
        self.skill_upserts.append(manifest)

    def create_session(self, spec, metadata):
        sid = f"s{next(self.ids)}"
        self.sessions[sid] = {"id": sid, "spec": spec, "metadata": metadata,
                              "slot_at_start": dict(self.skill_upserts[-1])
                              if self.skill_upserts else None}
        return self.sessions[sid]

    def start_turn(self, sid, message):
        self.started.append((sid, message))
        self.polls = self.polls_before_done
        return {"id": f"{sid}-t", "state": {"status": "running"}}

    def get_turn(self, sid, turn_id):
        self.polls -= 1
        if self.polls > 0:
            return {"id": turn_id, "state": {"status": "running"}}
        is_judge = self.sessions[sid]["metadata"]["kind"] == "replay-judge"
        answer = self.verdict if is_judge else self.replay_answer
        actions = () if is_judge else self.replay_actions
        self.events[sid] = [user(self.started[-1][1]), agent(None), agent(answer)]
        return done(turn_id, answer, 300 if is_judge else 5000, actions)

    def cancel_session(self, sid):
        self.cancelled.append(sid)


def replayer(tf, **kw):
    return Replayer(tf, "https://github.com/o/r", "skills", "skillsmith-replay",
                    sleep=lambda s: None, **kw)


def test_replay_passes_with_correct_answer_in_fewer_turns():
    tf = FakeTrueForge()
    result = replayer(tf).replay("orig", "acme-error-rate", "skillsmith/acme-error-rate-1")

    assert result.passed and result.correct
    assert result.judge_reason == "Same 4.2% figure."
    assert (result.original.turns, result.original.model_calls, result.original.tokens) == (
        2, 4, 21000)  # the subagent's message isn't counted
    assert result.original.answer == "You're right: 4.2% of requests failed."
    assert (result.replay.turns, result.replay.model_calls, result.replay.tokens) == (1, 2, 5000)

    replay_session, judge_session = tf.sessions["s1"], tf.sessions["s2"]
    assert tf.started[0] == ("s1", TASK)
    assert replay_session["metadata"] == {"source": "skillsmith", "kind": "replay",
                                          "replay_of": "orig", "skill": "acme-error-rate"}
    assert judge_session["metadata"]["source"] == "skillsmith"
    spec = replay_session["spec"]
    assert spec["model"] == ACME_OPS["model"]
    assert spec["mcp_servers"] == ACME_OPS["mcp_servers"]
    assert spec["skills"] == [{"name": "skillsmith-replay"}]
    assert spec["config"]["sandbox"]["enabled"] is True
    assert spec["config"]["ask_user_questions"] == {"enabled": False}
    assert spec["config"]["iteration_limit"] == 40
    assert judge_session["spec"]["response_format"]["type"] == "json_schema"
    assert "4.2% of requests failed (retries excluded)." in tf.started[1][1]


def test_replay_slot_points_at_branch_during_replay_and_is_released():
    tf = FakeTrueForge()
    replayer(tf).replay("orig", "acme-error-rate", "skillsmith/acme-error-rate-1")

    during = tf.sessions["s1"]["slot_at_start"]
    assert during == {"type": "git", "name": "skillsmith-replay", "url": "https://github.com/o/r",
                      "path": "skills/acme-error-rate", "ref": "skillsmith/acme-error-rate-1",
                      "description": during["description"]}
    after = tf.skill_upserts[-1]
    assert (after["name"], after["ref"], after["path"]) == ("skillsmith-replay", "main", "skills")
    assert "Do not attach" in after["description"]


def test_slot_is_released_even_when_the_replay_blows_up():
    tf = FakeTrueForge()
    tf.start_turn = lambda sid, message: (_ for _ in ()).throw(ToolError("TrueForge 422"))
    with pytest.raises(ToolError):
        replayer(tf).replay("orig", "acme-error-rate", "skillsmith/acme-error-rate-1")
    assert tf.skill_upserts[-1]["ref"] == "main"


def test_wrong_answer_fails():
    tf = FakeTrueForge(replay_answer="31% error rate.",
                       verdict='{"correct": false, "reason": "31% counts retries."}')
    result = replayer(tf).replay("orig", "acme-error-rate", "b")
    assert not result.passed and not result.correct
    assert "Fail**: answer judged incorrect" in result.markdown("acme-error-rate", "b")


def test_correct_but_not_fewer_turns_fails():
    tf = FakeTrueForge()
    tf.turns["orig"] = tf.turns["orig"][:1]
    result = replayer(tf).replay("orig", "acme-error-rate", "b")
    assert result.correct and not result.passed


def test_replay_paused_on_approval_is_cancelled_and_fails():
    tf = FakeTrueForge(replay_actions=[{"type": "tool.approval_required"}])
    result = replayer(tf).replay("orig", "acme-error-rate", "b")
    assert result.replay.status == "paused"
    assert "s1" in tf.cancelled
    assert not result.passed


def test_replay_that_never_finishes_times_out():
    tf = FakeTrueForge(polls_before_done=10**6)
    clock = itertools.count(0, 100)
    result = Replayer(tf, "https://github.com/o/r", "skills", "slot", timeout_s=250,
                      sleep=lambda s: None, clock=lambda: next(clock)).replay("orig", "x", "b")
    assert result.replay.status == "timed out"
    assert tf.cancelled == ["s1"]
    assert not result.passed
    assert len(tf.started) == 1  # no judge without an answer


def test_inline_original_session_is_replayed_with_its_own_spec():
    tf = FakeTrueForge(agent_type="inline")
    replayer(tf).replay("orig", "acme-error-rate", "b")
    assert tf.sessions["s1"]["spec"]["instructions"] == ACME_OPS["instructions"]


def test_replay_spec_does_not_touch_the_original():
    replay_spec(ACME_OPS, "slot")
    assert ACME_OPS["skills"] == [{"name": "some-published-skill"}]
    assert ACME_OPS["config"]["sandbox"] == {"enabled": False}


@pytest.mark.parametrize("text, expected", [
    ('{"correct": true, "reason": "ok"}', (True, "ok")),
    ('Sure!\n```json\n{"correct": false, "reason": "no"}\n```', (False, "no")),
    ("I think it's right", (False, None)),
    ('{"correct": "yes"}', (False, None)),
])
def test_parse_verdict(text, expected):
    correct, reason = parse_verdict(text)
    assert correct is expected[0]
    if expected[1]:
        assert reason == expected[1]


class FakeGitHub:
    def __init__(self, body):
        self.body = body

    def get_pr(self, number):
        return {"number": number, "body": self.body, "state": "open"}

    def update_pr_body(self, number, body):
        self.body = body


def test_replay_tool_writes_results_into_the_pr(tmp_path, monkeypatch):
    cfg = Config("http://tf", "tok", "o/r", "skills", ["acme-ops"], tmp_path / "state.json")
    state = State(cfg.state_path)
    state.record_proposal(7, {"kind": "proposal", "name": "acme-error-rate",
                              "branch": "skillsmith/acme-error-rate-1", "sessions": ["orig"]})
    gh, tf = FakeGitHub(""), FakeTrueForge()
    monkeypatch.setattr(server, "_deps", lambda: (cfg, tf, gh, state))
    gh.body = server._pr_body("proposal", "acme-error-rate", "d", "r", ["orig"], "",
                              "No secrets or personal data found.")
    monkeypatch.setattr("time.sleep", lambda s: None)

    out = server.replay_with_skill("orig", "skillsmith/acme-error-rate-1")

    assert out["passed"] and out["pr_number"] == 7
    assert "_Not replayed._" not in gh.body
    assert "| Original | `orig` | 2 | 4 | 21,000 |" in gh.body
    assert "| Replay | `s1` | 1 | 2 | 5,000 |" in gh.body
    assert "### Scrub\nNo secrets or personal data found.\n\n### Review" in gh.body
    assert State(cfg.state_path).proposal(7)["replay"] == {"session_id": "s1", "passed": True}


def test_replay_tool_rejects_unknown_branch(tmp_path, monkeypatch):
    cfg = Config("http://tf", "tok", "o/r", "skills", ["acme-ops"], tmp_path / "state.json")
    monkeypatch.setattr(server, "_deps", lambda: (cfg, None, None, State(cfg.state_path)))
    with pytest.raises(ToolError, match="not an open skillsmith proposal"):
        server.replay_with_skill("orig", "feature/x")


def test_with_verification_appends_when_the_section_is_missing():
    assert server.with_verification("Edited by hand.", "Pass") == (
        "Edited by hand.\n\n### Verification\nPass\n")


def test_replay_tool_rejects_closed_proposal(tmp_path, monkeypatch):
    cfg = Config("http://tf", "tok", "o/r", "skills", ["acme-ops"], tmp_path / "state.json")
    state = State(cfg.state_path)
    state.record_proposal(7, {"name": "x", "branch": "skillsmith/x-1"})
    state.close_proposal(7, "closed: denied")
    monkeypatch.setattr(server, "_deps", lambda: (cfg, None, None, state))
    with pytest.raises(ToolError, match="not an open skillsmith proposal"):
        server.replay_with_skill("orig", "skillsmith/x-1")
