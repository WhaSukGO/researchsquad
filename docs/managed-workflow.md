# Configuring and operating the managed team

Managed workflows preserve the four-perspective team's mandatory responsibilities
while reusing ResearchSquad's one `Agent` class, role JSON/Markdown, tool registry,
Docker workspaces, checkpoints and protected evaluators. `policy_version: 2` opts
into host dispatch. Custom workflows without that field retain the synchronous
coordinator-directed interface.

## Repaired runtime interfaces

The [current TODO](TODO-ko.md) and [runtime repair verification](runtime-reliability-results-ko.md)
track the source-study findings. Same-assignment reading coverage is now available
in `observed_work`, separate from the six recent action bodies. `read_file` preserves
its bounded text in the next model context and returns total `bytes`, window
`returned_bytes`, `end_offset`, `next_offset` and `eof`; advance by `next_offset`,
not the total file size. PNG/JPEG/GIF/WebP must use `view_image`.

`checkpoint` optionally accepts `checks: [{id, description, status, evidence_ids}]`.
Statuses are pending/passed/failed/unknown; completed checks require evidence, and
passed checks cannot cite failed actions. Checklist entries persist when a later
checkpoint omits them. These are agent-reported checks, never automatic gate votes.
They and observed_work are local to the assignment, not a cross-run memory feature.

`report_context.objection_targets` lists delivered paths and their canonical IDs.
`target_id` can use one of those paths (optionally `:section`); the host resolves it
only against delivered material and records the resolution in the tool receipt.
Unknown paths still fail. `files` contains authored outputs only; inputs and
baselines are already preserved. A reviewer's own recorded review event can support
a document claim of their verdict, never an empirical experiment claim. Peer
review conclusions remain isolated.

Atomic JSON writes retry only transient replacement errors for a bounded interval
with unique temporary files. Exhaustion before a provider call produces a known
`storage_blocked` boundary, rolling back the unused reservation. After a trusted
storage-restored event, managed work continues the same assignment and checkpoint.
This does not auto-repeat uncertain commands or migrate changed run contracts.
Other failure boundaries keep their existing recovery requirements.

JSON and artifact content publication pin one parent directory descriptor for
temporary creation, replacement and cleanup. This prevents two absolute lookups
from crossing mount instances during a same-directory mount transition. EXDEV
does not trigger a copy fallback. See [the R12 reproduction](r12-publication-results-ko.md)
for actual mount-race checks and the distinction from the unrecorded historical trigger.

Registered `Evaluator.preflight(snapshot, task)` may provide mechanical checks
before full reviews; returning None skips that stage. An explicit false verdict
sends the owner for correction before reviewers run. The receipt is input to full
reviewers, not report-only readers, and cannot populate final acceptance. The
source-study adapter uses this for immutable fetch/read provenance; semantic
attribution review and protected final evaluation are still required.

## Start with the file that owns the change

| Desired change | Edit |
| --- | --- |
| Change a role's judgment or required explanation | `agents/default/ROLE.md` |
| Change its model, tool grants or individual effort limits | `agents/default/ROLE.json` |
| Require a stage owner, reviewers, outputs or actual actions | `workflows/research.json` or `workflows/product.json` |
| Change ready-work selection, dependency or retry rules | `goalagent/workboard.py` |
| Change mandatory dispatch and review/rework transitions | `goalagent/stage_runtime.py` |
| Change report fields or receipt assertions | `goalagent/reports.py`, `goalagent/claim_checks.py` |
| Add a trusted host capability | Register a handler in the existing tool registry, then grant it |
| Add a scientific success test | Register a versioned maintainer-owned evaluator and input adapter |

`goalagent/team.py` connects these components and remains the single writer.
`goalagent/agent.py` runs the common action loop; it does not encode professions or
product/research stage ownership. Adding a role does not need a new Python class.

## Run a small example

On Linux or WSL, install locked dependencies and prepare the pinned image:

```sh
uv sync --locked --group dev
docker pull python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f
uv run python -m goalagent.managed_check --run-dir tmp/managed-check-01
```

The last command uses scripted decisions and real Docker. It deliberately drops a
duplicate, obtains a failed protected measurement, improves the same work item,
repeats independent reviews and obtains acceptance. A completed run adds no model
calls when reopened. Use a new directory for a new check or changed contract.

For actual model decisions under the configured provider login:

```sh
uv run python -m goalagent.team --task goals/managed-sort.json --run-dir tmp/managed-live-01
```

This consumes provider usage. It is a small software fixture, not an OMR benchmark
or evidence that multiple agents improve research quality. Omit `--model` to use
the configured provider model, or select one explicitly.

