# Approval happens at TrueForge's tool gate, not at PR merge

A skill proposal is opened as a GitHub PR so the reviewer can read the diff, but the PR is never merged by hand. The distiller merges it through its `publish_skill` tool, which is marked destructive so TrueForge pauses the run until the reviewer clicks Allow. That keeps the "stop before irreversible actions" step inside the agent harness (a judging criterion) and lets one decision cover the merge, the skill registration, and attaching the skill to the team agent.
