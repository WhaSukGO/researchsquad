# A default research team that can specialize

The general team now uses one `Agent` model/tool loop. Roles are JSON definitions plus Markdown prompts; assignments are separate data. Eight defaults are available: coordinator, planner, researcher, experiment engineer, environment engineer, critic, experience and strategy. The coordinator commissions only the roles needed. See [checkpoints, evidence and stage decisions](checkpoints-and-workflows.md) for the new operating protocol.

## Start a team

```sh
docker pull python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f
uv run python -m goalagent.team --task goals/team-sort.json --run-dir runs/my-team --model gpt-6.1-sol
```

This small non-music task has a protected exact-match evaluator. To investigate literature instead, use `goals/team-literature-review.json`. Its search and download tools require the task's explicit network grant. Public search endpoints may reject automation; failures must be reported. No external-search service subscription or credential is installed automatically.

Use the same command and directory to resume without changing the task, role files, model, implementation or evaluator version. Use a fresh directory when those change. A process lock prevents concurrent writers. Interrupted time is conservatively counted on recovery. Pending actions are retained, but arbitrary shell side effects are not guaranteed exactly once after a crash.

## Define a role without a new class

Each definition in `agents/default/` includes:

```json
{
  "version": 1,
  "id": "planner",
  "model": null,
  "reasoning_effort": "low",
  "system_prompt": "planner.md",
  "tools": ["read_file", "write_file", "list_files", "finish"],
  "limits": {
    "max_steps": 16,
    "max_seconds": 600,
    "command_timeout": 120,
    "model_call_timeout": 180
  }
}
```

`model: null` inherits the CLI model (or existing provider configuration). A model string overrides it for that role. Prompt paths must stay inside the definition directory. Use `--agents-dir` for your own set of definitions; it must contain a coordinator. Unknown tools, duplicate identities and malformed definitions are rejected before model calls. Role tools appear in the model's action schema, and the registry checks the grant again at execution.

The default team does not have host shell access. The existing provider runs model calls with model-side tools disabled. Its temporary prompt directory isolates context; it is not an OS read jail. Execution tools use restricted Docker containers with only the assigned workspace mounted, no Docker socket and no host credentials. Network is a coarse owner-controlled task permission, not a domain-level egress filter.

## Default toolbox

| Capability | Tools and behavior |
| --- | --- |
| Workspace | Read/write text, bounded directory listings and literal text search, inspect images |
| Execution | Run commands/scripts in Docker; full logs on disk, first diagnostic plus bounded tail returned |
| External research | Web search and HTTP(S) fetch in the network-enabled container; shell commands can clone repositories or download assets |
| Team coordination | Catalog, delegate, create a specialist from a template, read prior evidence |
| Environment | Engineer builds a controlled package recipe and readiness test; experiment engineer can request a missing capability and stop |
| Extensions | Register a captured Python script after a passing Docker test; future execution agents can call it |
| Results | Submit frozen artifacts and ask a host-registered evaluator for measurements |

Commands are synchronous; finite deadlines apply only when configured. Workers now return control at configurable checkpoints between completed actions. There is no background-job scheduler or remote GPU provisioner in this increment. Long work can run within configured command limits, with output written to files. An ordinary script requires no registration.

## How assignments and evidence move

The lead supplies the role, a distinct objective, success criteria, explicit inputs, and optional parent/mode. It cannot simply repeat the global goal. Each assignment receives an independent model context and workspace. Public text inputs come from `task.inputs`; binary inputs use `task.assets`, an explicit map of destination names to owner-provided paths (relative to the task file in the CLI). Asset hashes are pinned. No project checkout or reference directory is inherited.

Delegation copies only explicitly selected files into read-only child inputs. The child returns a host-owned checkpoint or final report, with preserved source, output and binary artifacts. The lead receives paths to read-only handoff copies and a concise outcome. An improve branch requires a measured parent; a debug branch requires failed execution. Parent artifacts come from the frozen snapshot, not a mutable workspace. Full records are retrievable by evidence ID.

Delegation is sequential in this increment. Roles do not chat through a shared transcript. Global limits bound calls, active time, assignments and nesting depth; individual role limits apply within those limits. No evaluator means no automatic `goal_met`, even if the lead submits a confident final report.

## Add capabilities during research

A coordinator can use `create_specialist` with a template, new identity, prompt and subset of tools. The specialist inherits the template's model and limits. It cannot grant itself new host privileges. Bounded mode supports up to eight run-local specialists; unlimited mode removes this cap.

An execution engineer can write a Python script that reads JSON from stdin, document its interface, and invoke `register_tool` with a test argument. The host captures the script, tests it in Docker and stores its source/hash. A failed test does not publish it. Bounded mode supports up to sixteen extensions; unlimited mode removes this cap. Future agents with an execution grant receive `script.NAME` in their frozen tool catalog. Read-only roles gain no execution permission. The registering engineer can continue using its ordinary scripts; its existing tool contract does not mutate mid-assignment.

Script-tool registration proves that the supplied test executed. It does not certify scientific validity. Script tools run in the same restricted environment as ordinary experiment code, never as imported host plugins. Run-local extensions do not silently become trusted defaults across future runs; a maintainer can promote useful ones through PR review.

