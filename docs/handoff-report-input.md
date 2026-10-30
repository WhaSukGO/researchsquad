# Output handoff and report input improvements

## 1. Direct job output publication

`publish_job_outputs({job_id,files:{output_path:workspace_destination}})` observes
that an owned job has exited, validates the entire mapping, reads bounded regular
files without links, registers immutable Team artifacts and copies bytes directly
to the assignment workspace. Include those destinations in the existing report's
files list to use the unchanged reviewer handoff. No output bodies need to be
generated again by the model. This is worker-reported material, not independent
measurement. Existing inputs and differing destination content cannot be replaced.

Up to 16 files, 16 MB each and 64 MB total may be published. Large model blobs
retain the separate model/checkpoint protocol. Repeating a completed mapping is
idempotent; pre-validation prevents invalid later sources causing an early copy.
Host crashes during copying may leave a partial bundle, which the same request can
complete. Provenance is in registered job-owned artifacts, Team events and durable
job_output_files context. Tool permission and job ownership are both required.

This change is committed independently before report-input work. Negative tests
cover running/foreign jobs, traversal, read-only inputs, symlinks and overwrites;
the positive test preserves exact bytes through the existing submission snapshot.

## 2. Structured report input and preflight

The model action schema now allows a typed report argument object for submit_report
and check_report. Nested claims require document/empirical scope, and objections
provide the actual category/severity enums. Unused sections are empty arrays;
failure_kind is null unless appropriate. The common Agent serializes this object
into the existing host tool protocol; old string arguments remain compatible.
No scope, evidence, category or conclusion is inferred or silently repaired.

check_report runs the same current assignment/evidence checks and artifact capture
checks as submission, but does not submit or change assignment status. It can save
a local immutable validation snapshot and its ordinary action receipt. A successful
preflight is not a review or scientific acceptance; submission validates again.
Optional preflight is not a mandatory extra model call. Semantic evidence mismatch
may still be rejected even when constrained decoding produces valid structure.

This is a separate commit. Tests cover typed normalization, required scope/enums,
unknown evidence rejection in preflight and submission, protected input exclusion,
and a typed response running through the common Agent loop.
