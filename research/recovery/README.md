# Live failure-recovery validation

The supplied starter is a maintainer-prepared training loop, not an agent invention.
`goalagent.recovery_live` gives each independent Team a blinded case label and one
incident source. The real Codex provider chooses diagnoses and recovery actions;
there is no scripted provider. Original source/args must actually fail before repair.

* case-01: save at epoch one, then the trusted host observer sends Docker SIGKILL.
  Acceptance requires failed exit 137 without Docker OOM, a registered checkpoint,
  actual parent/resume lineage, restored epoch one and exact weights matching an
  uninterrupted three-epoch control run.
* case-02: incorrect training-image preprocessing produces 27x27 inputs for a
  784-input MLP. The agent must diagnose the actual runtime error and repair source.
* case-03: an invalid logarithm of raw logits produces NaN before backward. The
  agent must diagnose and repair the loss, keeping finite checks and the data fixed.

Models are independently scored in a restricted CPU container using reviewed
architecture/inference code. A valid recovery needs validation accuracy >=75% on
the final 5,000 official training examples. Official test data is not used.
Research, critic and report-only reviews are separate contexts; project acceptance
is not inferred from a worker report or successful exit.

```sh
python -m goalagent.recovery_live --case case-01 --run-dir tmp/NEW-CASE-01
python -m goalagent.recovery_live --case case-02 --run-dir tmp/NEW-CASE-02
python -m goalagent.recovery_live --case case-03 --run-dir tmp/NEW-CASE-03
```

Avoid overlapping GPU phases: the runtime excludes concurrent GPU starts rather
than maintaining a queue. Role reviews may overlap after training has finished.
Fresh runs consume actual model calls. Matching contracts can reopen completed runs.
Use Linux/WSL with the approved CUDA image and configured provider authentication.

`scripts.recovery_readiness` checks the fault mechanisms with actual GPU containers
but **no model calls**; it is not evidence of agent diagnosis or repair.
`scripts.export_recovery_report` reads preserved evidence and exports the Korean
report, case traces, source patches and structured records without executing agent
code. See docs/recovery-results-ko.md for measured scope, errors and limitations.
