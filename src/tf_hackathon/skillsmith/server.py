"""skillsmith MCP server: the distiller's only way to read sessions and change team skills."""

import argparse
import json
import os
import re
import time
from functools import cache

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from tf_hackathon.skillsmith.config import Config
from tf_hackathon.skillsmith.github import GitHub
from tf_hackathon.skillsmith.replay import Replayer
from tf_hackathon.skillsmith.scrub import report_markdown, scrub_files, scrub_text, summary
from tf_hackathon.skillsmith.state import State
from tf_hackathon.skillsmith.trueforge import (
    TrueForge,
    is_skillsmith_session,
    transcript,
    with_skill,
    without_skill,
)

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)

SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
BRANCH_PREFIX = "skillsmith/"

mcp = MCPServer(
    "skillsmith",
    instructions=(
        "Reads the team's TrueForge sessions and manages the team's shared skills. "
        "Skill proposals are GitHub PRs; publish_skill and deprecate_skill change every "
        "teammate's agent and need a reviewer's approval."
    ),
)


@cache
def _deps() -> tuple[Config, TrueForge, GitHub, State]:
    cfg = Config.from_env()
    return cfg, TrueForge(cfg.trueforge_url), GitHub(cfg.github_token, cfg.github_repo), State(
        cfg.state_path
    )


def _skill_path(cfg: Config, name: str, file: str = "SKILL.md") -> str:
    return f"{cfg.skills_dir}/{name}/{file}"


def _check_name(name: str) -> None:
    if not SKILL_NAME.match(name):
        raise ToolError(f"Skill name {name!r} must be lowercase letters, digits and dashes.")


def render_skill_md(name: str, description: str, instructions: str) -> str:
    # JSON strings are valid YAML scalars, so this survives colons and quotes.
    return (
        f"---\nname: {name}\ndescription: {json.dumps(description)}\n---\n\n"
        f"{instructions.strip()}\n"
    )


