# Skillsmith

**Your team's hard-won fixes, turned into skills every agent can use.**

On a big team, people keep rediscovering the same fixes. One teammate's agent learns a trap the
hard way, and next week another teammate's agent falls straight into it. Skillsmith is a
[TrueForge](https://trueforge.dev) agent that mines the team's agent sessions for that know-how,
turns it into verified skills, and, once a human approves, gives it to every teammate's agent.

Built for **Agents That Act: TrueFoundry × Polaris**.

## How it works

```
teammates' sessions ──► distiller (TrueForge, hourly schedule)
 (TrueForge session store)   │ 1. list + read unprocessed sessions        ← skillsmith MCP
                             │ 2. draft SKILL.md + helper script, test it  ← Daytona sandbox
                             │ 3. scrub for secrets / personal data        ← Daytona sandbox
                             │ 4. open a skill proposal PR                 ← GitHub
                             │ 5. replay the original task with only       ← fresh TrueForge session
                             │    the new skill; judge the answer
                             │ 6. publish_skill  ⏸ paused for a reviewer   ← TrueForge tool approval
                             ▼
             Allow: PR merged, skill registered, attached to the team agent
             Deny:  PR closed, nothing reaches the team
```

The three judged criteria:

| Criterion | Where |
|---|---|
| Reaches real systems | The TrueForge session store, GitHub, and the acme-app log service, all through MCP |
| Runs code safely in a sandbox | The drafting, testing, scrubbing and replay all run in Daytona sandboxes; credentials stay in the harness |
| Stops before irreversible actions | `publish_skill` and `deprecate_skill` are marked `destructiveHint: true`, so TrueForge pauses for Allow or Deny |

### The demo

- **acme-app** is a fictional service whose gateway retries failed requests under the same
  `req_id`. Counting 5xx log lines says checkout-api's 6-hour error rate is **31.02%**. The real
  rate, counting only each request's final attempt, is **4.07%** (61 of 1,500).
- **Alice** asks the team agent `acme-ops`, gets 31.02%, pushes back, and ends up at 4.07%.
- The **distiller** finds her session and writes a skill for the trap. Its replay passes (2 turns
  → 1 turn). The run then pauses for approval.
- After **Allow**, **Bob** asks the same question in a new session. His agent loads the skill first
  and answers 4.07% the first time.

Screenshots of every step are in [`docs/demo/screenshots/`](docs/demo/screenshots), and the video
source is in [`docs/demo/video/`](docs/demo/video).

## Repo layout

| Path | What |
|---|---|
| `src/tf_hackathon/acme_app/` | acme-app MCP server: deterministic logs with the retry trap (`fetch_logs`) |
| `src/tf_hackathon/skillsmith/` | skillsmith MCP server: sessions, skills, PRs, scrub, replay, publish |
| `src/tf_hackathon/setup_trueforge.py` | Creates or updates the agents and schedule from `trueforge/` |
| `trueforge/agents/` | Agent specs: `acme-ops` (team agent) and `distiller` (+ `distiller.md` instructions) |
| `trueforge/schedules/` | `distiller-hourly` |
| `skills/` | Published team skills (TrueForge loads them from this public repo) |
| `CONTEXT.md`, `docs/adr/` | Domain glossary and design decisions |

## Run it

You need Node 22.14+, Python 3.14 with [uv](https://docs.astral.sh/uv/), the `gh` CLI (logged
in), an OpenAI API key and a [Daytona](https://www.daytona.io) API key that can create snapshots.

1. **Start TrueForge** so it can reach the local MCP servers:

   ```sh
   OUTBOUND_URL_ALLOWED_HOSTS='["localhost","127.0.0.1"]' npx @truefoundry/trueforge@latest
   ```

   Open http://localhost:8790, then add your OpenAI key (Settings → Models) and your Daytona key
   (Settings → Sandbox providers).

2. **Start the MCP servers**:

   ```sh
   uv sync
   uv run acme-app                                   # :8801
   GITHUB_TOKEN=$(gh auth token) uv run skillsmith   # :8802
   ```

   Set `SKILLSMITH_REPO=owner/repo` to publish skills to your own fork. The repo must be public.

3. **Register the connectors** in Settings → Connectors → Add MCP Server:
   - `acme-app` at `http://127.0.0.1:8801/mcp`
   - `skillsmith` at `http://127.0.0.1:8802/mcp`

4. **Create the agents and the schedule**:

   ```sh
   uv run setup-trueforge --model openai/gpt-5-5
   ```

5. **Run the demo**:
   1. Ask `acme-ops`: *"What was checkout-api's error rate over the last 6 hours?"* If it says
      31%, push back until it counts the final attempt per `req_id`.
   2. Tag the session: `PATCH /api/v1/sessions/{id}` with `{"metadata": {"author": "alice"}}`.
   3. Go to Schedules → `distiller-hourly` and click **Run now**.
   4. When the run pauses, review the PR, open the run, click **Resume now**, then **Allow**.
   5. Ask `acme-ops` the same question in a new session.

`uv run acme-app stats checkout-api 6h` prints the ground truth. `uv run pytest` runs the tests.

## Notes

- Use a model that opens attached skills. gpt-5.4-mini ignored them in our tests; gpt-5.5 loads them.
- TrueForge's own session list is creator-only, so the demo runs everyone on one no-auth instance
  ([ADR 0001](docs/adr/0001-single-shared-identity.md)). In production, teammates would opt in to
  sharing their sessions.
- skillsmith keeps its processed-session and proposal state in `.skillsmith/state.json`
  (gitignored).