## Role definitions remain ordinary configuration

The existing role schema names an ID, model, reasoning effort, Markdown prompt,
tool grants, limits and checkpoint interval. A missing tool handler or unknown
grant fails at startup. A prompt cannot create permission. `--agents-dir` selects
a complete role directory; include the coordinator and the workflow's bound roles.

Managed stage definitions add these fields:

```json
{
  "mode": "research",
  "policy_version": 2,
  "role_bindings": {
    "engineering": "experiment_engineer",
    "research": "researcher",
    "auditor": "critic",
    "environment": "environment_engineer"
  },
  "work_policy": {
    "max_attempts": 3,
    "checkpoint_interval": 8,
    "coordinator_checkpoint_interval": 1
  },
  "stages": [{
    "id": "R3",
    "description": "Execute the environment and pilot checks",
    "owner": "engineering",
    "required_reviewers": ["research", "auditor"],
    "required_outputs": ["pilot-report.md", "trace.json"],
    "required_tools": ["run"],
    "gates": [{
      "id": "pilot-measured",
      "kind": "evaluation",
      "criterion": "A valid protected pilot measurement exists"
    }]
  }]
}
```

These fields are implemented. The fragment demonstrates R3; use a suitable full
workflow and a registered evaluator for a real project. An evaluation gate without
`accepted: true` requires a measurement, including a valid negative one; it does
not require the objective to have succeeded. Full project completion still requires
protected acceptance of the selected submission.

Each `required_reviewers` entry becomes a separate gate and separate assignment.
Putting several names in one ordinary gate's `reviewers` field still means any
one authorized reviewer, not all of them. Owners and required reviewers are checked
against configured roles and grants before model calls.

The shipped research/product templates preserve the previous team's owner and
specialist matrices. The final stage also requires the report-only reader. R1
requires real web-search/fetch receipts; its task must permit networking. Candidate
names are domain configuration: the music wrapper requires HOMR/Audiveris decisions
at R1, while the generic research template does not hardcode OMR software.

## One scheduler and stable work identity

The host creates missing mandatory work before asking the coordinator what to do.
Managed `delegate` returns `QUEUED` and a work ID; it does not synchronously run a
child. The coordinator yields after its configured action period. The same host
scheduler then selects ready work. Execution remains sequential.

The work board records objective, owner, inputs, required tools/outputs, acceptance
check, dependencies, blocking flag, feedback and all assignment attempts. It lives
inside `team-state.json`, not a second database. Events use `Team.event`.

* **Work ID** identifies the problem, such as tracing a duration discrepancy.
* **Assignment ID** identifies a frozen attempt and its workspace/policy.
* **Checkpoint continuation** keeps that assignment, workspace and counters.
* **improve** requires a measured parent, including an inaccurate result.
* **debug** requires a failed/blocked parent.
* **revise** requires a submitted parent with a registered failed review or host
  required-action check. It handles document rejection without pretending an
  experiment was measured or failed to execute.

Saving code, running it and inspecting output are steps of one job. A measured
same-stage revision keeps that work ID and creates an improve attempt. Every new
submission repeats all required reviews and candidate-bound checks. Completed
receipts are reused only for recovery of the same unchanged submission.

Ready blocking predecessors/environment work run before ordinary owner work;
required reviews follow submitted work. Nonblocking proposals are recorded but
do not automatically run beyond scope. Dependencies cannot form cycles.

## Submit results, missing work and candidate decisions

Continue using `submit_report`. Managed claims require `scope: document` or
`scope: empirical`, alongside the existing epistemic status and evidence IDs.
Optional `execution_records` contain `action`, `target` and `evidence_ids`. A
searched/read/executed assertion must match successful receipts by that assignment
and their recorded target. A supplied URL is not an executed search.

Typed work requests have this shape:

```json
{
  "existing_work_id": "",
  "owner": "engineering",
  "objective": "Instrument raw-event to geometry assignment for event 13",
  "input_artifact_ids": [],
  "required_tools": ["run"],
  "acceptance_check": "Execute the trace and establish identity or preserve ambiguity",
  "blocking": true
}
```

An empty input list inherits the source's registered result artifacts. Refer to an
existing W-ID for the same work. A missing capability routes to a capable role or
an explicit external operator. `next_actions` remain proposals rather than a second
dispatch path. MAJOR/BLOCKER objections create resolution work and return the source
submission for revision; the label itself is not proof of the objection's truth.

`candidate_decisions` record candidate, SELECTED/REJECTED/DEFERRED/UNTESTED, reason,
evidence IDs and followup action. Deferred/untested candidates require a concrete
next action. Selecting a method for study does not identify a measured winner.
Required candidate omissions return the owner for rework.

