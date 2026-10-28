"""Transparent first-pass metrics, deliberately narrower than a full OMR evaluator.

Sequence edit distance is used instead of raw .krn text equality. It tolerates
different beaming and bar numbering, but is NOT a complete score-equivalence test.
"""
from __future__ import annotations

from collections import Counter
from fractions import Fraction
import io
import contextlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

import converter21
import music21 as m21
from rapidfuzz.distance import Levenshtein

converter21.register()

KINDS = {"maj": "major", "min": "minor", "7": "dominant", "maj7": "major-seventh",
         "min7": "minor-seventh", "min6": "minor-sixth", "dim7": "diminished-seventh",
         "sus4": "suspended-fourth", "add9": "major"}


def pitch_name(value):
    return value.replace("♭", "b").replace("♯", "#").replace("-", "b")


def chord_from_label(label):
    root, tail = label.split(":", 1)
    pieces = tail.split("/", 1)
    quality = pieces[0]
    if quality not in KINDS:
        raise ValueError(f"Unsupported reference chord quality: {quality}")
    bass = pieces[1] if len(pieces) == 2 else root
    degrees = ((9, 0, "add"),) if quality == "add9" else ()
    return (pitch_name(root), KINDS[quality], pitch_name(bass), degrees)


def reference_chords(text):
    lines = text.splitlines()
    headers = next(line.split("\t") for line in lines if line.startswith("**"))
    index = headers.index("**mxhm")
    return [chord_from_label(line.split("\t")[index]) for line in lines
            if line and not line.startswith(("*", "!", "=")) and line.split("\t")[index] != "."]


def xml_text(path):
    path = Path(path)
    if path.suffix == ".mxl":
        with zipfile.ZipFile(path) as archive:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            root = next(e.attrib["full-path"] for e in container.iter() if e.tag.endswith("rootfile"))
            return archive.read(root).decode("utf-8")
    return path.read_text()


def xml_chords(text):
    root = ET.fromstring(text)
    result = []
    def note_name(node, prefix):
        step = node.findtext(prefix + "-step")
        alter = int(float(node.findtext(prefix + "-alter", "0")))
        return step + ("#" * alter if alter >= 0 else "b" * -alter)
    for chord in root.iter("harmony"):
        root_node = chord.find("root")
        if root_node is None:
            result.append(("UNKNOWN", ET.tostring(chord, encoding="unicode"), "", ()))
            continue
        note = note_name(root_node, "root")
        bass_node = chord.find("bass")
        bass = note_name(bass_node, "bass") if bass_node is not None else note
        degrees = tuple(sorted((int(d.findtext("degree-value")), int(float(d.findtext("degree-alter", "0"))),
                                d.findtext("degree-type")) for d in chord.findall("degree")))
        result.append((note, chord.findtext("kind", "UNKNOWN"), bass, degrees))
    return result


def kern_melody_only(text):
    """Reference files have exactly one kern column. Do not silently apply to polyphony."""
    lines = text.splitlines()
    headers = next(line.split("\t") for line in lines if line.startswith("**"))
    if headers.count("**kern") != 1:
        raise ValueError("Reference scorer expects exactly one kern spine")
    i = headers.index("**kern")
    return "\n".join(line if line.startswith("!!") else line.split("\t")[i]
                     for line in lines if line.strip()) + "\n"


def restore_kern_body(text):
    """Restore omitted canonical header/terminator; never change pitches or durations.

Unsupported spine transitions are rejected rather than guessed. This adapter is
reported separately from raw model output and does not use the reference.
"""
    lines = [line for line in text.strip().splitlines() if line.strip()]
    if not lines:
        raise ValueError("Empty prediction")
    content = [line for line in lines if not line.startswith("!!")]
    width = len(content[0].split("\t"))
    if not content[0].startswith("**"):
        lines.insert(0, "\t".join(["**kern"] * width))
    for line in lines:
        if line.startswith("!!"):
            continue
        cells = line.split("\t")
        if len(cells) != width:
            raise ValueError("Inconsistent spine width")
        if any(c in {"*^", "*v", "*x", "*+"} for c in cells):
            raise ValueError("Spine manipulation requires a general restoration adapter")
    if not all(c == "*-" for c in lines[-1].split("\t")):
        lines.append("\t".join(["*-"] * width))
    return "\n".join(lines) + "\n"


