# Skillsmith demo script

Entry for **Agents That Act: TrueFoundry × Polaris**. Target runtime: **3:30** (hard cap 4:00).

This file is written for the agent that will record, edit and narrate the video. Read all of
"How to use this script" before touching a scene.

---

## How to use this script

### Conventions

- Each scene has these parts:
  - **Screen**: what is visible.
  - **Actions**: what to do on screen, in order.
  - **VO**: the voice-over, to be spoken word for word.
  - **On screen**: captions, badges and highlights to add in the edit.
  - **Capture**: how to record the scene.
- Only the text in `> VO:` blocks is spoken. Nothing else in this file is read aloud.
- `{LIKE_THIS}` is a placeholder. Fill it from the source named in the placeholders table,
  **never** from a guess. If you can't find a value, stop and report which one is missing.
- Timings are targets. When a scene runs long, speed up the footage (show a `×N` chip) rather
  than cutting VO.
- Match the TrueForge UI's real labels. Where this script names a button or panel (Allow,
  Settings → Skills, the session's tool calls), use what the UI actually shows and keep the VO
  as written.

### The three judged moments

The judges score three things, and each gets one **primary moment**. At a primary moment, show a
full-width lower-third banner for 4 seconds while the VO names the criterion. Later mentions get a
small corner chip only.

| # | Badge text | Primary moment | Reprises (chip only) |
|---|---|---|---|
| ① | **Reaches real systems** | Scene 3: the distiller reads the TrueForge session store | Scene 1 (acme-app), scene 4 (GitHub PR) |
| ② | **Runs code safely in a sandbox** | Scene 4: scrub and replay, both in Daytona | Scene 1 (log analysis) |
| ③ | **Stops before irreversible actions** | Scene 5: the run pauses on `publish_skill` | Scene 7 (updates and deprecation) |

Badge style: number in a circle, then the text. Use the same colour per criterion everywhere.

### Placeholders

| Placeholder | Where to read it |
|---|---|
| `{TRUEFORGE_URL}` | The TrueForge instance used for recording (local, e.g. `http://localhost:…`) |
| `{ALICE_SESSION_ID}` | TrueForge: Alice's session on acme-ops (`metadata.author=alice`) |
| `{BOB_SESSION_ID}` | TrueForge: Bob's session, created in scene 6 |
| `{PR_NUMBER}` | The PR the distiller opens in scene 4 (github.com/mkartic/tf-hackathon) |
| `{SKILL_NAME}` | The skill name in that PR's title (`Skill new: \`…\``) and its `skills/<name>/` path |
| `{SCRIPT_PATH}` | The script file in the PR, e.g. `scripts/error_rate.py` |
| `{ORIG_TURNS}`, `{ORIG_TOKENS}` | The PR's `### Verification` table, "original" row |
| `{REPLAY_TURNS}`, `{REPLAY_TOKENS}` | The same table, "replay" row |
| `{TOKENS_SAVED_PCT}` | `round(100 × (1 − REPLAY_TOKENS / ORIG_TOKENS))`. Compute it; don't estimate |
| `{SCRUB_SUMMARY}` | The PR's `### Scrub` section, first line |

Always write numbers the way they appear here: **31.02%**, **4.07%**, **61 of 1,500**. These are
the fixed ground truth of the seeded acme-app log and don't change between recordings:

| Fact | Value |
|---|---|
| Service, window | checkout-api, last 6 hours |
| Log lines (attempts) | 2,086 |
| Attempts with status 5xx | 647, so the naive rate is **31.02%** |
| Requests (distinct `req_id`) | 1,500 |
| Requests whose final attempt failed | 61, so the correct rate is **4.07%** |

If the agent in any recording states a different number, the take is wrong. Re-record it; don't
edit the number.

### Vocabulary (from `CONTEXT.md`)

Both the VO and the captions must use these words. The VO below already does, so don't paraphrase
it.

| Say | Never say |
|---|---|
| session | chat, chat log, conversation, thread |
| teammate | user, member |
| team agent (acme-ops) | assistant, bot |
| distiller, distillation run | miner, crawler, summarizer, job, batch |
| skill, skill proposal | playbook, recipe, doc, draft, suggestion |
| scrub | sanitize, redact |
| replay, pass | test, eval |
| publish, deprecate | deploy, release, delete, retire |
| reviewer | approver, admin |
| request, attempt, final attempt | log line, event (for an attempt) |

"Merged" is fine only as a description of what `publish_skill` does to the PR. Never use it as
a synonym for publishing.

---

## Pre-flight (before recording anything)

Check every item. If one fails, stop and report it rather than working around it.

