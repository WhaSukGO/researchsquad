# Goalagent: an evidence-driven research coordinator

New research runs use a coordinator with independent coding workers and a protected
music evaluator. The coordinator gives each worker a specific objective and chooses
whether to explore a new approach, improve a measured candidate, or debug a failed
candidate. Workers write and execute scripts in Docker; experiments are no longer
limited to a hardcoded recognition menu. Existing controller and blind-review runs
remain supported by their original commands below.

## Human feedback and proposed improvements

Use the [PR review workflow](docs/pr-review-workflow.md) to discuss and revise changes. The [environment and handoff proposal](docs/design/environment-and-review.md) responds to issue #1; its initial implementation is documented in [environment operations](docs/environment-operations.md).

## Prepared environments and explicit input handoffs

The follow-up implementation is available with `--goal goals/music-research-v2.json`.
See [environment operations](docs/environment-operations.md) for input contracts,
readiness checks, environment-engineer escalation, budgets and current limitations.
Use a new run directory; existing run evidence and acceptance rules are preserved.

## Run the research coordinator

Start Docker, then prepare the pinned execution image and run:

```sh
docker pull python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f
uv run python -m goalagent.coordinator --run-dir runs/my-research
```

The coordinator and workers use the existing authenticated Codex provider. `--model`
selects the model for both roles. `--goal` selects a goal contract; the default is
[music-research.json](goals/music-research.json). `--objective` changes the natural-language
objective within this music evaluation contract. Use a new directory when changing
the goal, budgets, model, worker policy or evaluator.

Run the same command to resume. `--stop-after 4` checkpoints after four coordinator
tool completions; remove the option to continue. Completed worker submissions and
evaluations are reused. A pending worker action resumes without asking the model to
choose it again. Shell actions interrupted before their receipt is committed can be
replayed; execution and external network effects are not guaranteed exactly once.

The default budget is 24 coordinator decisions, four experiment branches, 80 total
model calls and one active hour. Each worker gets up to 16 decisions and ten minutes,
with a two-minute command timeout, 2 GB RAM and two CPUs. These are ceilings, not a
promise that all branches will fit. All worker calls also consume the global budget.
The default research policy enables networking for public code, packages, datasets
and model downloads; set `worker.network` to `false` for offline runs. No host
credentials or environment variables are passed to command containers. This default
CPU image does not provide GPU access; larger models need an appropriate runtime
and explicitly configured resources.

## How research improves an approach

1. Inspect the dataset, baseline measurements and starting-source evidence.
2. Assign a worker a local objective, method, hypothesis and measurable deliverables.
3. Let the worker write files, run scripts, inspect images and investigate failures.
4. Freeze predictions and source/config files outside the worker workspace.
5. Score the frozen predictions using the protected evaluator.
6. Compare measured results and choose an older or newer parent to improve, debug a
   failure, explore another method, or stop with a supported outcome.

`explore` creates a root; `improve` requires an evaluated parent; `debug` requires a
failed parent. Identical assignments and repeated local objectives are rejected.
Children inherit their parent's submitted source/config snapshot and compact feedback,
not its entire model conversation or reference labels. Successful experiment execution
must be evaluated before assigning another worker. Failed branches can be debugged
without first pretending they have a meaningful accuracy score.

Workers are independent model loops with separate workspaces, goals and contexts.
The scheduler currently executes them **sequentially**, so branches can be compared
within the existing global budget. Parallel worker scheduling is not implemented.
The system improves candidate implementations and preserves experimental knowledge;
it does not automatically train the coordinator's underlying model.

| Responsibility | Input and authority |
| --- | --- |
| Coordinator | System goal, observed evidence, compact experiment tree; assigns work and selects branches |
| Experiment worker | Specific assignment, supporting evidence, anonymized images, optional parent code and aggregate feedback; writes and runs new approaches |
| Runner | Owns budgets, Docker policy, durable state, artifact sealing and completion decisions |
| Protected evaluator | Reads sealed predictions and reference labels; computes fixed metrics without running worker source |

