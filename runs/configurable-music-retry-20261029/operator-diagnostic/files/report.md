# Frozen first candidate

This is a seven-sample development submission. The church-band acceptance goal remains unmet: protected evaluation, chord timing audit and musician acceptance have not been performed. Submission does not establish accuracy.

## Reproduction

Use the declared prepared Python environment (music21 9.9.2 and converter21 4.0.1). Run `python build_candidate.py`, then `python -m unittest test_candidate`. Inputs are resolved by candidate-config.json. Seven root-level sample files are the candidate; provenance.json records source/output SHA256 hashes.

## Observations and source provenance

The supplied kern is preserved verbatim for samples 001, 006 and 012 except an empty harmony spine where required. For samples 017, 019 and 023, canonical converter21 export repairs serialization; exported Harte harmony is translated by an explicit finite map to MusicXML-style **mxhm. Harmonies come only from the supplied source, whose recognition can itself be wrong. Images were supplied but no new visually inferred chord was added in this freeze.

The supplied sample-029 MusicXML has divisions=0 and only two pitched notes with explicit half-note types. The repair uses divisions=1 and duration=2. The original D4/B3 pitches are retained; empty measures remain unresolved.

Evidence: supplied artifacts inputs/brief.txt, inputs/samples.json and the per-sample source paths/hashes in provenance.json; earlier inspection logs 007.log, 008.log, 011.log and 012.log in the task history document raw conversion failures and canonical export behavior. New directly reproducible evidence is build-results.log, test-results.log, provenance.json and transposition-checks.json (when its tests pass).

| Sample | Parse | Source/output note events | Source/output duration | Chords | Exact parsed event preservation |
|---|---|---|---|---|---|
| sample-001 | True | 8/8 | 9.0/9.0 | 0 | True |
| sample-006 | True | 15/15 | 8.5/8.5 | 0 | True |
| sample-012 | True | 32/32 | 16.0/16.0 | 4 | True |
| sample-017 | True | 19/19 | 21.5/21.5 | 2 | True |
| sample-019 | True | 20/22 | 21.0/21.0 | 1 | False |
| sample-023 | True | 15/16 | 23.0/23.0 | 1 | False |
| sample-029 | True | 2/2 | 12.0/12.0 | 0 | True |

## Local checks and limitations

test-results.log is authoritative for local test outcomes. Tests check tab-separated active spine widths, matched terminators, converter21 parsing, nonempty notes, and upward-major-second/inverse transposition of parsed note pitches, harmony roots and slash basses, duration, harmony kind and offsets. These checks do not prove source-image accuracy, and do not test a protected evaluator or a transposed file export. Canonical serialization may split tied events; changes in event counts are reported rather than hidden.

Chord timing is inherited from recognized source rows; its alignment to the images is unresolved and was not audited. Missing chords are intentionally omitted. Sample 006 and sample 029 have no source-supported harmonies in the selected notation sources. The MusicXML duration repair for sample 029 is an explicit interpretation of the written note types; correctness of its bar placement is uncertain.

## Hypotheses and next steps

Canonical serialization may improve evaluator parse coverage relative to the delivered baseline (which reported 3/7); this is a hypothesis until coordinator evaluation. No protected accuracy delta is claimed. Next, compare frozen output against the images, audit chord beats and sample-029 missing material, and request musician review after evaluator feedback.
