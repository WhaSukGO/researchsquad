# Managed workflow implementation notes

This implementation applies the previous team's v0.2.0 principles to ResearchSquad
without embedding the old runtime or its SQLite database. The common `Agent`,
configuration loader, workspaces, tool registry, protected scoring and environment
builder remain the execution base. The host now supplies mandatory work and reviews.

## Decisions and their concrete effect

1. `policy_version: 2` is explicit. Existing custom single-stage/version-1 workflows
   keep synchronous coordinator delegation; shipped research/product templates now
   opt into managed scheduling. A changed contract always needs a fresh run.
2. Work is authoritative inside `team-state.json`. `workboard.py` manages identity,
   dependencies, readiness and attempts; `stage_runtime.py` schedules them. There is
   no second state writer and no recursive child execution in managed `delegate`.
3. Owners/reviewers come from workflow configuration. Role JSON grants remain the
   actual permission boundary. Each required perspective receives its own gate.
4. Reviews are separate contexts. The report-only reader receives a filtered file
   bundle, not the parent input/code bundle. Peer review conclusions are not in
   automatic review context or available through peer-record lookups.
5. Document rejection uses `revise`; measured negative performance uses `improve`;
   failed execution/environment recovery uses `debug`. The semantic work ID remains
   stable while immutable attempts and old measurements remain inspectable.
6. Only typed work items request dispatch. Descriptive next actions are not silently
   converted into duplicate jobs. A proposal referring to an existing work ID does
   not replace its original acceptance criterion.
7. Required source/action receipts and candidate decisions prevent silent omission.
   They do not make every chosen experiment informative or remove semantic hallucination.
8. Environment setup is distinct work with readiness evidence. Counts are separate
   observations, but setup still consumes configured global active time.
9. Managed commands with an uncertain external effect require an explicit operator
   repeat decision. Legacy arbitrary command replay semantics remain in version 1.
10. Music defaults now cover all 32 samples and finite effort. Scoring equations and
    protected references are unchanged; scoped timing/musician events can complete
    only their own human criteria for the exact selected candidate.

## Repository and platform findings

The branch started from `main` at `caad09f`. The separate legacy-cleanup PR was still
open, so legacy runners and archived records are not removed by this change. Cleanup
may need to reconcile the music adapter imports when merged.

Windows Git checkout converted notation line endings and the original-data check
correctly refused to score. The fix preserves `.krn` Git bytes through attributes;
it does not change reference content or expected identities. Development checks
run through Ubuntu/WSL and Docker. POSIX locking/process APIs are not advertised as
native Windows support.

## Verification record and limits

The final check record belongs in `docs/verification/managed-workflow-20261030.json`.
It separates deterministic model fixtures, actual Docker operations, actual model
calls and protected music-adapter checks. Raw model logs and generated workspaces
remain local. Existing 32-sample reference files are not shipped to workers.

Final local regression: 166 passed, four opt-in cases skipped; those four real
Docker cases passed separately. The final-code container fixture passed its
negative-measurement/improve/review/restart sequence. The actual-model sort fixture
completed with 35 returned calls and no added calls on restart. It preceded the
last independent web-response refinement, which received final regression and
actual-network checks. The check record preserves that source-scope distinction.

The real-container fixture demonstrates one work item producing a failed protected
measurement, a measured improvement, separate required reviews and a no-call restart.
It uses scripted model choices and does not show autonomous research judgment.

The music checks verify all-sample handoff, retained denominators for missing output
and scoped human-acceptance logic. They do not establish improved OMR accuracy, new
held-out generalization, a shared-alignment metric redesign, or 100% transcription.

Fresh model verification, including failures and fixes, is added to the final record
before publication. CI executes on the pull request after publication; its live check
status is authoritative. A passing command alone never establishes that the
church-band workflow is ready for use.

## Failures found while validating the implementation

* A WSL non-login launch could not find the Codex executable. Provider preflight now
  rejects that condition before reserving a model call; a login-shell run was used
  for actual reasoning. The first launch's failed reservations are not actual calls.
* In the second live fixture, Experience used a receipt ID as a candidate ID, and
  Report Reader could not discover its filtered report path. The run waited with
  `goal_met: false`. Assignments now deliver explicit report paths and separate the
  review target from its cited receipt, with an actionable validation error.
* Withdrawing a trusted human PASS invalidated a cached receipt but left the goal
  flag true. Current acceptance is now recomputed; both past receipts remain intact.
* Real public search returned a bot challenge with HTTP success. Known challenges
  are now blocked evidence, not successful searches; readable text and per-action
  source files improve inspection. The official Humdrum source was retrievable.
* A newly added acceptance test replaced the shared evaluator dictionary and
  contaminated three later tests. Test-scoped restoration fixed the fixture;
  production evaluation criteria were not changed to satisfy those failures.