1. These are all running on the recording machine:
   - TrueForge, started with `OUTBOUND_URL_ALLOWED_HOSTS='["localhost","127.0.0.1"]'`
   - acme-app (`:8801`)
   - skillsmith (`uv run skillsmith`, `:8802`)
2. TrueForge has the `acme-app` and `skillsmith` connectors, the agents `acme-ops` and
   `distiller`, and the schedule `distiller-hourly` (`uv run setup-trueforge`).
3. **acme-ops has no skills attached** (Settings → Agents → acme-ops). If a previous take
   published a skill, deprecate it first, or Bob's session in scene 6 proves nothing.
4. Alice's session exists on acme-ops, is tagged `metadata.author=alice`, and is **not yet
   processed**. For a clean run it is the only unprocessed session. Reset
   `.skillsmith/state.json` between takes if needed.
5. `skills/` on `main` in github.com/mkartic/tf-hackathon doesn't already contain the skill.
6. Browser windows:
   - A: TrueForge UI, logged in, zoom 125%
   - B: GitHub, repo PR list
   Hide bookmarks, notifications and any personal tabs. Use a dark or light theme, but the
   same one throughout.
7. Nothing secret is visible anywhere: no `GITHUB_TOKEN`, API keys or terminal history. The repo
   is public (ADR 0003), and so is the video.

---

## Scene 0: Cold open (0:00–0:15)

**Screen:** Title card on a plain background: "Skillsmith". Subtitle: "Your team's hard-won fixes,
turned into skills every agent can use." Small footer: "Built on TrueForge".

**Actions:** None. Fade in, hold, fade to scene 1.

> VO: On a big team, people keep rediscovering the same fixes. One teammate's agent learns a
> trap the hard way, and next week another teammate's agent falls straight into it.

**Capture:** Rendered title card, no screen recording.

---

## Scene 1: Alice's session (0:15–0:55)

**Screen:** TrueForge window A, showing session `{ALICE_SESSION_ID}` on agent **acme-ops**.
Show the author tag "alice" in the session header or metadata if the UI displays it.

**Actions:**
1. Open Alice's recorded session. Scroll to the top.
2. Highlight Alice's first message: *"What was checkout-api's error rate over the last 6 hours?"*
3. Briefly expand the `fetch_logs` tool call (acme-app), then the sandbox code that counts the
   lines. Collapse both after about 2 seconds.
4. Highlight the agent's first answer: **31.02%**.
5. Highlight Alice's pushback: *"we'd have been paged"* (use her exact wording from the
   session).
6. Scroll to the agent's corrected answer. Highlight **4.07% (61 of 1,500 requests)** and the
   sentence where it explains that the gateway retries under the same `req_id`.
7. Cut in the log excerpt below as an overlay for 5 seconds.

Log excerpt overlay (real lines from the seeded log, monospace, `req_id` highlighted):

```
09:00:20.330Z level=ERROR svc=checkout-api req_id=1a69e7f1 status=500 err="connection reset by peer"
09:00:20.856Z level=ERROR svc=checkout-api req_id=1a69e7f1 status=502 err="bad gateway"
09:00:21.959Z level=INFO  svc=checkout-api req_id=1a69e7f1 status=200
```

Caption under the overlay: "3 attempts, 1 request, and it succeeded."

> VO: Here's Alice on acme-ops, our team agent. She asks for checkout-api's error rate over the
> last six hours. The agent pulls the logs from the acme-app MCP server, counts the failures in
> its sandbox, and says thirty-one percent.
>
> Alice pushes back: we'd have been paged. So the agent digs in. The gateway retries a failed
> request under the same request ID, so one request can leave three attempts in the log, and
> only the final attempt counts. The real rate is 4.07 percent: 61 of 1,500 requests.
>
> Alice got there. But that lesson is stuck in her session.

**On screen:**
- Chips at step 3: ① "acme-app MCP" and ② "sandbox", small, top-right.
- At step 4, strike through 31.02% in red. At step 6, show 4.07% in green.

**Capture:** Screen recording of window A. Make scrolling smooth, not jumpy.

---

## Scene 2: Trigger the distiller (0:55–1:10)

**Screen:** TrueForge → Schedules → `distiller-hourly` (agent: **distiller**, cron `0 * * * *`).

**Actions:**
1. Show the schedule row, with its hourly cron visible.
2. Click the control that runs it now. If the UI has none, run `uv run setup-trueforge
   --run-now` in a terminal with a clean, large font, then switch back.
3. Open the new distiller session it creates.

