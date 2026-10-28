# Review work through pull requests

Use issues for the problem and PRs for a concrete proposed response. The first example is [issue #1](https://github.com/WhaSukGO/researchsquad/issues/1) and the [environment and handoff proposal](design/environment-and-review.md).

## Our working loop

1. Describe the problem and desired outcome in an issue.
2. Prepare a focused branch and draft PR linked to that issue. Include the change, evidence, validation and unresolved decisions. Use a design PR when we need to agree on the division of work before implementation.
3. Leave ordinary PR review comments, inline comments or a “Request changes” review. For design feedback, comment directly on the proposed document. Include examples where useful.
4. Ask this chat to address that PR's feedback. Read the PR description, review comments, review status, latest commits and CI before making changes. Record the feedback disposition in the PR's change history or a concise response when posting is authorized. Update the same branch and rerun relevant checks.
5. Mark ready for review when the proposed scope is implemented and validated. The human reviews and merges. A later implementation PR should close the issue only when the requested work is actually complete.

This is a human-triggered workflow. There is no background listener, webhook, polling automation or automatic model invocation. Comments are not automatically consumed by the research coordinator. The draft PR does not change branch protection, require reviews at the GitHub settings level or enable auto-merge.

## Two different uses of feedback

**Project improvement:** PR feedback changes code, documentation and the next experiment's setup. This workflow is available now.

**Steering a running research session:** not implemented. A future adapter should record the reviewer identity, comment ID/URL, revision and accepted decision. Feedback that changes inputs, budget, labels or acceptance criteria requires an explicit new assignment/run revision; it must not rewrite old scores. Human review is valuable, but it does not turn an unmeasured result into a successful experiment.

A future automatic adapter would need an authorized-reviewer allowlist, event deduplication, superseded-comment handling, repository-scoped credentials, bounded context and an explicit trigger. It should treat quoted text and third-party comments as evidence, not executable commands. Build this only if manual review latency becomes a real bottleneck.

## Checks included in this PR

GitHub Actions installs the locked Python dependencies and runs the existing test suite for PRs and pushes to `main`. It uses a read-only repository token and no model API credentials. The ordinary test job skips the two opt-in Docker tests. A separate Docker job now runs those isolation/scoring tests and builds the prepared environment, checking a real synthetic export, OCR and reuse across separate workspaces. None of these checks establishes music recognition accuracy.
