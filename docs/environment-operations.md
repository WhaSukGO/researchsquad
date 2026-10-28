# Prepared research environments

The environment and input-handoff design is implemented as an opt-in research mode. Old goal files keep their existing behavior; old recorded results are not migrated or rescored silently.

Run a new session:

```sh
docker pull python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f
uv run python -m goalagent.coordinator --goal goals/music-research-v2.json --run-dir runs/my-v2-research --model gpt-6-astra
```

Use the same command to resume. Use a new run directory if the goal, protected code, environment profile, locked base requirements or acceptance criteria change. Do not edit those while a run is active.

## Who owns what

The research lead selects the experiment and declares required prediction artifacts. The experiment engineer implements the recognition intervention in a prepared environment. The environment engineer proposes package changes only when requested or when readiness fails. The host validates and builds the recipe, runs readiness tests and owns the registry. The protected evaluator still reads labels and scores frozen outputs.

The environment engineer has a structured package-proposal interface, not host shell access. It cannot change the pinned base image, the fixed readiness test, evaluator code, or label permissions. This initial implementation supports package-based additions to the reviewed Python/notation/OCR profile. It does not automatically author arbitrary Dockerfiles, provision GPUs, install arbitrary downloaded model bundles or promise an Audiveris runtime. Such capabilities need a reviewed profile and an appropriate end-to-end readiness test.

## Inputs are a contract

Every managed assignment includes:

```json
{
  "mode": "explore",
  "parent": null,
  "approach": "A specific recognition intervention",
  "objective": "A distinct local task, not the overall goal",
  "success_criteria": "Measurable output and comparison requirements",
  "required_inputs": ["baseline:audiveris-enlarged"],
  "environment": "music-python"
}
```

The dataset inspection tool returns an artifact catalog. Declared baseline predictions must exist, be nonempty and pass hashes before dispatch. The host copies only allowlisted prediction artifacts from the benchmark directory, including original model exports when available. It never searches reference labels as a fallback. The assignment contains an inventory and checksums. The baseline directory is mounted read-only and checked again after execution; source snapshots cannot overwrite it.

The host validates declared dependencies, not the semantics of arbitrary prose. A lead that fails to declare an implied dependency can still make a poor assignment. The prompt explicitly requires declaring predictions when preserving baseline melody; complete semantic enforcement is not claimed.

All supplied labels remain available to the evaluator. Supervised training access is not added by this change; it requires a separately declared training split. The existing development set is not a held-out evaluation set.

## Environment reuse and readiness

The reviewed profile provides Python, Pillow, music21, converter21, Verovio and Tesseract. The base image is digest-pinned; base Python requirements are exported from the project lockfile with hashes. Additional Python requirements are exact-version pins. Resolved Python and Debian package versions are captured with the immutable resulting image identity.

The registry key covers the recipe, base dependency lock, platform, smoke-test contents, sandbox code and relevant resource policy. Cache reuse checks the image identity and resolved-lock checksum. A changed key or missing image/lock cannot silently reuse readiness. A published image is reused while each experiment gets a separate writable workspace.

Readiness runs in a fresh container with the same non-root user, read-only root, no network and resource limits as experiment commands. It checks writable temporary storage, a real synthetic MusicXML-to-kern export, nonempty notes parsed from the exported kern, and OCR on synthetic chord text. No research images or labels are used. This proves these capabilities execute; it does not prove transcription accuracy or Audiveris functionality.

The base dependency lock is reproducible. Debian package requests and newly added transitive dependencies can still resolve differently when rebuilding after registry/package changes; the resolved lock and image ID disclose that. Image reuse is immutable, but byte-for-byte reproducible rebuilds of every future package change are not claimed. Preserve/export the built image if long-term offline reconstruction is needed.

## Setup budget and escalation

The v2 goal allows 3 setup attempts, 2 environment-engineer model calls and 900 setup seconds, all within the same 80-call / 3,600-second total research budget. The four scientific experiments are a separate limit.

A failed setup before an experiment engineer starts returns `environment_blocked` and releases that scientific experiment reservation. It produces no fake accuracy result. Setup attempts and calls are reserved before execution and recorded durably. Interrupted setup time is conservatively charged on recovery.

An experiment engineer can use `request_environment` to report a missing dependency and stop. Work already dispatched remains a scientific experiment, with its partial source and failure evidence retained. The lead can use `prepare_environment` to request a bounded package repair, then assign a new experiment or choose another approach. The engineer does not continue quietly installing packages.

Network access is disabled for managed experiment commands, system packages are read-only, and package installation is disabled in the prepared environment by default. This is an execution boundary, not a claim that a Python process can never write code: locally generated modules and scripts remain allowed. A writable workspace is necessary for experiments.

## Durable evidence and context

Every run records setup attempt/call counts, active setup time, image and lock identity, readiness receipts and cache hits. Build recipes, build logs, smoke logs and resolved locks are copied from the registry into run-owned artifacts. Full output stays on disk; receipts return the first diagnostic and a bounded tail. The environment engineer sees the request and compact failure evidence, not the research conversation or labels.

The existing experiment seals now include the environment receipt. Changes to protected code or profile inputs require a new run. Pending actions retain the existing durable replay behavior; shell/build side effects are not guaranteed exactly once after process death. A successful readiness receipt can be reused after a crash without rerunning model decisions. Existing completion checks remain unchanged.

## Verification

Unit tests cover missing-input rejection, label exclusion, read-only baseline handoff, setup capacity, context boundaries, cache invalidation, package-input validation and bounded diagnostics. Docker tests verify isolation and protected scoring. A live research rerun must additionally report parseability, melody/chord error, model calls, setup time and reuse.

A fresh research session means a new state directory, new assignments, no inherited experiment workspaces, and no previous session's conclusions in the prompt. It can still use the same declared benchmark and a prepared image. Report Docker layer/image cache warmth explicitly, and separate cold validation/build cost from reuse cost. One old run and one new run are a diagnostic comparison, not a controlled causal ablation.