> VO: Skillsmith is a TrueForge agent called the distiller. It runs every hour on a schedule. For
> the demo, we'll trigger it now.

**On screen:** Caption: "distiller-hourly: one distillation run per hour".

**Capture:** Screen recording. If you used a terminal, crop it to show only the command and its
one-line output.

---

## Scene 3: Reading the session store (1:10–1:35), primary moment ①

**Screen:** The distiller session, with its tool calls expanded as they stream in.

**Actions:**
1. Show the `list_sessions` call and its result. Highlight Alice's session in the list.
2. Show `list_skills`, whose result has no skill for this problem yet.
3. Show `get_session_transcript` for `{ALICE_SESSION_ID}`. Expand it just enough to show turns
   and tool calls.
4. Show the distiller's reasoning that this is a candidate: non-trivial, solved, with a
   correction from the teammate.

> VO: First, it reaches a real system: TrueForge's own session store. Through the skillsmith MCP
> server it lists the sessions it hasn't processed, then reads Alice's transcript. There's a
> correction and an accepted answer, so it's a candidate.

**On screen:**
- **Primary banner ①: "Reaches real systems: TrueForge session store"**. Show it at the start
  of the VO and hold it for 4 seconds.
- Label each tool call as it appears: "TrueForge sessions", "skills on GitHub `main`".

**Capture:** Screen recording, sped up ×4 to ×8 between tool calls with a visible `×N` chip.
Play the highlighted tool results at 1×.

---

## Scene 4: Draft, scrub, open the PR, replay (1:35–2:25), primary moment ②

**Screen:** The distiller session, then GitHub window B, then back to TrueForge.

**Actions:**
1. Show the distiller drafting the skill: `SKILL.md` plus `{SCRIPT_PATH}`. Show it running the
   script in the sandbox against the fetched log, with output 4.07%.
2. Show the sandbox commands that fetch and run the scrubber:
   `curl … scrub.py` and `python scrub.py --write SKILL.md scripts/*.py`, plus the JSON report.
   If the sandbox couldn't reach GitHub in this take, skip this step and rely on the Scrub
   section in step 4.
3. Show the `propose_skill` call and its result: PR `#{PR_NUMBER}` and the branch
   `skillsmith/{SKILL_NAME}-…`.
4. Switch to window B. Open PR `#{PR_NUMBER}`. Scroll the description slowly past these
   sections: **When to use**, **Evidence** (the session ID), **Scrub** (`{SCRUB_SUMMARY}`).
   Stop at **Verification**, which says "Not replayed" at this point.
5. Switch back to TrueForge. Show the `replay_with_skill` call in the distiller session.
6. Open the replay session: a new session tagged `source=skillsmith` with only the proposed skill
   attached. Show it loading the skill, running the script in its own fresh sandbox, and
   answering 4.07% in one turn.
7. Switch to window B and refresh the PR. The **Verification** table is now filled in. Zoom in
   on it.

> VO: Now it runs code, and all of it runs in a Daytona sandbox, never on our machines. It writes
> the skill: the retry trap, and a script that counts only each request's final attempt. It
> scrubs the skill proposal for secrets and personal data, then opens a pull request on GitHub.
>
> Then the key step: replay. Skillsmith asks Alice's question again, in a fresh session and a
> fresh sandbox, with only this skill attached. Straight to 4.07 percent. The verification
> table goes into the PR: {ORIG_TURNS} turns and {ORIG_TOKENS} tokens for Alice, against
> {REPLAY_TURNS} and {REPLAY_TOKENS} for the replay. That's a pass.

**On screen:**
- **Primary banner ②: "Runs code safely in a sandbox: Daytona"**. Show it at "all of it runs
  in a Daytona sandbox" and hold it for 4 seconds.
- Step 2: caption "Scrub: secrets and personal data removed before the PR opens".
- Step 3–4: chip ① "GitHub".
- Step 6: caption "Replay: fresh session, fresh sandbox, only the proposed skill".
- Step 7: highlight box around the Verification table. Chip "Pass: correct, and fewer turns".

**Capture:** Screen recording in both windows. The replay takes minutes, so speed it up ×8 to ×16
with a `×N` chip and play the final answer at 1×. Don't cut the replay out: seeing it run is the
point.

---

## Scene 5: The approval gate (2:25–3:00), primary moment ③

**Screen:** TrueForge distiller session, paused. Then GitHub PR diff. Then TrueForge again.

**Actions:**
1. Show the distiller calling `publish_skill` for `#{PR_NUMBER}`, and the session **paused**
   awaiting approval, with Allow and Deny visible. Hold for 2 seconds on the paused state.
