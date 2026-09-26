# Skillsmith

Skillsmith mines a team's agent sessions for hard-won know-how and turns it into verified, reusable skills, so teammates stop rediscovering the same solutions. A human approves every skill before it reaches the team.

## Language

### Team and sessions

**Teammate**:
A person on the team who works with agents. Identified by the author tag on their sessions, not by a login.
_Avoid_: User, member

**Session**:
One conversation between a teammate and an agent, including every turn and tool call.
_Avoid_: Chat, chat log, conversation, thread

**Team agent**:
The shared agent teammates use for everyday work; published skills are attached to it.
_Avoid_: Assistant, bot

**Processed session**:
A session the distiller has already considered, whether or not it yielded a candidate.

### Distillation

**Distiller**:
The scheduled agent that reads sessions and produces skill proposals.
_Avoid_: Miner, crawler, summarizer

**Distillation run**:
One execution of the distiller over the sessions not yet processed.
_Avoid_: Job, batch

**Candidate**:
A session (or set of sessions) judged to contain a non-trivial, solved problem worth turning into a skill.

**Skill**:
A reusable instruction pack, optionally with scripts, that an agent loads when relevant.
_Avoid_: Playbook, recipe, doc, knowledge-base entry

**Skill proposal**:
A new skill or a change to an existing skill, drafted by the distiller and awaiting a human decision.
_Avoid_: Draft, suggestion

**Scrub**:
Removing secrets and personal data from a skill proposal before it is shown to anyone.
_Avoid_: Sanitize, redact

**Replay**:
Re-running a candidate's original task in a fresh session with the proposed skill attached, to check the skill helps.
_Avoid_: Test, eval

**Pass**:
A replay that reaches the correct answer in fewer turns than the original session.

### Approval

**Publish**:
Making an approved skill live for the team: it lands in the shared skills and is attached to the team agent.
_Avoid_: Deploy, release, merge

**Deprecate**:
Withdrawing a published skill from the team.
_Avoid_: Delete, retire

**Reviewer**:
The human who approves or denies a publish or deprecate.
_Avoid_: Approver, admin

### Demo system (acme-app)

**acme-app**:
The fictional production service whose logs teammates investigate in the demo.

**Request**:
One logical client call to acme-app, identified by its request ID.

**Attempt**:
One try at serving a request; a failed request may be retried, producing several attempts with the same request ID.
_Avoid_: Log line, event

**Final attempt**:
The last attempt for a request; it alone decides whether the request succeeded.
