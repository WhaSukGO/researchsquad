"""Run recognizers using images only; never open reference transcriptions here."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
REVISION = "b529f8aa5d996d9224df3395b5b92d0867343c91"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_image(source, destination, enlarged):
    image = Image.open(source).convert("RGB")
    if enlarged:
        image = ImageOps.expand(image.resize((image.width * 3, image.height * 3),
                               Image.Resampling.LANCZOS), border=60, fill="white")
    image.save(destination)


def run_audiveris(image, out, timeout):
    executable = ROOT / ".cache/audiveris-mount/Audiveris.app/Contents/MacOS/Audiveris"
    if not executable.exists():
        executable = ROOT / ".cache/Audiveris.app/Contents/MacOS/Audiveris"
    env = dict(os.environ, TESSDATA_PREFIX=str(ROOT / ".cache/tessdata"))
    command = [str(executable), "-batch", "-transcribe", "-export", "-output", str(out), "--", str(image)]
    with (out / "engine.log").open("w") as log:
        result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    files = sorted(out.rglob("*.mxl")) + sorted(out.rglob("*.musicxml"))
    return {"exit_code": result.returncode, "status": "ok" if files else "no_output",
            "output": str(files[0].relative_to(ROOT)) if files else None,
            "command": command}


def load_transcoda():
    import torch
    from transformers import AutoModelForCausalLM, PreTrainedTokenizerFast
    torch.set_num_threads(4)
    torch.manual_seed(0)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    path = ROOT / ".cache/transcoda-hf"
    # Code is downloaded at a pinned revision and inspected before this load.
    model = AutoModelForCausalLM.from_pretrained(str(path), trust_remote_code=True).to(device).eval()
    tokenizer = PreTrainedTokenizerFast.from_pretrained(str(path))
    return model, tokenizer, device


def run_transcoda(image, out, loaded, beams, timeout):
    import numpy as np
    import torch
    model, tokenizer, device = loaded
    img = Image.open(image).convert("RGB")
    # Exact model-card geometry: aspect-preserving width resize, bottom white padding.
    h = max(1, int(img.height * 1050 / img.width))
    img = img.resize((1050, h), Image.Resampling.BILINEAR)
    canvas = Image.new("RGB", (1050, 1485), "white")
    canvas.paste(img.crop((0, 0, 1050, min(h, 1485))), (0, 0))
    pixels = torch.from_numpy(np.array(canvas)).permute(2, 0, 1).float() / 127.5 - 1
    pixels = pixels.unsqueeze(0).to(device)
    sizes = torch.tensor([[1485, 1050]], device=device)
    with torch.inference_mode():
        result = model.generate(pixel_values=pixels, image_sizes=sizes, max_length=2048,
                                do_sample=False, num_beams=beams, repetition_penalty=1.1,
                                max_time=timeout)
    ids = result[0].tolist()
    prediction = tokenizer.decode(ids, skip_special_tokens=True)
    target = out / "prediction.krn"
    target.write_text(prediction)
    (out / "token_ids.json").write_text(json.dumps(ids))
    finished = model.config.eos_token_id in ids
    return {"status": "ok" if finished else "generation_limit", "output": str(target.relative_to(ROOT)),
            "device": device, "tokens": len(ids), "eos_reached": finished,
            "settings": {"num_beams": beams, "max_length": 2048, "max_time": timeout,
                         "repetition_penalty": 1.1, "do_sample": False, "revision": REVISION}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["audiveris-raw", "audiveris-enlarged", "transcoda-greedy", "transcoda-beam"], required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--first-per-song", action="store_true", help="Exploratory subset: first listed excerpt from each song, preserving original sample IDs")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--run-root", default="runs/first-benchmark")
    args = parser.parse_args()
    samples = json.loads((ROOT / "research/manifest.json").read_text())[:args.limit]
    run_dir = ROOT / args.run_root / args.engine
    run_dir.mkdir(parents=True, exist_ok=True)
    loaded = None
    if args.engine.startswith("transcoda"):
        try:
            loaded = load_transcoda()
        except Exception as error:
            (run_dir / "setup_failure.json").write_text(json.dumps({"status": "setup_failed", "error": repr(error)}, indent=2))
            raise
    seen_songs = set()
    for index, sample in enumerate(samples):
        if args.first_per_song:
            if sample["song"] in seen_songs:
                continue
            seen_songs.add(sample["song"])
        out = run_dir / f"sample-{index+1:03}"
        out.mkdir(exist_ok=True)
        trace_path = out / "trace.json"
        if trace_path.exists():
            print(f"cached {args.engine} {index+1}/{len(samples)}", flush=True)
            continue
        source = ROOT / sample["image"]
        if sha(source) != sample["image_sha256"]:
            raise ValueError(f"Input image changed: {source}")
        image = out / "input.png"
        prepare_image(source, image, args.engine == "audiveris-enlarged")
        record = {"id": sample["id"], "engine": args.engine, "source_image": sample["image"],
                  "source_image_sha256": sha(source), "input_sha256": sha(image),
                  "started_unix": time.time(), "reference_access": False,
                  "runner_sha256": sha(__file__)}
        start = time.monotonic()
        try:
            record.update(run_audiveris(image, out, args.timeout) if args.engine.startswith("audiveris")
                          else run_transcoda(image, out, loaded, 3 if args.engine.endswith("beam") else 1, args.timeout))
        except subprocess.TimeoutExpired:
            record.update(status="timeout", output=None)
        except Exception as error:
            record.update(status="error", output=None, error=repr(error))
        record["elapsed_seconds"] = time.monotonic() - start
        if record.get("output"):
            record["output_sha256"] = sha(ROOT / record["output"])
        trace_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        print(f"{args.engine} {index+1}/{len(samples)} {record['status']} {record['elapsed_seconds']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