Public search is transport, not guaranteed access to results. A known bot challenge
is reported as `access_blocked` even if HTTP and the container command succeeded;
it cannot satisfy the required successful search action. Each response keeps its
own source file and readable text file. Fetch a known official source where useful,
or create concrete work for another authorized search provider or original operator
material. An unavailable provider remains an explicit limitation, not an exhaustive
search claim. The current default search provider is public DuckDuckGo HTML.

Receipt matching constrains unsupported claims; it does not establish that arbitrary
prose follows semantically from a citation. Protected measurement and specialist
review remain necessary.

## Reviews and the report-only reader

A separately assigned reviewer calls `review_gate` for its exact gate and candidate,
then submits its report. Failed review returns the original work to its owner with
the actual resolution condition. Other pending reviews of an obsolete submission
are superseded. Reviewers receive no peer conclusions in their automatic context;
peer-review evidence/artifacts are also denied through host lookup tools.

`report_reader` has a restricted configuration. A stage specifies:

```json
{
  "required_reviewers": ["auditor", "report_reader"],
  "review_scopes": {"report_reader": "report_only"},
  "report_paths": ["report.md"]
}
```

The host hands that reader only the listed submitted report files and opaque
candidate metadata. It does not inherit original inputs, code, global evidence,
other reviews or project history. Its tools cannot fetch those records. This checks
comprehension and presentation, not independent experimental truth.

## Missing environments and external material

An experiment engineer's `request_environment` creates a blocking environment job.
The environment engineer proposes the existing controlled recipe/readiness test;
the host builds and checks it. A ready receipt wakes the original work as a new
debug attempt with the new image. Old assignments keep their frozen image.

Missing original data instead records a named owner and exact resumption condition.
Once independent ready work is exhausted the run waits; it does not poll or invent
observations. Supply original material through the existing operator external-event
interface. A purely external work item additionally requires an explicit PASS for
its W-ID in `gate_verdicts`; an upload alone does not silently close it.

Effort limits remain finite unless explicitly made unlimited. Setup usage is
recorded separately but remains part of global active time. A checkpoint interval
is a scheduling cadence, not another total research budget.

## Music entry point and acceptance

```sh
uv run python -m goalagent.music_team --run-dir tmp/music-managed-01
uv run python -m goalagent.music_team --run-dir tmp/music-charter-01 --completion-stage R0
```

The new defaults select the managed research workflow, all 32 development samples
and finite 80-call/one-hour effort limits. `--sample-scope first_per_song` explicitly
selects the seven-sample pilot; it cannot complete the original 32-sample objective.
The wrapper now forwards `--agents-dir`, `--workflow`, `--external-event`,
`--resume-stopped`, `--retry-action` and `--retry-reason`. `--unlimited` is explicit;
the older implicit unlimited default is intentionally changed for new runs.

The submission interface remains the existing editable `sample-NNN.krn` melody and
harmony format. MusicXML conversion is work for the configured engineers; this PR
does not add a new recognizer or change event-alignment metrics. Missing/unparseable
outputs retain the full selected reference denominators in protected scoring.

Final `chord-timing-audit` and `musician-review` verdicts must be trusted original
operator events for the same frozen candidate. A maintainer-owned finalizer combines
them with unchanged numeric criteria; neither can override bad scores, coverage or
transposition failures. Base measurements remain immutable. A new acceptance receipt
records the scoped external evidence instead of rewriting the original measurement.
When an operator changes a verdict, cached acceptance is invalidated and current
goal acceptance is recomputed; historical positive receipts remain historical.

## Scope, recovery and compatibility

`--completion-stage R0` explicitly completes only a reviewed charter scope. The
reported `goal_met` remains separate; partial completion does not claim OMR success.
Changing the pinned goal, original inputs, prompts, grants, evaluator, host code or
policy requires a new run. New experiment code, derived artifacts and prepared
images within the existing contract remain work inside the run.

Managed execution reserves unsafe actions. A committed action receipt is reused.
If external execution may have happened without a completion receipt, the runtime
waits instead of blindly repeating the command. After inspecting effects:

```sh
uv run python -m goalagent.team --task goals/managed-sort.json --run-dir tmp/managed-live-01 \
  --retry-action ASSIGNMENT_ID --retry-reason "Effects inspected; safe to repeat"
```

This operator interface is not a model tool. It prevents automatic ambiguous replay,
not arbitrary external exactly-once effects. Native Windows POSIX-bound execution,
GPU/remote provisioning, parallel scheduling and scientific-quality guarantees are
outside this change; use Linux/WSL and Docker.
