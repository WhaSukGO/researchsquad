# Working on ResearchSquad

Use this repository as the working project. Its common `goalagent.agent.Agent`
executes every configured role. Role judgment belongs in `agents/*/*.md`, grants
in the adjacent JSON, and mandatory dispatch/gate policy in workflow version 2.
Do not add a new Agent subclass for a new profession.

Read `docs/managed-workflow.md` for interfaces and `docs/managed-workflow-notes.md`
for implementation decisions and remaining limits. Keep `Team` as the single
state/event writer; the work board is part of `team-state.json`.

Develop and run checks on Linux or WSL with Python 3.12 and Docker. The current
POSIX file/process boundaries are not a native Windows implementation. Protected
`.krn` files must retain their exact Git bytes; never change references or expected
digests to make a failing evaluation pass.

Run the relevant pytest cases, then the full suite for host-policy changes.
`python -m goalagent.managed_check --run-dir tmp/NEW-UNIQUE-DIRECTORY` checks real
Docker execution, failed protected measurement, improvement, separate reviewers
and restart. Decisions in that fixture are scripted, not research evidence.

Keep protected evaluators maintainer-owned, never execute agent source on their
host, and never hand reference labels or credentials to workers. A report's DONE
is not project acceptance. Changed contracts require fresh runs. Preserve scoped
negative and inconclusive outcomes without inventing measurements.

Use the PR template. Distinguish source changes, scripted integration fixtures,
actual model calls and domain measurements. Do not commit generated runs, model
credentials, Docker build output or user data.
