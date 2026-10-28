"""Isolated parsing/rendering worker so a malformed score cannot stop the benchmark."""
import json
from pathlib import Path
import sys

from .metrics import parse_events, restore_kern_body, xml_chords, xml_text


def inspect(path):
    import verovio
    path = Path(path)
    result = {"events": [], "chords": [], "parse_ok": False, "render_ok": False,
              "raw_render_ok": False, "adapter_actions": [], "errors": []}
    text = path.read_text() if path.suffix == ".krn" else xml_text(path)
    if path.suffix == ".krn":
        result["raw_has_header"] = any(line.startswith("**kern") for line in text.splitlines())
        try:
            adapted = restore_kern_body(text)
            if adapted.strip() != text.strip():
                result["adapter_actions"].append("Restore canonical kern header and final terminator; musical tokens unchanged")
            text = adapted
            (path.parent / "adapted.krn").write_text(text)
        except Exception as error:
            result["errors"].append("adapter: " + repr(error))
            return result
        fmt = "humdrum"
        # This checkpoint emits kern only; absent chord labels are counted as deletions.
    else:
        fmt = "musicxml"
        (path.parent / "prediction.musicxml").write_text(text)
        try:
            result["chords"] = xml_chords(text)
        except Exception as error:
            result["errors"].append("harmony: " + repr(error))
    try:
        result["events"], result["parser_warnings"] = parse_events(text, fmt)
        result["parse_ok"] = True
    except Exception as error:
        result["errors"].append("parse: " + repr(error))
    toolkit = verovio.toolkit()
    toolkit.setOptions({"inputFrom": fmt, "pageWidth": 2200, "pageHeight": 800, "scale": 40,
                        "adjustPageHeight": True, "breaks": "auto"})
    try:
        if toolkit.loadData(text):
            svg = toolkit.renderToSVG(1)
            result["render_ok"] = "<svg" in svg and ("class=\"note\"" in svg or "class=\"rest\"" in svg)
            (path.parent / "prediction.svg").write_text(svg)
            result["render_pages"] = toolkit.getPageCount()
            result["renderer_log"] = toolkit.getLog()
            result["raw_render_ok"] = result["render_ok"] and not result["adapter_actions"]
        else:
            result["errors"].append("renderer rejected the score")
    except Exception as error:
        result["errors"].append("render: " + repr(error))
    if fmt == "musicxml" and result["parse_ok"]:
        try:
            converter = verovio.toolkit()
            converter.setOptions({"inputFrom": "musicxml-hum"})
            if converter.loadData(text):
                kern = converter.getHumdrumBuffer()
                if "**kern" in kern:
                    (path.parent / "converted.krn").write_text(kern)
                    result["kern_export"] = True
        except Exception as error:
            result["errors"].append("kern export: " + repr(error))
    return result


if __name__ == "__main__":
    try:
        result = inspect(sys.argv[1])
    except Exception as error:
        result = {"events": [], "chords": [], "parse_ok": False, "render_ok": False,
                  "errors": ["worker: " + repr(error)]}
    Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False, indent=2))