For dependencies, the environment engineer supplies validated Debian package names, pinned Python package requests, and a capability smoke script. The host fixes the base image, isolates the build context, captures dependency versions and publishes a unique retained image tag plus immutable image ID. Readiness runs without network under the actual non-root/read-only restrictions. It does not receive research data or labels. The lead can inspect its readiness receipt and package inventory through the catalog, and new assignments receive that inventory explicitly. New assignments can reuse that image; existing assignments keep their frozen policy. Bounded mode allows three build attempts within the total time budget; unlimited mode removes the attempt cap. Receipts and setup duration are retained. This generic path supports more than the earlier fixed notation/OCR profile, but agent-proposed readiness is still not independent scoring.

## Protected evaluation and music compatibility

Evaluators are versioned host registrations. Agents cannot register a scorer through script tools, change task acceptance, or overwrite the frozen submission. The host verifies the submission hash before every evaluation, including cached evaluations. The included non-music evaluator is deliberately a small software fixture. A new scientific domain usually needs a suitable evaluator and input contract; configuration alone cannot define trustworthy measurement for every problem.

The existing music coordinator remains a compatibility workflow with its existing acceptance checks and protected evaluator. Its experiment engineer now uses the same `Agent` runtime, with music prompts loaded from `agents/music/`. The music coordinator's control loop has not been silently replaced by the general team's policy. Existing recorded runs remain unchanged; changed protected fingerprints require a new run. The general team is the new entry point for configurable roles and arbitrary goals. A full migration of the music workflow into its tool/evaluator adapters is not claimed in this increment.

## Verification

Run the regression suite, then the real-container fixture:

```sh
uv run pytest -q
uv run python -m goalagent.team_check --run-dir runs/new-team-verification
```

The fixture creates a specialist, commissions an engineer to register a sorting tool, obtains a failed protected measurement on an incomplete input, commissions an improvement that reuses the tool with the complete input, and obtains a passing measurement. Resuming adds no calls. Its model decisions are scripted to make the regression deterministic. It proves execution, delegation, extension reuse and evaluation wiring, not autonomous research quality or improved music transcription.

The recorded local verification is [available here](../runs/configurable-team-final-20261029/verification.json): the complete tool-reuse scenario and a real generic environment build/readiness/cache-hit check passed. The regression suite passed 106 tests; two real-Docker music isolation/scoring tests also passed separately. CI includes the new team fixture alongside the existing Docker checks.

New checkpoints and reports preserve binary and text artifacts (up to 256 files, 16 MB per file and 64 MB per bundle); the legacy finish tool retains its 8 MB text contract. Protected text evaluators receive only a text view of explicitly submitted files. A production evaluator for a new scientific domain must define its artifact and acceptance contracts. The generic environment cache is run-local; its immutable image is reused across assignments, while Docker build layers can accelerate another run. Automatic image garbage collection is not included.

## Live music pilot

`python -m goalagent.music_team --run-dir runs/new-music-team --model gpt-6.1-sol` connects the default configured team to the existing music inputs and protected scorer. It supplies seven images and fourteen prediction/export artifacts, with labels retained by the evaluator. It uses a fresh state and the prepared notation/OCR environment; it does not add a new agent class.

The [29 October live assessment](../runs/configurable-music-retry-20261029/assessment.html) records an important limit: the 40-call run created a candidate but exhausted its budget before submission or evaluation. An unchanged, operator-recovered copy improved parse coverage from 3/7 to 5/7; melody errors stayed at 101/130 and chord errors at 38/38. This diagnostic score was not produced by the autonomous loop. The report distinguishes the initial interrupted interface-bug attempt, all three engineer assignments, and the remaining handoff/progress/evaluation gaps. The goal remains unmet.

## Unlimited research budgets

New music-team runs now default to unlimited mode:

```sh
uv run python -m goalagent.music_team --run-dir runs/music-unlimited --model gpt-6.1-sol
```

For another task, set `"unlimited": true` in its task JSON or pass `--unlimited` to `goalagent.team`. The literature-review task enables this mode; the sorting verification fixture remains bounded. `--bounded` restores the historical 40-call music-pilot configuration.

Unlimited mode replaces team call/time/assignment/depth limits and every role's step/time/model-call/command deadlines with JSON `null`. It also removes run-local specialist/tool-count and generic environment-build-attempt caps. A `null` budget can be set individually for a team or role limit; other finite values remain effective. No artificially large integer stands in for unlimited. Model subprocesses receive no timeout, and serialized contracts/context use `null`, never non-standard JSON Infinity.

Usage is still counted and saved. The team can finish normally or be interrupted; use Ctrl-C to stop the CLI. A hung model or command can now wait indefinitely until interrupted. External provider quotas, resource availability, protected scoring and completion requirements still apply. Container CPU/memory/process limits, isolation, output/file/context size bounds, parser/HTTP operational timeouts and the bounded readiness bootstrap remain. A failed bootstrap can still be routed to the environment engineer; it does not end the research session.

The previous live pilot had 40 calls, 1,800 team seconds, six assignments and depth two. Engineers had 16 steps, 600 seconds, 180-second model deadlines and 120-second command deadlines. The legacy music-coordinator entry point retains its separate goal-file budgets; unlimited mode applies to the new configurable team. Existing evidence is never rewritten to change these historical limits. Start a new run when changing budget mode.

The checkpoint and artifact protocol now addresses repeated inspection without coordinator visibility and missing handoffs. Unlimited operation remains a user-selected execution policy, not a claim that research will converge. The earlier assessment is a historical record.
