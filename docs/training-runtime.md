# Training tools, runtime and observable traces

This implements the first local training increment. All roles still use `Agent`.
`Team` remains the state/event writer. Detached Docker containers own process life;
the training service observes them and commits job changes through Team events.
It does not import experiment code or run it on the host.

See [the Korean implementation/results report](training-runtime-results-ko.md) for
the actual learning outcome, failures found and measured scope.

The subsequent [actual-agent study](fashion-live-results-ko.md) replaces scripted
decisions with real provider calls, agent-authored training code, validation-driven
model selection and separate role reviews. Run `python -m goalagent.fashion_live
--run-dir tmp/NEW-LIVE-STUDY` to start a fresh bounded study; this consumes provider
usage and restricts architecture selection to a reviewed declarative MLP/CNN registry.

Direct job output publication and typed report input are described in
[handoff/report interfaces](handoff-report-input.md). Their
[actual-agent comparison](handoff-comparison-results-ko.md) found less manual
Engineering packaging and no missing report-field errors, but no reduction in
overall calls or repeated reading. It records both improvements and remaining gaps.

[Actual-agent recovery validation](recovery-results-ko.md) exercises an externally
killed training container, invalid input dimensions and nonfinite loss. The source
and replay guide are in research/recovery/; these bounded seeded incidents do not
establish generic recovery from arbitrary failures.

## Order and file ownership

Define contracts first, implement the runtime and tracing together, verify CPU
lifecycle/file boundaries, validate CUDA/backpropagation, then exercise a complete
learning/checkpoint/evaluation fixture. Logs are needed before the first failure.

| Change | File |
| --- | --- |
| Profile grants, jobs, datasets, model references and registered adapters | `goalagent/training.py` |
| Streaming immutable binary storage | `goalagent/large_store.py` |
| Container timeout, bounded logs and child privilege drop | `goalagent/job_supervisor.py` |
| Observable spans, redaction and HTML export | `goalagent/tracing.py` |
| Model/tool boundary instrumentation | `goalagent/agent.py` |
| Job waiting and continuation through existing work IDs | `goalagent/stage_runtime.py` |
| Opt-in role prompts/tool grants | `agents/training/` |
| CUDA environment and actual package snapshot | `environments/training-cuda/` |
| Fixed learning/inference fixture | `goalagent/fashion_train.py`, `fashion_model.py`, `fashion_check.py` |

## Enable tools and approve a profile

Default roles retain their original tools and synchronous CPU execution policy.
Select `agents/training` explicitly for the new grants, and include owner-controlled
`training.profiles` in the task. A profile must use an immutable image digest/ID:

```json
{
  "training": {
    "max_blob_bytes": 8000000000,
    "profiles": {
      "gpu": {
        "image": "sha256:REPLACE_WITH_REVIEWED_64_HEX_IMAGE_ID",
        "gpu": "all", "memory": "8g", "cpus": 4,
        "max_seconds": 900, "max_output_bytes": 500000000,
        "roles": ["experiment_engineer"]
      }
    }
  }
}
```

The placeholder is intentionally invalid until replaced. Roles cannot change this
profile through a prompt. `memory` limits system RAM, not VRAM. The initial single
GPU path serializes starts across ResearchSquad runs using a host lock plus active
Docker labels. It does not reserve the GPU against unrelated applications.
This is exclusion, not a resource queue: a concurrent start returns `GPU_BUSY`.
Wait for the active job and explicitly issue a new attempt; reserved uncertain
dispatch keys are not automatically replayed.

`training_catalog` returns profiles and public registered references, not private
host paths. `register_dataset` streams explicit workspace files into the run-local
store; its source paths cannot escape that workspace. The trusted owner API can
also register selected files before the run. It does not automatically discover,
license or judge a dataset. Publish training labels; keep protected test labels
outside the worker data registry.

## Job and checkpoint tools

`start_job` accepts `{profile, code_files, entrypoint, args, dataset_ids,
resume_model?}`. Python source is frozen in a separate directory, mounted read-only.
The job sees `/datasets/DATASET_ID/`, `/checkpoints/resume` when supplied, and a
writable `/workspace/output`. No project checkout, host environment or Docker
socket is handed to it. Networking is disabled for these training jobs.

`job_status` observes Docker state, exit/OOM information, bounded logs and output
inventory. `read_job_output` reads bounded UTF-8 output with parent-directory and
final-file link protection, even while the job is running. These are experiment
reports, not independently verified accuracy.

`await_job` yields a managed assignment. The host observes completion without
model-call polling, then continues the same assignment and work ID. Other ready
work can run while waiting. A closed Team process does not kill the detached job;
the supervisor's finite time budget still applies. On reopen, Docker state is
observed before further action. An ambiguous start is never blindly repeated.

