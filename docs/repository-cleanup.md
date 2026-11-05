# Repository cleanup — 30 October 2026

The supported architecture is the common Agent with configurable roles, the Team
state/event writer and managed product/research workflows. PR #8 was merged first;
this cleanup updates the earlier PR #7 against that main without reverting its
mandatory owners, separate reviewers, recovery or acceptance behavior.

## Removed active code

The fixed-menu runner, old coordinator/ExperimentWorker path, blind-review runner,
and their dedicated audits/reports/fork/timing helpers are retired. The 12 removed
modules are `runner`, `coordinator`, `research`, `worker`, `roles`, `blind_review`,
`blind_audit`, `audit`, `diagnostic_report`, `fork`, `report` and `timing` under
`goalagent/`. Their music-only role files, obsolete goal files and interface-specific
tests are also removed. Applicable scoring, transposition, environment-escalation,
file-boundary and real-container checks are retained against the current runtime.

`music.py` now retains MusicScorer, inspection and transposition, without a recognition
menu. The current music adapter imports that scorer. The common Agent, nine current
roles, managed work/reviews, original metrics and completion predicate remain.
Supported entry points are `goalagent.team` and `goalagent.music_team`; the standalone
`scorebench` benchmark and current verification fixtures also remain.

Version-1 custom workflow support is retained because it is still a tested interface.
The retired runners are separate implementations, not the version-1 workflow mode.
The music default remains managed/all-32/finite-80-calls-and-one-hour. Unlimited mode
and the seven-sample pilot require explicit selection.

## Inputs and generated output

Generated tracked `runs/` files and superseded diagrams/PDF reports are removed from
the active tree. Current local scratch runs remain ignored; no new local run or
user dataset is published. Duplicate pre-managed operating guides/examples are
retired in favor of the current Korean/English managed guides. Their earlier
versions remain in Git history, including the original cleanup branch commit.
Future report exports under `output/` are ignored.

Required baseline predictions and aggregate results are relocated byte-for-byte to
`research/baselines/first-benchmark`. The provenance manifest covers 163 original
files. Current execution no longer depends on generated `runs/first-benchmark`.
Byte-pinned baseline JSON/XML/kern files are exempt from checkout line-ending
conversion. Original images, protected references and the reference manifest remain.
Baseline parity is a retention check, not a new recognition result.

## Recovery

The existing annotated tag `archive/pre-cleanup-20261030` retains pre-managed main
`caad09f`. The additional `archive/pre-managed-cleanup-20261030` tag retains main
`fd4ffd2`, including the merged managed workflow and the former tracked output.
No Git history is rewritten or purged. Cleanup reduces the active tree, not the
repository's historical object size.

```sh
git fetch origin --tags
git worktree add --detach ../researchsquad-archived archive/pre-managed-cleanup-20261030
```

Use the archived version's dependencies and contracts for its commands. Do not
resume old run state under changed implementation or rewrite it to match a new one.

## Validation and training scope

Current regression, managed Docker fixture, clean-tree input availability and PR CI
are recorded in the cleanup verification JSON. Local Ubuntu startup hit a VHDX
sharing violation; locked dependencies were therefore also tested through Docker
from Windows, without forcing a WSL restart. GPU visibility and an actual CUDA
kernel were checked separately. These are not neural-model training evidence.

The training benchmark proposal supplies nine
learning projects and identifies required GPU/job/dataset/checkpoint/evaluator
extensions. This cleanup does not silently claim those extensions are implemented.