Workers can install Python dependencies into `/workspace/vendor`, create a virtual
environment, fetch public repositories or weights, and implement arbitrary new scripts.
They do not receive a Docker socket or permission to choose host mounts. All command
execution uses the host's configured container image and resource policy. The input
image mount is read-only. Reference labels, evaluation code, model-provider credentials,
run state, receipts and full command logs are outside the mounted worker workspace.
Host-side file operations reject traversal, symlinks, hard links, devices and oversized
artifacts. Containers are removed after commands and orphaned run-owned containers
are removed when resuming. The model provider remains tool-disabled; returned actions
are executed only by the runner.

## Evidence, context and evaluation

Each run contains:

- `state.json`: durable coordinator state, budgets, history and pending action.
- `experiment-tree.json`: lineage, assigned goals, execution state, measurements and
  deltas from parents (negative error-rate deltas mean improvement).
- `evidence/index.json` and content-addressed step records: hypotheses, citations,
  observations and failed attempts, retained across resumes.
- `experiments/<id>/assignment.json`: the explicit worker contract.
- `experiments/<id>/worker/`: worker checkpoints, model receipts and full command logs.
- `source-snapshot.json`, predictions, `seal.json` and the experiment receipt: frozen
  artifacts used for reproducibility and branching.
- `evaluation-contract.json` and per-experiment evaluation attestations: hashes of the
  goal, data manifest, baseline, scoring code/dependencies, predictions and score cache.
- `report.html`: a readable experiment tree and comparison table.

The coordinator receives eight recent observations plus compact branch metrics; workers
receive six recent action receipts plus their assignment. Command output goes to disk,
with at most a 4,000-byte tail returned to the worker. Large files can be read in bounded
windows. The coordinator's `read_record` action retrieves older evidence in pages.
There is no automatic sharing of raw conversations or automatic cross-run memory import.

The local curated source catalog is a starting point, not live web search. Workers can
retrieve additional public resources through network-enabled commands. Such content is
evidence and cannot grant new permissions. Research claims and worker self-reports do
not count as measured accuracy.

The evaluator checks seals even on cached reads and the runner rechecks them on resume
and before accepting a selected result. A changed scoring contract requires a new run;
legacy evaluation-correction forks are not an automatic migration path for research
runs. The existing completion predicate is preserved: all 32 samples, parseability,
zero measured melody/chord errors, successful transposition checks, audited timing and
musician acceptance. The current seven-sample development pilot and evaluator's false
timing/human-review flags still prevent full-goal success. There is no new held-out
generalization claim or evidence that multiple workers improve recognition accuracy yet.