`cancel_job` stops an owned job and retains already completed files. It does not
force arbitrary training code to create a fresh checkpoint. Root coordinators
with the tool grant may also inspect/control jobs in their own Team.

`register_model` freezes an exited job's output as a `model` or `checkpoint`.
Large content stays outside the 16MB/64MB text-artifact protocol; small IDs and
metadata can be handed to subsequent assignments. References are checked before
mounting or evaluation. Automatic snapshots do not implicitly back up large files.

`resume_job` creates a new attempt from the same frozen source/profile/data and a
parent checkpoint. Experiment code must restore the correct state. Changed args
and a checkpoint alone do not prove equivalent continuation. The Fashion fixture
restores model, Adam, epoch/step, CPU/CUDA RNG and deterministic sample ordering;
it verifies epoch-boundary equivalence, not arbitrary frameworks or mid-batch resume.

`job_started` and `job_completed` report records distinguish starting work from
observing a successful terminal job. A RUNNING/start receipt cannot prove completed
training. Failed runs remain failures even if their status query itself succeeded.

## Independent evaluation

`evaluate_model` names a maintainer-registered, versioned adapter. Register adapters
through `Team(..., model_evaluators=...)`; agents cannot nominate evaluator source.
The base CLI does not automatically load arbitrary model classes or plugins.

The included Fashion adapter mounts a fixed trusted architecture/inference script,
saved safetensors and private official test inputs in a separate restricted CPU
container. It never imports the training job's Python. Test source identity is
checked and results bind to immutable model IDs and adapter versions. Project
completion still needs the configured workflow's reviews and protected predicate.
The fixture's reference evaluator connects this model verdict to the existing gate.
Other model architectures need their own reviewed loader and scientific predicate.

## Trace interface

```sh
python -m goalagent.tracing --run-dir runs/your-run --output trace.html
```

The local standalone HTML view shows parent/child spans and supports filtering by
agent, tool, job, stage or error. A synchronous child links to its actual delegate
call. Host-managed dispatch is a host operation, not an invented LLM delegation.

Each model span stores the effective system prompt, logical context/messages,
actual combined provider prompt, image reference, available tools, selected action,
public `why`, usage/model metadata and error. The current CLI adapter transports one
combined prompt, not a persistent chat session. Context truncation is visible in
the exact request. A tool span stores arguments, results, errors and causal links.
Host events also enter the trace. Terminal job logs are retained beside the job.

`record_decision` records a concise supplied summary and explicit candidates
`{kind,target,status,reason}`. Available tools are permissions/options; they are not
evidence that the model considered each one. Unreported alternatives stay unknown.
Hidden chain of thought and raw provider reasoning events are not copied into this
trace. `COMPLETED` means a span returned; inspect its result for experiment success.
An unmatched RUNNING span after a crash means unfinished/unknown, not confirmed live.

Known credential fields/token patterns are redacted in new traces and exports.
This is not a complete secret detector. Existing raw provider/run files retain their
own behavior and may contain project data. Traces stay local; sharing an export is
a separate deliberate action. The viewer is a first local debugger, not a hosted
LangSmith service, streaming dashboard or high-volume trace database.

## Verify

```sh
uv sync --locked --group dev
uv run python -m goalagent.training_check --run-dir tmp/new-lifecycle-check
docker build -t researchsquad-training:torch2.9.1-cu128 environments/training-cuda
uv run python -m goalagent.fashion_check --run-dir tmp/new-fashion-check
```

Use fresh directories after code/config changes. The CPU fixture uses actual
containers for detached recovery, cancellation, deadline enforcement and a 20MB
artifact. The Fashion fixture uses scripted choices/reviews through the same Agent
and real GPU learning. It is a one-seed, fixed-architecture machinery check, not
evidence of autonomous research or a fair comparison against a single agent.
The build records resolved packages; runtime approval pins the resulting image ID.

## Practical limits

Storage is run-local; cross-run deduplication, garbage collection and retention UI
are not implemented. Output bytes are monitored periodically, not a hard disk quota;
a rapid writer can overshoot. GPU VRAM quotas, reliable utilization telemetry,
remote/distributed jobs and total cross-run GPU-hour budgeting are not implemented.
Third-party task cancellation and generic optimizer/RNG restoration are not inferred.
Owner intervention is required for LOST/START_UNCERTAIN cases. Finite job deadlines
are separate from model-call/Team effort limits. Native Windows execution remains
unsupported: use Linux/WSL with Docker.
