# Operating a source-informed GPU study

This extends the existing common Agent/configuration/runtime with real paper and
implementation retrieval. It does not add a researcher subclass or let downloaded
Python run on the host. The executable study is `goalagent.literature_live`.

## Responsibilities and handoffs

| Work | Owner | Required delivery | Next reader |
| --- | --- | --- | --- |
| Find primary method papers and public implementations, read their bodies, select a bounded hypothesis | Researcher | `sources.json`, `literature.md`, `plan.md`, preserved original source text | Critic, then Experiment Engineer |
| Check attribution, transfer assumptions and feasibility | Critic in a separate assignment | Review gate verdict and evidence | Managed workflow |
| Implement baseline, inspect results, choose a controlled comparison, select by validation | Experiment Engineer | Training source, actual output files, `experiments.json`, `source-influence.json`, `model-ref.json`, self-contained `report.md` | Researcher, Critic, Report Reader |
| Inspect experiment/source fidelity and isolation | Researcher and Critic in separate contexts | Review verdicts and objections | Managed workflow |
| Read the report as a recipient without code/source context | Report Reader | Clarity verdict, scope limitations | Managed workflow |
| Verify provenance and run frozen final inference | Maintainer-owned evaluator | Structural source check, independent validation and final test | Workflow acceptance |

Review rejection creates another immutable attempt. A valid negative experiment
can complete: acceptance means the bounded source-linked delivery met its gates,
not that the paper was reproduced or accuracy improved. The host's provenance
check cannot establish that a source actually supports an interpretation; this
remains an explicit reviewer responsibility.

## Tools and runtime boundaries

`web_search` still accepts a plain query. It additionally accepts a JSON string
`{"provider":"crossref|github|duckduckgo","query":"..."}`. Crossref and GitHub
return compact discovery metadata, explicitly distinguished from reading a paper
or code. One failed provider does not imply all public retrieval is unavailable.

`web_fetch` preserves original response bytes and readable text as Team-owned
immutable artifacts, and returns their IDs, paths, format and transport metadata.
Python source remains source text rather than being passed through an HTML parser.
PDFs use an owner-approved immutable image with pypdf 6.21.4 in a separate,
network-disabled, read-only, resource-limited container. Parsing is limited to
40 pages/200,000 characters, with page markers and explicit truncation. Image-only
documents have no OCR fallback and are rejected when usable text is unavailable.
HTTP, challenge-page and parsing failures are distinct from usable retrieval.

The study grants managed web access only to Researcher, with no arbitrary shell.
Engineering can run code and GPU jobs but has no network. The dataset adapter
provides only the official training corpus. Known official test-file URLs and
checkpoint extensions are excluded from public fetching. These URL patterns are
an access policy, not a universal detector of every possible data mirror; reviewers
must still inspect source and data use. Downloaded sources are untrusted evidence.

The source gate requires a fetched PDF body and a commit-pinned Python body,
owner-bound fetch/read/discovery receipts, preserved original text, and substantive
paper read windows. Search metadata alone cannot pass. Submitted text and actual
read windows must match the original immutable bytes. This protects provenance,
not semantic truth or proof that a model understood every page.

Training uses the existing managed GPU jobs, direct output publishing, large model
storage and safe declarative inference registry. The experiment can choose MLP/CNN
size, dropout, optimizer/schedule and compatible training-only changes within that
registry. It cannot invent an arbitrary inference architecture. The split is fixed
at 55,000 train / 5,000 validation, seed 1337; each job has at most five epochs.
Two valid runs are the planned limit unless an execution repair is documented.
After selection the host scores the frozen model on validation and on the official
test corpus once. Report-only revisions cannot silently swap the tested model.

## Run and inspect

Use WSL/Linux, the locked Python 3.12 environment and Docker. Build the source
reader image, retain its immutable ID, and prepare the existing CUDA training image
as described in the training guides:

```sh
docker build -t researchsquad-sources:pypdf6.21.4 environments/source-reader
python -m scripts.source_readiness --run-dir /absolute/path/to/fresh-readiness
python -m goalagent.literature_live --run-dir /absolute/path/to/fresh-study
```

Readiness executes actual retrieval with fixed maintainer-selected URLs and **zero
model calls**. It is transport verification, not evidence that an agent discovered
those sources. `literature_live` uses the configured actual provider for every role;
it names no particular paper or repository in the study prompt.

Use absolute run directories. During this task a relative-directory managed
fixture failed on reopen with `FileNotFoundError` while resolving the process
working directory; a fresh absolute-directory invocation passed. The underlying
cause has not been established. Reuse the same directory only for an unchanged
contract/restart. Otherwise create a fresh run and preserve the old outcome.

Inspect `traces/*.json`, `events.jsonl`, assignment `actions/*.json`, original source
artifacts, source/evaluation results and `training/jobs/*/output`. Export a readable
trace at any point with `python -m goalagent.tracing --run-dir RUN --output TRACE.html`.
It shows prompts, grants, messages, explicit alternatives/why, tool results and
reviews. It does not expose hidden reasoning or all internal alternatives.

Human reports should connect source → reading → decision → code → actual job →
observed outcome. Keep original PDFs, downloaded source bodies, datasets,
checkpoints and raw traces local rather than committing them. Commit maintained
notes, bounded paraphrases, source URLs and measured summaries.

The [actual execution report](external-source-results-ko.md) records a valid
negative comparison and the limits encountered. For standalone report reviews,
objections must target a registered artifact/candidate ID, not a file path with a
passage label; put the passage in the objection statement. Explicitly grant
`view_image` if a text-only reader is also expected to inspect an included PNG.
The shipped training reader is text-only. Preserve incomplete/blocked reviews
rather than calling their checkpoint an accepted review.