The implementation borrows experiment lineage from
[AIDE](https://github.com/WecoAI/aideml) and
[AI Scientist-v2](https://github.com/SakanaAI/AI-Scientist-v2), distinct assignments from
[multi-agent research systems](https://www.anthropic.com/research/multi-agent-research-system),
and persistent experiment/evidence records from
[R&D-Agent](https://github.com/microsoft/RD-Agent) and
[ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep).
It uses these architectural patterns without introducing those frameworks as dependencies.

Verify control flow and real container execution:

```sh
uv run pytest -q
GOALAGENT_DOCKER_TESTS=1 uv run pytest -q tests/test_research.py
uv run python -m goalagent.audit runs/my-research
```

Tests use scripted model decisions. The Docker integration tests execute generated
fixture scripts in actual containers and score their output, but do not measure live
model reasoning or recognition quality.

## Earlier bounded controller and blind-review experiments

A real model now chooses actions from the goal, observed failures and reviewed evidence. The host executes registered tools and evaluates their outputs. This is a working local prototype with a music toolkit, not a universal solver or a finished church transcription app.

The latest [failure investigation and blind-review experiment](runs/blind-review-001/report.html) explains the error mechanisms, existing alternatives, per-role goals, and whether an independent reviewer repairs or damages the original predictions. [Investigation evidence](research/failure-investigation.json) separates confirmed failures from causal hypotheses; [existing solutions](research/existing-solutions.json) records primary sources and what has actually been tested.

## Goals, blindness and scoring

The system goal is to reduce musician correction work while preserving editable melody, harmony and correct transposition. [Role contracts](goalagent/roles.py) assign separate goals:

| Role | Goal | Information available |
| --- | --- | --- |
| Controller | Choose informative experiments and stop honestly within the budget | Goal, domain evidence, development measurements; no reference transcription |
| Transcriber | Recover the visible music faithfully | Image and format specification |
| Blind reviewer | Find image-supported mistakes and propose minimal corrections or abstain | Image and candidate only; no gold answers, previous scores, error locations or shared conversation |
| Deterministic scorer | Measure the frozen result without changing it | Committed predictions and protected references, after the batch is sealed |

The scorer is code, not an LLM agent. The blind reviewer is the answer-free evaluator the user requested. Reference-based accuracy measurement necessarily uses an answer key; separating it from review prevents the answer key from becoming a repair hint. Blindness alone does not guarantee correct analysis.

The reviewer is available to the controller as `run_experiment` with `{"kind":"blind_review","source":"exp-..."}`, using a completed `vision_kern` experiment in the same run. It costs one experiment slot and one additional model call per image. It receives no controller history. Every output is committed before reference scoring is permitted.

The standalone diagnostic separates preparation, review and scoring into different commands:

```sh
uv run python -m goalagent.blind_review prepare \
  --source runs/goal-agent-001-checked/experiments/exp-0ca8aa4fa31f \
  --run-dir runs/my-blind-review
uv run python -m goalagent.blind_review review --run-dir runs/my-blind-review
uv run python -m goalagent.blind_review score --run-dir runs/my-blind-review
uv run python -m goalagent.blind_audit runs/my-blind-review
uv run python -m goalagent.diagnostic_report runs/my-blind-review
```

The frozen protocol records model, prompt/schema hashes, sample policy, budgets and role goals. Inputs and outputs are hashed; changed inputs, changed budgets, premature scoring and post-seal model calls are rejected. Interrupted calls are not silently retried. A failed review retains the original candidate and is counted as a review failure. Existing completed runs remain unchanged.

Model processes now use fresh temporary working directories outside this project with only explicit inputs. Shell and web tools are disabled, and unrecognized model-side tool events cause rejection. This is audited application-level separation, **not an OS filesystem read jail**. A future worker with file/shell tools must run in a separate container/service without the references mounted; a role name or a shared-state framework is insufficient.

All 32 supplied excerpts have already contributed development evidence. We cannot retroactively call any of them an untouched test set. The blind-review run is a development diagnostic; a final evaluation needs fresh songs held out by song, frozen competing systems and no answer feedback until all predictions are committed.

An added chord-onset diagnostic detects correct labels at wrong beats. It supports this dataset's simple two-spine representation only and marks null melody/chord rows as unscorable instead of guessing. It does not replace musician adjudication or a general notation-equivalence metric.

The actual blind-review run used seven additional model calls (442 seconds). It repaired one F4/G4 error: melody edits fell from 4/130 to 3/130, with no measured regressions on the other six excerpts. Chord labels stayed at 0/38 errors. The added timing diagnostic found one wrong onset among 25 scorable chord changes, unchanged by review; one excerpt with 13 chord labels was excluded from timing because of under-specified null rows. The reviewer flagged 내입술의_1 for human review but did not identify its wrong note and slur/tie mistake. This is modest evidence for review, not evidence that a team solves recognition. The recorded-input audit passed, and 51 tests passed.

Open [the agent run report](runs/goal-agent-001-checked/report.html) for the model's decisions, reasons, experiments and scores. [Durable state](runs/goal-agent-001-checked/state.json) is the complete machine-readable record. The earlier [recognition benchmark](runs/first-benchmark/report.html) remains separate and unchanged.

## Run the agent

```sh
uv sync --frozen --extra neural
codex login status
uv run python -m goalagent.runner --goal goals/music.json --run-dir runs/my-agent-run
```

To supply a different natural-language objective within the music toolkit, add `--objective "your goal"` and choose a new run directory. Other domains require an adapter and evaluator; unsupported domains fail explicitly.

This uses the installed Codex CLI and its existing ChatGPT login. It consumes that account's usage allowance; exact monetary cost is not available. It does not require an API key, and it does not reuse or expose raw login tokens. The model defaults to the user's existing Codex model setting; `--model` can select another supported model explicitly. Recognition images are sent to that model only if the controller chooses `vision_kern`.

Run the same command to resume. Completed experiments and per-image predictions have receipts; they are not rerun on normal resume. Use a new run directory for a new goal, changed budget or changed acceptance rule. `--stop-after 5` checkpoints after five tool completions, which is useful for testing resumption. Only one process may operate on a run at a time.

## What makes this an agent

The controller receives observations and emits one structured action at a time. Its action order and experiment choices are model-generated, not a fixed list of calls. It can inspect the dataset, discover and read contextual evidence, inspect the baseline, choose an experiment, request independent evaluation, then change direction or finish. A hypothesis and expected observation must precede each experiment.

The first domain adapter offers three interventions: a vision model producing melody and chords, recovery of text-form chords in Audiveris output, and selectable image scaling/padding for Audiveris. These implementations are predefined tools. The system does not yet invent arbitrary training code or support every possible domain. Extending it means adding a domain's tools and an independent success test, not merely changing a prompt.

The research tool uses an explicit domain-curated library. It does not pretend that the controller performed an unrestricted internet literature search. The source review was performed before the run; the controller chooses which reviewed evidence to consult.

## Why this architecture

- One controller provides a baseline for decision quality and cost. Recognition is a model/tool call, not a claim of improved multi-agent collaboration.
- The controller returns JSON with a brief reason, hypothesis, predicted observation and evidence IDs. The host rejects unsupported actions and citations to unseen evidence.
- Model-side shell and web tools are disabled. Tool execution belongs to host code, with constrained experiment parameters. This is not an OS-level confidentiality boundary against a hostile installed CLI; traces are checked for unexpected model-side tool calls.
- The evaluator opens reference transcriptions only after predictions are saved. The recognition prompt contains pixels and notation instructions, not the reference or song name. The controller receives aggregate scores, not a tool to edit the answer key.
- State is written atomically before actions. Results have receipts and hashes. Interrupted actions can reuse completed image calls rather than restart all inference. Model calls can still have uncertain cost if a process dies before its receipt is saved; this is not an exactly-once billing guarantee.
- Steps, experiments, model calls, per-call time and active run time have limits. A failed call remains a failure. Budget exhaustion never becomes success.
- Completion is a host predicate. The music goal requires all 32 samples, no measured melody/chord errors, transposition checks, audited chord timing and musician acceptance. Those are conservative prototype guards, not an agreed release threshold. A seven-sample pilot cannot pass the complete goal.

## Recent talk review

The selection followed decisions in this project through the official October 2026 conference program. Full available transcripts were reviewed; video frames were not inspected. [Source review with timestamps and limitations](research/recent-talks/review.json).

- [Prime Intellect, October 14: Self-Improving Organizations](https://ai.engineer/nyc/2026/talks/prime-intellect): informs the distinction between evaluation, routing and eventual weight training.
- [Basis, October 14: Process Supervision for Agents That Do Long-Horizon Work](https://ai.engineer/nyc/2026/talks/basis): informs tests for consequential agent behavior as well as final outcomes.
- [Arca, October 13: Inside Arca's long-horizon agents that run the business](https://ai.engineer/nyc/2026/talks/arca): informs durable progress and explicit stopping/resumption.

These are practitioner accounts, not proof of performance on musical notation. The implementation choices above are our application of the evidence. The first system changes plans and records evidence; it does not retrain itself.

## First live result

The controller chose text-to-harmony recovery first, observed no improvement, then chose direct vision transcription. On the same seven excerpts, the vision candidate produced 4 melody edits across 130 reference events and matched all 38 ordered chord labels; five excerpts matched both measured sequences exactly. Enlarged Audiveris and the text-recovery experiment each had 87 melody edits and 30 chord errors on that subset. Chord timing is still unmeasured.

The initial checker falsely rejected four transpositions because it assigned default octaves to octave-free chord labels. Explicit B-to-C# and Bb-to-C regression cases exposed the mistake. A corrected checker passed all seven major-second transformations. The original run is retained, and a versioned continuation let the controller reassess the new evidence. The controller still returned `goal_unmet`, citing the remaining melody errors, unaudited timing, absent musician review and the untested 25 excerpts for this recognizer.

Across the original run and continuation there were 11 controller decisions and 7 recognition calls (18 model calls total), with no unexpected model-side tool calls. The checkpoints preserve the action history. Reopening the completed continuation made no new model calls. See [the process audit](runs/goal-agent-001-checked/agent-evaluation.json) and [33 passing tests](runs/goal-agent-tests.log). A test double is used only in regression tests, not for these live decisions or recognition results.

To version a future evaluator correction while preserving the original run:

```sh
uv run python -m goalagent.fork --source runs/goal-agent-001 --destination runs/recheck-new --evidence research/evaluator-correction.json
uv run python -m goalagent.runner --run-dir runs/recheck-new
uv run python -m goalagent.audit runs/recheck-new
```

The fork carries forward consumed budgets. It retains original model prompts verbatim, redirects copied prediction paths and invalidates cached evaluations. It does not automatically authorize a larger budget or fabricate new recognition output.

## Failure measurements

Measure the two layers separately:

1. **Agent behavior:** invalid actions/citations, tool failures, measured experiments versus unevaluated attempts, model calls and tokens, elapsed time, completion-gate consistency, original-file integrity and whether resume repeats completed work. Regression tests use scripted model doubles; live calls are labeled separately.
2. **Music outcomes:** pitch/duration sequence errors, chord-label sequence errors, missing/extra events, parseability, transposition checks and per-excerpt failures. Chord timing and human correction time remain separate, unmeasured requirements. Same-subset baselines appear beside each experiment.

```sh
uv run pytest -q
```

No result from this small development set demonstrates broad reliability. A future verifier-agent comparison must hold the recognition inputs and budget fixed, measure corrected and introduced errors, and retain an untouched test set. A stronger model, different preprocessing and more agents are different interventions.

---

# Earlier score recognition benchmark

This repository runs image-only recognizers against the 32 supplied score excerpts and evaluates the saved predictions against the corresponding `.krn` files. It is a diagnostic benchmark, not a finished transcription app or a trained model.

Open [the review report](runs/first-benchmark/report.html) to inspect every source image, predicted score, execution trace and individual error. [Complete results](runs/first-benchmark/results.json) include per-song counts. Original inputs and references remain unchanged in `research/data/`; their hashes are in `research/manifest.json`.

## What ran and why

| Experiment | Reason | Observed result |
| --- | --- | --- |
| Audiveris 5.11.0, original pixels | Establish whether existing music recognition software accepts these crops | Only 1/32 produced an output; 31 rejected the small staff spacing |
| Same Audiveris, 3× enlargement and a 60-pixel white border | Test a cheap input change before changing the model or adding agents | 32 files, 31 parseable; 349 melody edits / 570 reference events; 47/200 structured chord labels recovered |
| Transcoda 59M zero-shot checkpoint, greedy decoding | Compare a specialized neural image-to-kern recognizer with frozen weights | 32 adapted files parse; 2,873 melody edits / 570 events; no chord-symbol output; four generations reach a stopping limit |
| Transcoda, beam width 3, seven paired excerpts | Isolate extra decoding search using the same model | Two improve, three worsen, two tie; no chords. This is an exploratory subset, not the full benchmark |

The neural recognizer matches the measured melody exactly in 6/32 excerpts; enlarged Audiveris does so in 2/32. Neither gives an exact measured melody-and-chord result on any of the 32 excerpts. Edit rates above 100% are possible because repeated invented events add insertion errors. They are **not accuracy percentages**. A parseable or renderable file can still contain wrong music.

Examples to inspect:

- `내이름으로_2`: the neural model generates 329 events for an 8-event reference, reaching a generation limit.
- `사랑하셔서_3`: the neural model matches all 23 melody events but supplies none of the 7 chord symbols. This checkpoint's output representation does not cover the complete product requirement.
- `내입술의_1`: enlarged Audiveris matches all 27 melody events but recognizes only 4/6 structured chords.
- `주품에_1`: enlarged Audiveris emits MusicXML with zero divisions; the parser fails. This input remains in the error denominator.

**Historical baseline decision:** improve input handling, recognition coverage and conversion first. That benchmark did not test more agents. At that stage OpenAI vision had not run because no API credential was available. Later experiments above use the authenticated Codex CLI, send the selected images to its model and consume the existing account's usage allowance. No weight training has been performed.

## Measurement contract

- Inference opens images, not reference transcriptions. Anonymous `input.png` copies avoid exposing song names to recognizers. This is a separation of code paths, not an OS security sandbox.
- The primary melody metric is Levenshtein sequence distance over pitch spelling and rational duration. Rests count as events. Adjacent valid ties of the same pitch are merged; an illegal tie between different pitches is not merged. Beaming and bar numbers are ignored.
- There are 570 tie-normalized reference melody events and 200 chord labels. Chords are compared in order by root, quality, slash bass and explicit extensions. This first benchmark **does not measure chord beat placement**, absolute note onsets, voice alignment, repeat playback or complete notation fidelity.
- Audiveris chords come from structured MusicXML `harmony` elements. OCR words that resemble chords are not silently promoted to structured chords. Recovering and aligning those words is a future adapter experiment.
- Missing or unparseable melody output counts as deleting every reference melody event. Insertions inside unparseable output cannot be counted. Parsing and rendering are reported separately.
- Transcoda's canonical output omits the Humdrum header/terminator. A disclosed adapter restores those only, retaining the raw output. It does not repair notes, rhythms or harmonies.
- Enlargement and padding changed together; their individual effects are not isolated. Some processes overlapped and startup treatment differs, so recorded latency is diagnostic rather than a fair speed ranking.
- These 32 excerpts form a development set from seven song groups. The supplied labels have not been audited by a musician. Missing meters, partial measures and boundary ties limit the claims. There is no held-out generalization estimate, release threshold, calibrated confidence or measured musician correction time.

## Checks that distinguish model failure from pipeline failure

1. The same Transcoda adapter scored 0 edits over 80 reference melody events on row 0 of the publisher's synthetic dataset. This positive integration control helps rule out a universally broken input adapter. One sample does not reproduce the model's published benchmark or prove the cause of the user-data failures.
2. Twelve regression tests cover real scoring/conversion pitfalls: pitch and rhythm differences, insertions/deletions, valid and invalid ties, chord quality/extensions and slash bass, and formatting equivalence.
3. A deterministic transposition adapter passes major-second checks on all 32 supplied references, comparing melody intervals/rhythm and chord roots/basses/qualities. This is not recognition accuracy or validation of all possible keys.

The transposition check found a concrete format mismatch: supplied labels use `G:maj/B`; the existing Humdrum transpose filter changes this to `A:maj/B`, leaving the bass unchanged. Our explicit dialect adapter produces `A:maj/C#`. `converter21` also drops these colon-style harmony labels when given them directly, so the reference evaluator parses the dialect explicitly. Originals are preserved. See [transposition checks](runs/first-benchmark/transposition-checks.json) and [generated references](runs/first-benchmark/transposition/).

## Reproduce on this machine

Python 3.12 and `uv` are used. `uv.lock` pins dependencies. The local model and Audiveris assets are already present in `.cache/`.

```sh
uv sync --frozen --extra neural
uv run pytest -q

# Re-score saved predictions without running recognition again.
uv run python -m scorebench.evaluate

# A fresh full run: run these sequentially for less resource contention.
uv run python -m scorebench.run --engine audiveris-raw --run-root runs/repeat-001
uv run python -m scorebench.run --engine audiveris-enlarged --run-root runs/repeat-001
uv run python -m scorebench.run --engine transcoda-greedy --run-root runs/repeat-001
uv run python -m scorebench.evaluate --run-root runs/repeat-001

# The exploratory seven-excerpt decoding comparison.
uv run python -m scorebench.run --engine transcoda-beam --first-per-song

# Optional report server; bind locally, then open /runs/first-benchmark/report.html.
python3 -m http.server 8765 --bind 127.0.0.1
```

The runner resumes from existing `trace.json` files. Use a new `--run-root` for an actual rerun; changing settings in an existing run directory will not replace cached predictions. The evaluator requires all 96 primary traces before scoring. Audiveris subprocesses have a 120-second timeout; neural generation uses the library's 120-second stopping criterion and 2,048-token maximum. Generation time can exceed the criterion slightly because it is checked between generation steps.

The saved control, beam comparison and transposition diagnostics are supplementary artifacts. They are retained in the report; the primary evaluator does not rerun their inference. Each prediction includes a trace and source/output hashes. `provenance.json` records versions and asset hashes, while each inference trace records the runner hash at execution time. Later report and CLI changes do not retroactively change those traces.

## External assets and portability

- [Audiveris official release](https://github.com/Audiveris/audiveris/releases/tag/5.11.0), macOS ARM64. The runner searches `.cache/Audiveris.app` or the mounted `.cache/audiveris-mount/Audiveris.app`. Other platforms require an executable-path adapter.
- [Tesseract English language data](https://github.com/tesseract-ocr/tessdata/blob/4.1.0/eng.traineddata), tag `4.1.0`, in `.cache/tessdata/`. The runner sets `TESSDATA_PREFIX` for the child process only.
- [Transcoda checkpoint](https://huggingface.co/btrkeks/transcoda-59M-zeroshot-v1/tree/b529f8aa5d996d9224df3395b5b92d0867343c91), revision `b529f8aa5d996d9224df3395b5b92d0867343c91`, in `.cache/transcoda-hf/`. The pinned custom Python modules, tokenizer, config and weights are needed. The modules were inspected before loading; `trust_remote_code=True` executes this local model code. Follow the model card's preprocessing. The primary run uses greedy decoding, so it is not a reproduction of published beam-search scores.
- [Transcoda source](https://github.com/btrkeks/transcoda), recorded commit `d4e2e687d5679ae96ca4aa6f01e06a5b338cd488`.
- [Synthetic control dataset](https://huggingface.co/datasets/btrkeks/verovio-synth-omr), default config, `train` split, row 0. The downloaded input and transcription are saved under `runs/control/`; the control was not used for training.

Caches are not part of the source package. Moving this repository requires provisioning these assets and preserving the data and run folders. No cloud infrastructure is required for the completed local benchmark.

## Next experiment and decision gate

Keep these results fixed. On the same images, compare a recognizer capable of melody **and** chord symbols, and separately test extracting Audiveris's text labels into structured chords with image-supported alignment. Audit chord timing with a musician before claiming usable output. Keep newly collected complete pages and different songs as a locked test set.

Only after a baseline has sufficient perceptual coverage should a verifier/repair agent be compared with that same baseline at a fixed budget. Count corrected errors, newly introduced errors, failed runs, cost and musician correction time. Promote a change only if it passes external evaluation gates; an agent's self-critique is not a ground-truth score.

## Configurable research team

The general-purpose entry point is `python -m goalagent.team`. Six default roles share one agent runtime; JSON definitions select models, prompts, tools and limits. The team can create specialist definitions and tested sandbox script tools during a run. See [configuration, tools, delegation and limitations](docs/configurable-team.md).

The existing music workflow remains available, and its experiment engineer now uses the shared runtime. A non-music Docker integration check is available with `python -m goalagent.team_check --run-dir runs/new-team-verification`; its decisions are scripted, not an autonomous research claim.
