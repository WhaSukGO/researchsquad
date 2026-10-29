# Research environment operations

The configurable team separates experiment work from environment preparation. The experiment engineer implements the candidate; the environment engineer proposes missing capabilities; the host validates and builds a Docker image. The protected evaluator measures the submitted candidate independently.

## Start and reuse the music environment

```sh
uv run python -m goalagent.music_team --run-dir runs/my-music-team --model gpt-6.1-sol
```

Music runs default to unlimited research effort. Startup first tries the reviewed `environments/music-python` profile. It provides Python, Pillow, music21, converter21, Verovio and Tesseract. Audiveris is not installed; existing predictions and raw exports are supplied as inputs.

This deterministic bootstrap does not call a setup model. Its operational readiness attempt remains bounded to 180 seconds; failure is recorded and the team can delegate environment work. That readiness timeout does not restore a total research budget. A reusable profile receipt lives under `.cache/research-environments`, and each run keeps its own copy of the build/readiness evidence.

Verify the reviewed profile without live model calls:

```sh
uv run python -m goalagent.environment_check --run-dir runs/environment-verification
```

The check exercises synthetic export, parsing and OCR, then independent command workspaces using the same immutable image. It does not use research labels or establish transcription accuracy.

## Ask for additional capabilities

An experiment engineer calls `request_environment` with the missing capability and observed failure. The assignment returns `environment_blocked`, preserving its work. The coordinator can delegate a distinct setup assignment to the configured environment engineer, then start a new engineering assignment with the prepared environment and relevant inherited artifacts. Continuing an existing assignment does not change its frozen execution policy.

The generic environment engineer can write a synthetic smoke script and call `prepare_environment` with:

```json
{
  "system_packages": ["tesseract-ocr"],
  "python_packages": ["Pillow==11.3.0"],
  "smoke_script": "smoke.py"
}
```

These values illustrate the interface, not a complete music environment. Include the packages actually needed by the capability under test. The host fixes the base image, validates package syntax, builds an isolated context and executes the smoke script. The build never mounts the project, reference data, host credentials or Docker socket. The proposed smoke test proves execution of that capability; it is not a replacement for protected evaluation.

The generic cache is run-local. A successful receipt and immutable image can be reused by later assignments; Docker layers may also accelerate a fresh run. Unlimited mode removes the generic build-attempt cap. Full logs stay on disk; returned observations contain the first diagnostic and a bounded tail.

## Protect inputs and image identity

The music adapter reads preserved predictions from `research/baselines/first-benchmark`, not generated `runs/` output. The provenance manifest records their original paths and hashes. The supplied reference labels remain in `research/data` and are read only by the protected scorer. The adapter delivers seven images and fourteen prediction/export artifacts to the coordinator; downstream engineers receive only explicitly delegated inputs.

Task assets are pinned by hash. Handoff manifests record actual files and their provenance; required inputs must exist before dispatch. Agent file tools cannot write input or baseline directories. Docker mounts assigned inputs read-only, mounts only that assignment's workspace, and provides no host Docker socket. Prepared experiment commands run without network. Research roles can use network tools only when the task and their role grants permit them.

Each build receives a unique retained image tag and records its immutable image ID. A later build does not move the tag keeping a previously assigned image available. Reuse verifies readiness receipts, image identity and captured dependency locks. The reviewed-profile key also covers the recipe, dependency lock, platform, synthetic smoke test, sandbox and relevant resource policy.

Dependency resolution during a future rebuild may differ for system packages or transitive additions. The resolved lock and image ID record what actually ran; byte-for-byte reproducibility of every future rebuild is not claimed. Automatic image garbage collection is not implemented.

## Read the evidence

Inspect the run's `bootstrap/` records for reviewed-profile setup, `environments/` for generic preparation, and each assignment's `execution-policy.json` for the image it actually received. Shared evidence and the environment catalog expose compact receipts to the coordinator. See the [operating guide](multi-agent-operating-guide.md) for the complete record map.

Use a fresh run when changing code, the goal, role prompts, the environment profile or acceptance checks. A fresh research run uses new state and assignments; it may legitimately reuse a declared baseline and prepared image. Report cache warmth and setup time separately from research accuracy.

The earlier opt-in coordinator workflow and its reports are historical. Their source, commands and tracked evidence are preserved in the [pre-cleanup archive](repository-cleanup.md); they are no longer active entry points.
