# Handoff: cloud session → local session

Written 2026-09-26 at `1f885c7` on `main`. The cloud session couldn't reach TrueForge, acme-app or
skillsmith, so **everything below is unit-tested against fakes only**. Your job locally is to run
it against the live servers, fix what breaks, and get the demo in #3 working end to end.

Read first: `AGENTS.md`, `CONTEXT.md` (use its vocabulary), `docs/adr/`, and the latest comment on
each of issues #2–#5 (`gh issue view N --comments`). Stop and ask the user before changing a design
decided in the ADRs or issues.

## State of the issues

| Issue | Status | Commit |
|---|---|---|
| #2 skillsmith MCP | Done earlier; `publish_skill`, `propose_skill_update`, `deprecate_skill` never exercised live | `0bef897` |
| #5 scrub | Scrub done; the "update PR shows a clean diff" half is unexercised | `7a2d079` |
| #4 replay_with_skill | Implemented; never run live | `70f22e9` |
| #3 distiller | Specs and setup script written; **not run** | `1f885c7` |

## What was added

- `src/tf_hackathon/skillsmith/scrub.py`: deterministic scrubber (regexes plus Shannon entropy),
  stdlib-only so it runs as a script in the sandbox (`python scrub.py [--write] FILES`). Both
  propose tools scrub every file and the PR text, and add a `### Scrub` section to the PR body.
- `src/tf_hackathon/skillsmith/replay.py` plus the `replay_with_skill(session_id, branch)` tool:
  1. Point the reserved skill `skillsmith-replay` at the PR branch.
  2. Replay the original first user message in an inline session tagged
     `metadata.source=skillsmith`. It uses the same agent spec with only that skill, sandbox on
     and `ask_user_questions` off.
  3. An inline judge session (JSON `response_format`) compares the answer with the original's
     final answer.
  4. Point the slot back at `main` with an inert description.
  5. Write original vs replay turns, model calls and tokens into the PR's `### Verification`
     section.

  **Pass** = correct and fewer turns.
- The reserved slot is a user-approved deviation from #4: TrueForge 0.2.1 has **no API to delete
  a configured skill**. Replays are serialised with a lock. Config: `SKILLSMITH_REPLAY_SLOT` and
  `SKILLSMITH_REPLAY_TIMEOUT` (600s).
- `trueforge/`: `agents/acme-ops.json`, `agents/distiller.json` + `distiller.md` (instructions),
  and `schedules/distiller-hourly.json`.
- `src/tf_hackathon/setup_trueforge.py` (`uv run setup-trueforge`) creates or updates the agents
  and the schedule by name. Details:
  - It checks the connectors exist first.
  - `--model` is only needed while an agent is new.
  - Re-runs keep each agent's model and any skills already attached.
  - `--run-now` triggers the schedule.
- `list_sessions` also skips sessions of the `distiller` agent (`SKILLSMITH_DISTILLER_AGENTS`),
  because schedule-created sessions can't carry `metadata.source`.
- The `TrueForge` client (`skillsmith/trueforge.py`) gained session, turn, agent, schedule, model
  and connector methods. All HTTP goes through it.

## API facts (from the TrueForge 0.2.1 sources, not the live docs)

trueforge.dev was blocked, so the cloud session read the TypeScript from the npm package's source
maps: `npm pack @truefoundry/trueforge @truefoundry/trueforge-core`, then extract `sourcesContent`
from `dist/*.js.map`. Against a live server, prefer `GET /api/v1/openapi.json`.

- Skills: `PUT /api/v1/settings/skills` `{manifest: {type: git, name, url, path, ref, description}}`.
  There's no delete.
- Sessions: `POST /api/v1/sessions` `{agent: {spec} | {name}, metadata}`. Turns:
  `POST /sessions/{id}/turns` `{input: [{type: user.message, content}], stream: false}`, then poll
  `GET /sessions/{id}/turns/{tid}` until `state.status != running`. Tokens are at
  `state.metrics.total_tokens`, the answer at `state.output.content`.
- Agents: `GET /agents?agent_name=` (substring match) returns `{id, name, description, manifest}`.
  `PUT /agents/{id}` `{description?, manifest}`.
- Runtime config key is `ask_user_questions` (plural); the tool is `ask_user_question`.
- Schedules: `POST /schedules` `{agent_name, name, manifest: {task, cron, timezone, status}}`, with
  a minimum interval of 1h. Trigger now: `POST /schedules/runs` `{schedule_id}`.
- Names must match `^[a-z][a-z0-9-]{0,62}[a-z0-9]$`.

## Verify live, in this order

1. `uv run pytest`: 62 tests should pass.
2. Register the `acme-app` connector if it isn't already (`http://127.0.0.1:8801/mcp`); skillsmith
   is registered as `skillsmith`. Restart `uv run skillsmith` so it picks up the new tool.
3. Run `uv run setup-trueforge --model <provider/model>` and check that both agents and
   `distiller-hourly` show up in the UI.
4. Record Alice's session on acme-ops: naive error rate, pushback, retry-aware answer. Then
   `PATCH /api/v1/sessions/{id}` with `{"metadata": {"author": "alice"}}`.
5. Try `replay_with_skill` on its own before running the distiller: `propose_skill` a
   hand-written skill, then replay Alice's session against its branch. Watch for these unverified
   points:
   - Does a git skill load from a ref containing `/` (`skillsmith/<name>-<ts>`)?
   - Is a registered name different from SKILL.md's `name:` accepted?
   - Does the judge model honour `response_format: json_schema`? (The parser tolerates prose and
     code fences; anything else counts as a fail.)
   - Does TrueForge time out the MCP tool call during a multi-minute replay? If so, consider
     making replay asynchronous; that's a design change, so ask the user first.
6. `uv run setup-trueforge --run-now`: expect PR(s) under `skills/` with Scrub and Verification
   sections, and the distiller paused on `publish_skill`. Allow publishes the skill and attaches
   it to acme-ops; then a new "Bob" session should use it.
7. Seed a session containing a fake API key and check the PR says it was removed (#5 acceptance).
   Build fake keys by string concatenation, or GitHub push protection may block the push.
8. Check whether the distiller's sandbox can `curl` `raw.githubusercontent.com` for `scrub.py`.
   If not, the instructions fall back to skillsmith's server-side scrub.

## Conventions

- Python 3.14 + uv, MCP SDK 2.x (`MCPServer`). Raise `ToolError` for errors the model should see.
- One commit per step and push to `main`. Comment progress on the relevant issue, and mark
  anything still unverified live.
- Line length is roughly 100; match the surrounding style (terse docstrings, few comments).
