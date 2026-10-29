# Repository cleanup — 30 October 2026

The active repository now contains one configurable research-team architecture. The shared `Agent`, configuration loader, team scheduler, artifact/checkpoint protocol, workflows, prepared environments and protected evaluators remain. Unlimited research effort remains available and is still the music runner's default.

## Retired components

The fixed-menu `goalagent.runner`, older `goalagent.coordinator` / `ExperimentWorker` path, blind-review runner, and their dedicated audits, reports, fork utility and timing helper are retired. Their music-only role definitions and old goal files were removed. Tests specific to those obsolete interfaces were removed; applicable scoring, transposition, input-isolation, environment-escalation and real-Docker checks were retained against the current runtime.

The music domain module now contains `MusicScorer`, inspection and transposition checks. It no longer owns a recognition menu or dispatches experiments. The current music adapter calls this scorer directly; experiments continue through the same configurable `Agent` used by other tasks. Shared integrity helpers and the conservative music completion predicate remain unchanged.

Unused legacy effort-limit fields were removed from the music profile specification. It still supplies sample scope, acceptance criteria and prepared-environment settings; actual team and role budgets are selected by the current runner.

The supported execution entry points are `goalagent.team` and `goalagent.music_team`. The standalone `scorebench` benchmark remains available. The `team_check`, `checkpoint_check` and `environment_check` fixtures remain in CI.

## Generated files and research inputs

Generated `runs/` output is no longer tracked and is ignored for future sessions. Existing run directories are kept on this machine. Superseded PDF reports are also kept locally and in the archive, while the maintained operating guide and its diagram remain in the active tree. No generated run is silently rescored or migrated.

The music task previously depended on predictions inside `runs/first-benchmark`. Those required artifacts and historical aggregate results are copied unchanged into `research/baselines/first-benchmark`. `provenance.json` records each original path, SHA-256, byte count and source revision. The original music images, reference labels, manifest, research notes and source evidence remain.

The delivered baseline still has seven samples, three parseable outputs, 101 melody errors out of 130 and 38 chord errors out of 38. This is an artifact-parity check, not a new research result. Historical paths inside the preserved results JSON describe the archived run; current execution uses the new baseline directory.

## Recover historical code and evidence

The annotated tag `archive/pre-cleanup-20261030` points to pre-cleanup main revision `caad09f98dd985ae8e081aa7689280870ad08a83`. It preserves the older tracked implementation, runs and reports. Git history is not rewritten, so this cleanup reduces the active tree rather than the repository's historical object size.

To inspect that snapshot separately:

```sh
git fetch origin --tags
git worktree add --detach ../researchsquad-pre-cleanup archive/pre-cleanup-20261030
```

Use the archived checkout's documentation and locked dependencies for its commands. Original run state remains pinned to its original implementation and may contain machine-specific paths. Do not overwrite contracts or assume an archived run can resume on another machine unchanged.

The archive tag covers previously committed records. Newer uncommitted local runs, including the checkpoint pilot and stopped unlimited session, remain untouched locally and are now ignored; this cleanup does not publish those large records. Copy or export selected evidence deliberately when it should be shared.

## Verification expectations

The regression suite checks current contracts, handoffs, workflow gates, environment reuse, protected completion, baseline parity and file boundaries. Docker checks exercise real execution, read-only inputs, compact logs, timeouts, immutable environment publication, tool reuse, checkpoint continuation and evidence-driven improvement on a deterministic fixture. A clean-tree export is tested to ensure ignored local run data is not required.

No live model research run is required for this cleanup. These checks establish preserved interfaces and measurement behavior, not improved research accuracy.
