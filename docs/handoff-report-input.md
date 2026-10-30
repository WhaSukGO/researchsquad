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