def events_from_score(score):
    """Merge tied continuations, retaining pitch spelling and exact rational duration."""
    rows = []
    parts = list(score.parts) if hasattr(score, "parts") else []
    for part_index, part in enumerate(parts or [score]):
        previous = None
        for obj in part.flatten().notesAndRests:
            if isinstance(obj, m21.harmony.Harmony):
                continue
            pitches = ("REST",) if isinstance(obj, m21.note.Rest) else tuple(sorted(p.nameWithOctave for p in obj.pitches))
            duration = Fraction(obj.quarterLength).limit_denominator(65536)
            offset = Fraction(obj.offset).limit_denominator(65536)
            tie = obj.tie.type if getattr(obj, "tie", None) else None
            # Do not let a notation library merge an illegal tie between different pitches.
            if (previous and tie in {"stop", "continue"} and previous["tie"] in {"start", "continue"}
                    and previous["pitches"] == pitches and previous["offset"] + previous["duration"] == offset):
                previous["duration"] += duration
                previous["tie"] = tie
            else:
                previous = {"part": part_index, "offset": offset, "pitches": pitches,
                            "duration": duration, "tie": tie, "grace": obj.duration.isGrace}
                rows.append(previous)
    rows.sort(key=lambda r: (r["offset"], r["part"]))
    return [(r["pitches"], "grace" if r["grace"] else str(r["duration"])) for r in rows]


def parse_events(text, fmt):
    warnings = io.StringIO()
    with contextlib.redirect_stderr(warnings):
        score = m21.converter.parseData(text, format=fmt, forceSource=True)
        events = events_from_score(score)
    if not events:
        raise ValueError("Parsed score contains no musical events")
    return events, warnings.getvalue()


def sequence_metrics(reference, prediction):
    operations = Levenshtein.editops(reference, prediction)
    counts = Counter(op.tag for op in operations)
    matches = len(reference) - counts["replace"] - counts["delete"]
    precision = matches / len(prediction) if prediction else (1.0 if not reference else 0.0)
    recall = matches / len(reference) if reference else (1.0 if not prediction else 0.0)
    return {
        "reference_count": len(reference), "prediction_count": len(prediction),
        "matches": matches, "substitutions": counts["replace"], "deletions": counts["delete"],
        "insertions": counts["insert"], "errors": len(operations),
        "error_rate": len(operations) / len(reference) if reference else (None if prediction else 0.0),
        "precision": precision, "recall": recall,
        "f1": 2 * matches / (len(reference) + len(prediction)) if reference or prediction else 1.0,
        "edits": [{"operation": op.tag, "reference_index": op.src_pos, "prediction_index": op.dest_pos,
                   "expected": reference[op.src_pos] if op.tag != "insert" else None,
                   "actual": prediction[op.dest_pos] if op.tag != "delete" else None} for op in operations],
    }


def transpose_reference_dialect(text, interval_name="M2"):
    """Transpose the supplied two-column dialect without losing slash bass or quality."""
    import verovio
    interval = m21.interval.Interval(interval_name)
    # Use the existing Humdrum tool for melody, while explicitly handling the local chord dialect.
    melody = kern_melody_only(text)
    transposed = verovio.toolkit().convertHumdrumToHumdrum(f"!!!filter: transpose -t {interval_name}\n" + melody)
    melody_lines = [line for line in transposed.splitlines() if not line.startswith("!!!Xfilter:")]
    original = [line for line in text.splitlines() if line.strip()]
    if len(melody_lines) != len(original):
        raise ValueError("Transposition changed row count; refusing to misalign harmony")
    result = []
    def shift(note):
        return interval.transposePitch(m21.pitch.Pitch(note.replace("b", "-"))).name.replace("-", "b")
    for source, target in zip(original, melody_lines):
        if source.startswith("!!"):
            result.append(source)
            continue
        _, chord = source.split("\t")
        if not source.startswith(("*", "=", "!")) and chord != ".":
            root, rest = chord.split(":", 1)
            quality, *bass = rest.split("/", 1)
            chord = shift(root) + ":" + quality + ("/" + shift(bass[0]) if bass else "")
        result.append(target + "\t" + chord)
    return "\n".join(result) + "\n"