2. Switch to window B, the **Files changed** tab of PR `#{PR_NUMBER}`. Scroll `SKILL.md`, then
   `{SCRIPT_PATH}`, pausing on the lines that group by `req_id` and keep the final attempt.
3. Scroll to the bottom of the PR description, the **Review** section: "Don't merge this PR on
   GitHub…". Highlight it.
4. Switch to window A. Move the cursor to **Allow**, hold for 1 second, then click.
5. Show the `publish_skill` result: merged, registered, attached to acme-ops.
6. Show three quick confirmations, about 1.5 seconds each:
   - The PR now shows as merged, by the distiller.
   - Settings → Skills lists `{SKILL_NAME}`.
   - acme-ops's skills list includes `{SKILL_NAME}`.

> VO: Publishing reaches every teammate's agent, so it's the step we don't let an agent take on
> its own. publish_skill is marked destructive, so TrueForge pauses the run right here.
>
> The reviewer reads the diff on GitHub, but approves in TrueForge, not by merging. One click on Allow merges the PR,
> registers the skill, and attaches it to acme-ops. Deny, and the distiller closes the PR and
> nothing reaches the team.

**On screen:**
- **Primary banner ③: "Stops before irreversible actions: human approval in TrueForge"**.
  Show it at step 1 and hold it for 4 seconds.
- Step 1: pulse outline on the Allow and Deny controls.
- Step 3: caption "Review on GitHub. Approve in TrueForge."
- Step 4: cursor click ripple on Allow.

**Capture:** Screen recording at 1×. Don't speed up this scene.

---

## Scene 6: Bob asks the same question (3:00–3:20)

**Screen:** TrueForge window A, a **new** session on acme-ops.

**Actions:**
1. Start a new session on acme-ops and tag it `metadata.author=bob`, as with Alice. Do the
   tagging before recording or off-screen.
2. Type exactly: *"What was checkout-api's error rate over the last 6 hours?"*
3. Show the agent loading `{SKILL_NAME}` and running `{SCRIPT_PATH}` in the sandbox.
4. Highlight the answer: **4.07% (61 of 1,500 requests)**. It should come first time, with no
   pushback needed.

> VO: Next day, Bob asks the same question in a brand-new session. His agent loads the skill,
> runs the script, and answers 4.07 percent first time. Bob never learns there was a trap.

**On screen:**
- Side-by-side split for 3 seconds at step 4: left "Alice: 31.02% → pushback → 4.07%", right
  "Bob: 4.07%".
- Caption: "Same team agent. One published skill."

**Capture:** Screen recording at 1×. Type at a natural speed; don't paste.

---

## Scene 7: Numbers and the production path (3:20–3:45)

**Screen:** Rendered end cards, no screen recording.

**Card 1: Numbers.** Two columns, Alice vs Bob or replay:
- Turns: `{ORIG_TURNS}` → `{REPLAY_TURNS}`
- Tokens: `{ORIG_TOKENS}` → `{REPLAY_TOKENS}` (**−{TOKENS_SAVED_PCT}%**)
- Answer: 31.02% then 4.07%, versus 4.07% the first time

**Card 2: Production path.** Three short lines:
- Opt-in session sharing, not one shared identity (ADR 0001)
- Skill updates arrive as diff PRs, through the same gate
- Deprecating a skill is destructive too, so it pauses for the reviewer as well

**Card 3: Close.** "Skillsmith: agents that learn from each other, with a human deciding what
the team gets." Repo URL: `github.com/mkartic/tf-hackathon`.

> VO: The skill saved {TOKENS_SAVED_PCT} percent of the tokens and every turn of pushback, and it
> saves them again for every teammate who asks.
>
> In production, teammates opt in to sharing their sessions instead of one shared identity. And
> skill updates and deprecations stop at the same approval gate.
>
> Skillsmith: your team's hard-won fixes, learned once and reviewed by a human.

**On screen:** Chip ③ on the "same approval gate" line of card 2.

**Capture:** Rendered cards, with a 0.3-second crossfade between them.

---

## Post-production checklist

- [ ] Every `{PLACEHOLDER}` is replaced, and none are left in captions, cards or VO.
- [ ] Every figure on screen matches the fact table and the PR's Verification table.
- [ ] Each of ①, ② and ③ has exactly one primary banner and it's readable at 1080p.
- [ ] No banned vocabulary in the VO or captions (see the vocabulary table).
- [ ] No tokens, keys, emails or personal tabs are visible in any frame.
- [ ] Every sped-up segment shows a `×N` chip. Scene 5 is not sped up.
- [ ] Runtime is 4:00 or less.