def parse_frontmatter(skill_md: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---", skill_md, re.S)
    fields = {}
    for line in (match[1] if match else "").splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith('"'):
            value = json.loads(value)
        fields[key.strip()] = value
    return fields


def _pr_body(kind: str, name: str, description: str, rationale: str, sessions: list[str],
             verification: str, scrub_report: str) -> str:
    cfg, tf, _, _ = _deps()
    evidence = "\n".join(f"- `{sid}`" for sid in sessions) or "- (none given)"
    return f"""## Skill {kind}: `{name}`

**When to use:** {description}

### Why
{rationale}

### Evidence
Distilled from these TrueForge sessions:
{evidence}

### Verification
{verification or "_Not replayed._"}

### Scrub
{scrub_report}

### Review
Don't merge this PR on GitHub. The distiller is paused in TrueForge ({cfg.trueforge_url}) on
`publish_skill` for this PR: **Allow** publishes it to the team, **Deny** closes it.
"""


def with_verification(pr_body: str, verification: str) -> str:
    """The PR body with its Verification section replaced."""
    body, n = re.subn(r"(### Verification\n).*?(?=\n\n### )", lambda m: m[1] + verification,
                      pr_body, count=1, flags=re.S)
    return body if n else f"{pr_body.rstrip()}\n\n### Verification\n{verification}\n"


def _propose(kind: str, name: str, description: str, instructions: str,
             files: dict[str, str] | None, rationale: str, source_session_ids: list[str],
             verification: str) -> dict:
    cfg, _, gh, state = _deps()
    changes: dict[str, str] = {"SKILL.md": render_skill_md(name, description, instructions)}
    for rel, content in (files or {}).items():
        if rel.startswith("/") or ".." in rel.split("/") or rel == "SKILL.md":
            raise ToolError(f"Bad skill file path {rel!r}")
        changes[rel] = content
    # Scrub before anything leaves skillsmith: the skills repo and its PRs are public (ADR 0003).
    changes, findings = scrub_files(changes)
    rationale, found = scrub_text(rationale, "PR description")
    findings += found
    verification, found = scrub_text(verification, "PR description")
    findings += found
    description = parse_frontmatter(changes["SKILL.md"])["description"]
    branch = f"{BRANCH_PREFIX}{name}-{int(time.time())}"
    title = f"Skill {kind}: {name}"
    gh.commit_to_new_branch(
        branch, title, {_skill_path(cfg, name, rel): c for rel, c in changes.items()}
    )
    pr = gh.open_pr(
        branch, title,
        _pr_body(kind, name, description, rationale, source_session_ids, verification,
                 report_markdown(findings)),
    )
    state.record_proposal(pr["number"], {
        "kind": kind, "name": name, "description": description, "branch": branch,
        "sessions": source_session_ids,
    })
    return {"pr_number": pr["number"], "url": pr["html_url"], "branch": branch,
            "scrub": summary(findings)}


@mcp.tool(annotations=READ)
def list_sessions(limit: int = 50) -> list[dict]:
    """List teammates' sessions that haven't been processed yet, newest first.

    Skillsmith's own sessions (distiller runs and replays) are never listed.
    """
    _, tf, _, state = _deps()
    out = []
    for s in tf.list_sessions(limit=limit * 3):
        if is_skillsmith_session(s) or state.is_processed(s["id"]):
            continue
        meta = s.get("metadata") or {}
        agent = s["agent"]
        out.append({
            "id": s["id"],
            "author": meta.get("author") or s["created_by_subject"].get("subject_display_name"),
            "title": s.get("title"),
            "agent": agent.get("name") or agent["type"],
            "created_at": s["created_at"],
            "turns": s["metrics"].get("total_turns"),
        })
        if len(out) == limit:
            break
    return out


@mcp.tool(annotations=READ)
def get_session_transcript(session_id: str, clip: int = 800) -> str:
    """The session as a readable transcript. Long tool arguments and results are clipped
    to `clip` characters."""
    _, tf, _, _ = _deps()
    return transcript(tf.session_events(session_id), clip=clip)


@mcp.tool(annotations=READ)
def list_skills() -> list[dict]:
    """The team's published skills: name and when-to-use description."""
    cfg, _, gh, _ = _deps()
    skills = []
    for entry in gh.list_dir(cfg.skills_dir):
        if entry["type"] != "dir":
            continue
        md = gh.read_file(_skill_path(cfg, entry["name"])) or ""
        skills.append({"name": entry["name"],
                       "description": parse_frontmatter(md).get("description", "")})
    return skills


@mcp.tool(annotations=READ)
def get_skill(name: str) -> dict:
    """A published skill's SKILL.md and the contents of its other files."""
    cfg, _, gh, _ = _deps()
    root = f"{cfg.skills_dir}/{name}/"
    paths = gh.list_tree(root)
    if not paths:
        raise ToolError(f"No published skill named {name!r}")
    return {p.removeprefix(root): gh.read_file(p) for p in paths}


@mcp.tool(annotations=WRITE)
def mark_processed(session_ids: list[str], note: str) -> str:
    """Record sessions as considered, so later runs skip them. `note` says what came of it,
    e.g. 'trivial', or 'proposed as PR #3'."""
    _deps()[3].mark_processed(session_ids, note)
    return f"Marked {len(session_ids)} session(s) processed."


@mcp.tool(annotations=WRITE)
def propose_skill(name: str, description: str, instructions: str, rationale: str,
                  source_session_ids: list[str], files: dict[str, str] | None = None,
                  verification: str = "") -> dict:
    """Open a PR adding a new skill under skills/<name>/. Nothing reaches teammates until
    publish_skill is approved.

    name: lowercase-with-dashes. description: when an agent should use the skill.
    instructions: the SKILL.md body (markdown). files: extra files keyed by path relative to
    the skill folder, e.g. {"scripts/error_rate.py": "..."}. rationale: why this is worth
    a skill. verification: replay results, if any.

    Everything is scrubbed of secrets and personal data first; the PR lists what was removed.
    """
    _check_name(name)
    cfg, _, gh, _ = _deps()
    if gh.read_file(_skill_path(cfg, name)) is not None:
        raise ToolError(f"Skill {name!r} already exists; use propose_skill_update.")
    return _propose("proposal", name, description, instructions, files, rationale,
                    source_session_ids, verification)


@mcp.tool(annotations=WRITE)
def propose_skill_update(name: str, description: str, instructions: str, rationale: str,
                         source_session_ids: list[str], files: dict[str, str] | None = None,
                         verification: str = "") -> dict:
    """Open a PR changing an existing skill. Pass the full new SKILL.md body and any files
    to add or replace; the PR shows the diff against what the team uses today."""
    cfg, _, gh, _ = _deps()
    if gh.read_file(_skill_path(cfg, name)) is None:
        raise ToolError(f"No published skill named {name!r}; use propose_skill.")
    return _propose("update", name, description, instructions, files, rationale,
                    source_session_ids, verification)


@mcp.tool(annotations=WRITE)
def replay_with_skill(session_id: str, branch: str) -> dict:
    """Check that a skill proposal helps: re-run the session's first user message in a fresh
    session with only the proposed skill attached, and have an LLM judge compare the answer
    with the original session's final answer.

    session_id: the candidate session the skill was distilled from. branch: the proposal's
    branch, as returned by propose_skill. Pass = correct answer in fewer turns. The results are
    written into the PR's Verification section and returned here. Takes a few minutes.
    """
    cfg, tf, gh, state = _deps()
    found = state.proposal_for_branch(branch)
    if found is None or "outcome" in found[1]:
        raise ToolError(f"Branch {branch!r} is not an open skillsmith proposal.")
    pr_number, proposal = found
    replayer = Replayer(tf, cfg.repo_url, cfg.skills_dir, cfg.replay_skill_slot,
                        timeout_s=cfg.replay_timeout_s)
    result = replayer.replay(session_id, proposal["name"], branch)
    verification, _ = scrub_text(result.markdown(proposal["name"], branch))
    pr = gh.get_pr(pr_number)
    gh.update_pr_body(pr_number, with_verification(pr["body"] or "", verification))
    state.record_proposal(pr_number, proposal | {"replay": {
        "session_id": result.replay.session_id, "passed": result.passed}})
    return {"pr_number": pr_number, "passed": result.passed, "correct": result.correct,
            "judge_reason": result.judge_reason,
            "original": vars(result.original), "replay": vars(result.replay)}


@mcp.tool(annotations=WRITE)
def close_proposal(pr_number: int, reason: str) -> str:
    """Close a skill proposal PR without publishing it, e.g. after the reviewer denied it."""
    _, _, gh, state = _deps()
    gh.close_pr(pr_number, f"Closed by skillsmith: {reason}")
    state.close_proposal(pr_number, f"closed: {reason}")
    return f"Closed PR #{pr_number}."


def _set_on_team_agents(update) -> list[str]:
    cfg, tf, _, _ = _deps()
    report = []
    for name in cfg.team_agents:
        agent = tf.find_agent(name)
        if agent is None:
            report.append(f"{name}: not found")
            continue
        tf.update_agent(agent, update(agent["manifest"]))
        report.append(f"{name}: updated")
    return report


@mcp.tool(annotations=DESTRUCTIVE)
def publish_skill(pr_number: int) -> dict:
    """Publish a skill proposal to the whole team: merge its PR, register the skill in
    TrueForge, and attach it to the team agents. Requires reviewer approval."""
    cfg, tf, gh, state = _deps()
    proposal = state.proposal(pr_number)
    if proposal is None:
        raise ToolError(f"PR #{pr_number} is not a skillsmith proposal.")
    pr = gh.get_pr(pr_number)
    if pr["state"] != "open":
        raise ToolError(f"PR #{pr_number} is {pr['state']}.")
    name = proposal["name"]
    sha = gh.merge_pr(pr_number, f"Skill {proposal['kind']}: {name} (#{pr_number})")
    tf.upsert_skill({
        "type": "git", "name": name, "url": cfg.repo_url, "path": f"{cfg.skills_dir}/{name}",
        "ref": "main", "description": proposal["description"],
    })
    agents = _set_on_team_agents(lambda m: with_skill(m, name))
    state.close_proposal(pr_number, f"published {sha[:7]}")
    return {"skill": name, "merged": sha, "agents": agents}


@mcp.tool(annotations=DESTRUCTIVE)
def deprecate_skill(name: str, reason: str) -> dict:
    """Withdraw a published skill from the team: detach it from the team agents and remove
    it from the skills repo. Requires reviewer approval."""
    cfg, _, gh, _ = _deps()
    paths = gh.list_tree(f"{cfg.skills_dir}/{name}/")
    if not paths:
        raise ToolError(f"No published skill named {name!r}")
    agents = _set_on_team_agents(lambda m: without_skill(m, name))
    branch = f"{BRANCH_PREFIX}deprecate-{name}-{int(time.time())}"
    title = f"Deprecate skill: {name}"
    gh.commit_to_new_branch(branch, title, dict.fromkeys(paths))
    pr = gh.open_pr(branch, title, f"Deprecated by skillsmith after approval.\n\n{reason}")
    sha = gh.merge_pr(pr["number"], f"{title} (#{pr['number']})")
    return {"skill": name, "merged": sha, "agents": agents}


def main() -> None:
    parser = argparse.ArgumentParser(prog="skillsmith")
    parser.parse_args()
    _deps()  # fail fast on missing config
    mcp.run(
        "streamable-http",
        host=os.environ.get("SKILLSMITH_HOST", "127.0.0.1"),
        port=int(os.environ.get("SKILLSMITH_PORT", "8802")),
    )
