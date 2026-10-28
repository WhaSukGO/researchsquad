# Give research engineers a ready workplace

Status: proposed design, awaiting human review. Related: [issue #1](https://github.com/WhaSukGO/researchsquad/issues/1).

This PR establishes the review workflow and records a proposed change in responsibilities. It does not add an environment engineer to the running system or change access to labels. We should review the design before replacing the current runtime.

## What the feedback exposed

The first engineer was asked to preserve an earlier model's melody predictions while improving chord recognition. We did not supply those predictions to its workspace. That was a faulty assignment and handoff, not a failure to reconstruct music from a score.

The report should say: **“We asked the engineer to reuse earlier melody predictions, but did not give it those files.”** Benchmark scores help the research lead compare approaches and identify regressions. They do not supply the missing implementation inputs.

The supplied labels are present: all 32 reference files exist and match their recorded SHA-256 hashes. The host validates them and the evaluator reads them. Experiment engineers deliberately receive anonymized images without references. Labels and baseline predictions are different artifacts:

| Material | Purpose | Current access | Proposed handling |
| --- | --- | --- | --- |
| Score images | Inputs to recognition | Experiment engineer and evaluator | Explicit input inventory |
| Supplied `.krn` labels | Expected answers for scoring | Protected evaluator | Explicit split and access policy |
| Earlier model predictions | Reuse an existing method's output | Available in the project, but not handed to the first engineer | Declare and validate required artifacts before dispatch |
| Benchmark scores | Compare outcomes | Research lead; selected summaries in assignments | Keep as evidence, never substitute for input files |

If we intend to **train** a recognizer, a training engineer needs labeled training data. Hiding every label is not a universal research policy. We need separate training, development and held-out evaluation sets, with permissions attached to their purpose. All existing 32 excerpts have already informed development; they cannot become an untouched test set retroactively. Any future generalization claim needs fresh songs. Do not repair the missing-prediction handoff by giving a recognition job the answers to the same evaluation images.

## Why Docker did not prevent repeated setup

Docker was already used, but the image was a minimal Python environment. The preflight checked that Docker and the image existed; it did not check Java, OCR, native libraries or a real music export. Each command started a new container. Files in the same engineer's workspace persisted, but child experiments inherited selected source/configuration files, not the installed environment.

The second engineer encountered storage, Java and native-library problems. The next engineer restored runtimes again. The last engineer made GTK load in a Python process but did not demonstrate successful Java/Audiveris export before its deadline. A successful library check was not a successful recognition test.

The logs show repeated setup dominating the work narrative. They do not contain a clean setup-versus-research time breakdown, so we should not claim a precise percentage of time wasted. Future receipts should measure those categories separately.

## Recommendation: a reusable environment tool, with an engineer for exceptions

Use a tested, versioned Docker recipe for routine execution. Ask a dedicated environment engineer to create or repair that recipe only when the requirements change or a readiness test fails. Reuse the resulting immutable image across experiments, while giving each experiment a fresh writable workspace.

| Option | Advantages | Costs and risks | Decision |
| --- | --- | --- | --- |
| Every research engineer installs its own tools | Flexible; little orchestration code | Repeated work, inconsistent environments, research budget spent on setup | Replace as the default |
| One shared mutable container | Fast initially; installed tools survive | Hidden state, cross-experiment interference, difficult replay and cleanup | Do not use as the common workspace |
| A fixed prebuilt image | Simple and cheap to reuse | Cannot anticipate every method; stale packages and architecture mismatches | Good starting point, not the whole solution |
| An environment engineer for every experiment | Clear owner for setup; adapts to unfamiliar tools | Extra model calls and handoffs; may repeat setup unless its outputs are reusable | Do not invoke on every experiment |
| Versioned recipes + cached images + bounded repair engineer | Reusable setup with a clear exception owner | Requires artifact contracts, build management, readiness tests and cache invalidation | Recommended |

An extra role alone will not fix the issue. It needs an enforceable handoff: **recipe, immutable image identity, platform, tested capabilities and evidence that the intended command works**. The host should own builds and validation; research engineers should not receive the Docker socket.

## Team responsibilities

| Owner | One primary responsibility | What it hands over | What it does not own |
| --- | --- | --- | --- |
| Research lead | Choose the next hypothesis and method | Specific assignment, required artifacts, environment requirements, local criteria | Installing dependencies or declaring its own accuracy |
| Environment engineer | Make the requested method executable | Recipe, dependency versions/checksums, entrypoints, smoke tests, concise failure diagnosis | Recognition tuning, reference labels or evaluation thresholds |
| Experiment engineer | Implement and measure the assigned intervention in a ready environment | Source, predictions, execution diagnostics, requests for missing capabilities | Rebuilding the OS/runtime during an experiment |
| Protected evaluator | Score sealed predictions consistently | Metrics, parse/transposition checks and limitations | Repairing candidates or accepting self-reported scores |
| Human reviewer | Decide whether proposed changes and evidence justify the next step | PR feedback, approvals or requested changes | Silently changing an already-recorded evaluation contract |

An evaluation-analysis role, if added later, may explain results and suggest tests. It should use an already prepared evaluation environment and must not modify the scoring authority while assessing a candidate. Specialization should be expressed through tools and permissions as well as prompts. A prompt saying “do not install” cannot fully enforce separation while unrestricted shell commands remain available; the implementation must define and test the actual boundary.

## Proposed handoff and execution flow

1. The lead writes an assignment with explicit required inputs and capabilities. “Preserve baseline melody” must name the prediction artifact set and required sample coverage. If any required file is missing, reject the assignment before commissioning an experiment. Do not manufacture replacements from labels.
2. The host resolves an environment request against the registry. The cache key covers the recipe, base-image digest, dependency lock/checksums, CPU architecture and readiness-test version. A mutable image tag is not sufficient identity.
3. On a miss, the environment engineer proposes or repairs the recipe under a separate setup budget. It returns files and a short diagnosis; the controlled builder executes the build. No reference labels, evaluator source, host credentials or Docker socket are mounted into that engineer's workspace.
4. The host runs readiness tests under the **same user, filesystem, architecture and network constraints** as the real experiment. Tests should check writable temporary storage, required commands/imports and an actual nonempty export from a public or synthetic fixture. Library loading alone is insufficient. This checks executable capability, not model accuracy on our evaluation set.
5. A passing environment is published by immutable image ID/digest. A failed setup returns `environment_blocked`; it does not create a misleading zero-accuracy result or consume one of the scientific experiment slots. It still consumes a bounded setup allowance and contributes to the total run budget.
6. The experiment engineer receives the ready environment plus verified inputs. If a required capability is absent, it returns a structured environment request instead of silently spending its research budget rebuilding dependencies. The lead can authorize a new environment version or choose another method.
7. The evaluator scores sealed predictions using its separately fixed environment. The lead compares results and selects the next experiment. Repeated environment failures prompt a deliberate repair-versus-alternative decision rather than an unbounded repair loop.

Store full build logs on disk. Return the failed phase, command, exit/timeout, duration, first actionable diagnostic, bounded excerpt and retrievable log ID. Last-lines-only output already hid useful information in this run. Do not flood subsequent research contexts with package-manager output.

Persist readiness and build receipts alongside the durable state. Verify image identity and capabilities on reuse/resume; invalidate stale receipts when requirements change. The setup budget needs a retry ceiling even though scientific experiment capacity is preserved. Keep accepted old results immutable and start a new run when the evaluation contract changes.

## What the Claude Code material contributes

I read the requested [overview](https://wikidocs.net/338204) and inspected the linked source tree at commit `a371abbe75ffa0d0a3c92290e2bbf56a7ef54367`. The repository [describes itself as a leaked-source backup](https://github.com/yasasbanukaofficial/claude-code#readme), not an official maintained release or a verified open-source distribution. No source from it is copied or added as a dependency here.

The inspected coordinator separates delegation from implementation and describes resuming workers with prior context. Its tool interface separates schema validation and permissions; its sandbox adapter checks dependencies and initialization; task output is kept on disk with bounded reading. Those are useful design patterns, but they do not establish that the linked system solves our Docker dependency handoff. Its feature-gated PR subscription references also do not mean our project has automatic review-event handling.

Source locations: [coordination](https://github.com/yasasbanukaofficial/claude-code/blob/a371abbe75ffa0d0a3c92290e2bbf56a7ef54367/src/coordinator/coordinatorMode.ts), [tool contracts](https://github.com/yasasbanukaofficial/claude-code/blob/a371abbe75ffa0d0a3c92290e2bbf56a7ef54367/src/Tool.ts), [sandbox adapter](https://github.com/yasasbanukaofficial/claude-code/blob/a371abbe75ffa0d0a3c92290e2bbf56a7ef54367/src/utils/sandbox/sandbox-adapter.ts), [disk output](https://github.com/yasasbanukaofficial/claude-code/blob/a371abbe75ffa0d0a3c92290e2bbf56a7ef54367/src/utils/task/diskOutput.ts).

Official sources provide firmer guidance:

- [Development containers](https://code.claude.com/docs/en/devcontainer) describe consistent isolated environments. The relevant lesson is to version the environment, not repeat its installation inside every task.
- [Custom subagents](https://code.claude.com/docs/en/sub-agents) describe separate contexts, prompts, tools and permissions. Separation reduces context pollution but still consumes model calls.
- [Effective harnesses for long-running agents](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents) describes an initializer, incremental coding work, durable handoff artifacts and end-to-end verification. That supports separating setup from research; it is not evidence that more agents always perform better.

For us, **harness engineering** means making those surrounding contracts reliable: artifact availability, execution environments, budgets, context limits, recovery and independent scoring. Much of the needed change belongs in deterministic host code. Use a model where diagnosing an unfamiliar environment actually requires judgment.

## How we will know the change helped

A follow-up implementation PR should demonstrate:

- A missing required baseline prediction prevents dispatch before any experiment-model call.
- Supplied labels remain available to the evaluator and absent from recognition workspaces; training access uses a separate declared split.
- Two independent experiments use the same prepared image without repeating dependency installation; their writable workspaces remain separate.
- A fresh container passes the real export smoke test. A Python-only library check cannot mark the environment ready.
- Changes in architecture, dependency lock, image identity or smoke-test version invalidate stale readiness.
- A setup failure produces a bounded, resumable setup record and no unsupported accuracy result.
- Resuming does not rebuild a valid environment or silently accept a changed evaluator.
- A live comparison reports setup time, useful experiment time, calls, cost if available, parseability and melody/chord errors under comparable total budgets. Faster setup alone is not an accuracy improvement. Reuse across repeated runs and first-build cost should be reported separately.

## Delivery through PR review

This design PR adds a reusable PR template, a documented human-review loop and ordinary test CI. It leaves the current experiment architecture unchanged. Issue #1 remains open.

Suggested implementation sequence after review:

1. Explicit input contracts and missing-artifact rejection, including baseline-prediction delivery.
2. Environment recipes, registry, readiness tests, cached image reuse and setup accounting.
3. A bounded environment-engineer role and escalation route for new capabilities.
4. A fresh research session comparing outcomes and setup overhead, with a team-readable report.

Review questions: Is tool-first setup with an exception engineer the right division of work? Is the next goal inference improvement or supervised training? Should automated PR comment ingestion be added later, or is a human-triggered review cycle sufficient initially?
