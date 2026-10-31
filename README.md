# ResearchSquad

A configurable research team with one reusable `Agent`, JSON/Markdown role definitions,
explicit tools, host-managed work, independent reviews and protected evaluation.
Product and research workflows select responsibilities and required evidence.

The [current TODO](docs/TODO-ko.md) separates existing runtime repairs from future
cross-run experience and adaptive research work. [Repair verification](docs/runtime-reliability-results-ko.md)
records fault checks, real GPU regression and actual reader evidence.

Start with the [Korean operating guide](docs/managed-workflow-ko.md),
[configuration and recovery guide](docs/managed-workflow.md), and
[implementation notes](docs/managed-workflow-notes.md).
The [training benchmark proposal](docs/training-benchmark-plan-ko.md) describes nine
research projects. [Training operations](docs/training-runtime.md) and the
[measured implementation report](docs/training-runtime-results-ko.md) describe the
implemented job/checkpoint/trace path and its remaining research limitations.
The [external-source study guide](docs/external-source-study.md) connects actual
paper/code discovery and body reading to source-informed GPU comparisons and
independent final inference. The [actual source-study report](docs/external-source-results-ko.md)
records the negative dropout result, final protected score, role decisions,
storage intervention and report-review failures.

![The reusable agent loop](docs/diagrams/configurable-team-loop.png)

## Run

Use Linux/WSL, Python 3.12, uv and Docker. Actual model calls additionally need the
configured Codex CLI login. Scripted verification fixtures need no model calls.

```sh
uv sync --locked --group dev
docker pull python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f

# Scripted choices and real containers: failure, improvement, reviews and restart.
uv run python -m goalagent.managed_check --run-dir tmp/managed-check-01

# Actual model choices on a small protected sorting task.
uv run python -m goalagent.team --task goals/managed-sort.json --run-dir runs/sort-01

# Reviewed research-question scope; does not claim the music goal is complete.
uv run python -m goalagent.music_team --run-dir runs/music-charter-01 --completion-stage R0
```

Use a fresh directory after changing code, prompts, grants, task or evaluator.
Unchanged completed runs reuse their receipts. External waits and stopped runs need
explicit operator transitions; see the operating guide.

Music defaults select all 32 development excerpts with 80 model calls and one active
hour. `--unlimited` and `--sample-scope first_per_song` are explicit alternatives.
A seven-sample pilot cannot satisfy the full music objective. The configured team
still needs real recognition experiments; the current adapter is not an OMR model.

## Responsibilities and files

Nine roles live in `agents/default/`: coordinator, planner, researcher, experiment
engineer, environment engineer, critic, experience, strategy and report reader.
Policy version 2 automatically dispatches configured stage owners and every required
reviewer. One sequential scheduler records stable work IDs, immutable attempts,
checkpoints, dependency work and concrete revision conditions in team state.
Custom version-1 workflows retain their coordinator-directed interface.

| Location | Purpose |
| --- | --- |
| `agents/default/*.json`, `*.md` | Models, prompts, tool grants and role limits |
| `workflows/` | Product/research owners, required outputs/actions and separate gates |
| `goalagent/agent.py`, `team.py` | Common action loop and the sole state/event writer |
| `goalagent/workboard.py`, `stage_runtime.py` | Work identity, dependencies, dispatch and rework |
| `goalagent/music.py`, `music_team.py` | Protected music scoring and explicit input adapter |
| `research/data/`, `research/manifest.json` | Original music images and protected labels |
| `research/baselines/first-benchmark/` | Preserved baseline predictions and aggregate results |
| `environments/`, `tests/` | Reviewed environments and current regression checks |
| `runs/`, `tmp/`, `output/` | Local generated output, ignored by Git |

Default containers currently have no GPU grant, a 2 GB memory limit and two CPUs.
Opt-in GPU profiles, detached jobs, large dataset/model references and observable
traces are now implemented; see [training operations](docs/training-runtime.md).
The [benchmark plan](docs/training-benchmark-plan-ko.md) describes the research
quality questions beyond the included fixed learning fixture.

## Verify

```sh
uv run --no-sync pytest -q
GOALAGENT_DOCKER_TESTS=1 uv run --no-sync pytest -q tests/test_sandbox.py tests/test_environments.py tests/test_budgets.py
uv run --no-sync python -m goalagent.managed_check --run-dir tmp/managed-check-02
```

CI also runs environment, configurable-tool and checkpoint fixtures. A scripted
fixture proves execution/control flow, not autonomous scientific quality. Protected
labels, numeric criteria and scope requirements are maintainer-owned.

## Documentation and history

- [Role configuration](docs/configurable-team.md)
- [Checkpoint and workflow protocol](docs/checkpoints-and-workflows.md)
- [Prepared environment operations](docs/environment-operations.md)
- [Cleanup decisions and recovery](docs/repository-cleanup.md)
- [Verification of managed workflows](docs/verification/managed-workflow-20261030.json)

The supported team entry points are `goalagent.team` and `goalagent.music_team`.
The standalone `scorebench` benchmark remains. Superseded fixed-menu,
coordinator/worker and blind-review runners, their dedicated roles/goals/tests,
generated tracked runs and obsolete exports are removed from the active tree.
Git history and the archive tag retain prior versions. Current protected music
inputs remain available without depending on generated runs.
