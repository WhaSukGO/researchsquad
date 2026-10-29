# A team that returns evidence before choosing more work

This implementation adapts the user-supplied **Four-Perspective Multi-Agent Design** (English edition, 29 October 2026). Its research, engineering, experience and strategy perspectives are configurable responsibilities. Every member still uses the same `Agent` runtime. The coordinator assigns work; the host owns execution, durable state and acceptance. The critic supplies evidence review. Environment preparation remains a separate engineering assignment.

The initial implementation priorities came from the music runs: a worker could keep inspecting for 131 calls without returning for evaluation, failed workers could lose shell-created files from their handoffs, and child assignments could receive incorrectly nested input paths. This change addresses those execution problems. It does not establish an improvement in music accuracy.

## What a work period looks like

1. The coordinator gives someone a distinct objective, acceptance criteria and actual inputs. It can also specify required outputs and evidence types for individual acceptance checks.
2. The host registers the inputs by content hash, writes the task packet and supplies exact read-only paths. A destination written as `inputs/example.png` becomes `inputs/example.png` in the child, without an additional `inputs/` prefix. Ambiguous duplicate destinations are rejected.
3. The worker implements, inspects or measures. Full command logs stay on disk; recent context and evidence reads are bounded.
4. The worker calls `checkpoint` with findings, failures and the next useful test, or the host yields after eight actions by default. The host preserves regular authored files, including files created by shell commands and binary outputs.
5. The coordinator gets the checkpoint ID, partial artifacts, progress, failure details and input inventory. It can call `continue_assignment` with a concrete next instruction, commission another person, request environment repair, or stop.
6. The worker submits a final assignment report. The coordinator requests protected measurement of a completed candidate and uses the result to improve that branch, investigate failure, or explore another approach.

`checkpoint_interval` is configurable per role. It is a scheduling cadence, **not a total budget**. Unlimited mode continues to use JSON `null` for total calls, time, assignments, nesting and role deadlines. Continued work retains its original assignment, workspace, counters and durable findings. In version 1 the coordinator has no automatic work-period cutoff; managed version 2 defaults to a one-action coordinator period.

Checkpoints are cooperative, between completed tool/model actions. A single command or model call with an unlimited deadline can still run indefinitely until the operator interrupts it. This implementation does not add a background scheduler or preempt a command midway through execution.

## Assignment and report contracts

`delegate` accepts the existing `inputs` path map and a new `input_artifact_ids` map. It also accepts:

- `required_outputs`: objects with `path`, `kind` and `description`.
- `acceptance_checks`: objects with `check_id`, `description` and `required_evidence_kind`.
- `review_of`: the assignment whose frozen candidate the reviewer must inspect.

The host binds the actual role, tools, workflow stage, revision and remaining budget into the saved task packet. Existing string `success_criteria` remains supported. Output delivery is enforced for `DONE`; semantic acceptance is governed separately by protected gates.

`submit_report` returns `DONE`, `NEEDS_INPUT` or `FAILED`, with a summary, files, optional claims, objections, next actions and open questions. Failed reports classify environment, implementation, measurement, performance, missing-input or other failures. Empty file lists are permitted for honest blocked reports. The host assigns claim/objection IDs and checks cited evidence and objection targets. Reports cannot declare their own evidence verified.

Legacy `finish` remains available for bounded text submissions. Both report paths preserve the distinction between completing an assignment and achieving the project goal. Missing dependencies do not refute a scientific hypothesis.

A debug or improvement branch inherits the parent's preserved authored files **and its registered input files**, unless the coordinator explicitly supplies a replacement input. Original versions remain in the registry. Full reviewers receive the specified candidate version and its inputs; managed report-only readers receive only explicitly selected report files. No reference labels or other host-private files are introduced by this mechanism.

## What is preserved

The run contains the pinned charter and contract, atomic team state, a decision/event journal, task packets, reports, immutable evidence records, and a content-addressed artifact registry. Each agent also keeps action receipts, progress, checkpoint manifests, snapshots and original command logs.

Automatic snapshots include up to 256 files, 16 MB per file and 64 MB per bundle. They exclude read-only inputs and cache/scratch/dependency directories. Important scratch files can be explicitly named in a checkpoint. Unsafe links, oversized files and scan limits appear in an omission manifest; a checkpoint is not represented as a complete machine backup. Explicit submissions fail if their files cannot be preserved. Binary files are retained and handed off; existing protected text evaluators still receive a text view of submitted artifacts.

Candidate revisions include the artifact bundle and evaluator version, including binary artifacts. Old receipts and handoff directories are never overwritten when work continues. The state is the authoritative transaction record; the append-only logical event history repairs an incomplete journal append on restart.

Repeated delegation/continuation requests reuse their dispatch receipt. Restarting after a committed action receipt reuses its observation; local terminal tools can reapply their idempotent state effects. A command interrupted before its receipt is committed may still have partial external effects. Arbitrary shell/network operations do not have an exactly-once guarantee.

## Host-checked decisions

`project_state` exposes the current stage, gates, recent decisions and assignments. `propose_decision` accepts:

- `ADVANCE`: every required current gate must pass. Forward stage skipping is rejected.
- `REVISE`: name the owner and verification condition; remain at the current stage or return to an earlier stage.
- `WAIT_EXTERNAL`: preserve the required input, owner and resumption condition; end execution without polling.
- `STOP`: preserve the result and unmet conditions without calling the objective achieved.
- `ESCALATE`: save a specific unresolved choice beyond current authority.

The default workflow has one protected objective gate and permits ordinary experiment branching. To select the supplied staged templates, use `--workflow research` or `--workflow product`; a custom JSON path is also supported. The selected workflow is pinned into the run contract. These templates are starting structures, not universal scientific protocols. Their criteria and the protected domain evaluator must fit the actual goal before a run starts.

Four gate kinds have deliberately different meanings:

| Gate | What can establish it |
| --- | --- |
| `artifact` | The required submitted file actually exists and its hash matches. This proves delivery, not quality. |
| `evaluation` | A versioned, host-registered evaluator measured that frozen candidate. Optional `accepted` fixes the required verdict. |
| `review` | An authorized reviewer, assigned separately to that candidate revision, cites its receipt or measurement and supplies a scoped judgment. |
| `external` | A trusted operator supplies original files and a scoped verdict through the external-event API or CLI. |

Missing or stale evidence remains `UNKNOWN`. A model review cannot satisfy an evaluation or external gate. Distinct contexts using the same model are not independent experimental reproduction. Final completion additionally requires protected acceptance of the selected candidate; a negative finding can complete a research objective only if the original evaluator was designed to accept that valid answer.

A changed candidate cannot inherit another candidate's gate verdict. Historical measurements remain available for comparison. Review and external evidence are bound to the candidate bundle. The recorded `no_evidence_cycles` and `unchanged_artifact_periods` are mechanical signals for reconsideration, not proof that every changed file is scientifically useful, and they do not impose a hidden effort cap.

## Trusted resumption

A waiting run does not restart merely because the same command is invoked. The operator can supply an event JSON:

```json
{
  "request_id": "dispatch-ID-FROM-PENDING-REQUEST",
  "event_id": "independent-confirmation-001",
  "summary": "Independent execution completed under the recorded conditions",
  "files": {"confirmation.json": "./confirmation.json"},
  "gate_verdicts": {"confirmation-received": "PASS"}
}
```

Pass it with `--external-event event.json` and the same task/workflow/run arguments. Files are relative to the event file. The event must match the pending request; replay is idempotent, and changed contents under the same event ID are rejected. Only external gates accept these verdicts. This API is deliberately unavailable as an agent tool.

An operator can explicitly continue a stopped generic team with `--resume-stopped "reason to continue"`. Its objective, evaluator, implementation, configuration and budget must still match the pinned contract. Changed code or prompts require a fresh run. Existing music evidence is not migrated or rewritten by this implementation.

## Verification and limits

Regression tests exercise checkpoint continuation beyond former step limits in unlimited mode, failure reports, shell-created/binary handoffs, missing and nested inputs, artifact tampering, restart after receipt creation, stale decisions, gate restrictions, external waiting and journal recovery.

```sh
uv run pytest -q
uv run python -m goalagent.checkpoint_check --run-dir runs/checkpoint-verification
```

The second command runs real Docker commands with scripted model decisions. A first candidate removes duplicates, yields a checkpoint, resumes and fails protected comparison. A measured improvement branch inherits the original input, retains duplicates and passes. Restarting adds no model calls. This checks machinery and evidence-driven routing; it does not demonstrate autonomous reasoning, general research convergence, or improved music transcription. The later live checkpoint pilot is described in the operating guide. Further controlled studies, including a single-agent baseline where practical, are still needed to assess research quality.

The [recorded local verification](verification/checkpoints-20261029.json) includes the fixture results, runtime fingerprint and test outcomes.
