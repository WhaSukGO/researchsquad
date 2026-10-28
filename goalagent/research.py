"""Open-ended experiment implementation with host-owned sealing and evaluation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil

from scorebench.run import ROOT
from .contracts import atomic_json, digest
from .music import MusicTools
from .provider import CodexProvider
from .sandbox import DockerSandbox, workspace_path, read_file
from .worker import ExperimentWorker

DEFAULT_WORKER_POLICY = {
    "image": "python:3.12-slim", "network": False, "memory": "2g", "cpus": 2,
    "max_steps": 16, "max_seconds": 600, "command_timeout": 120,
    "model_call_timeout": 180,
}
EVALUATOR_FILES = ["goalagent/research.py", "goalagent/music.py", "goalagent/inspect.py",
                   "goalagent/contracts.py", "scorebench/metrics.py", "scorebench/evaluate.py",
                   "scorebench/inspect_prediction.py"]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def compact_evaluation(result):
    if not result:
        return None
    return {"samples": result["samples"], "parseable": result["parseable"],
            "melody_error_rate": result["melody"]["error_rate"],
            "chord_error_rate": result["chords"]["error_rate"],
            "transposition_failures": result.get("transposition_failures"),
            "chord_timing_audited": result.get("chord_timing_audited", False),
            "musician_accepted": result.get("musician_accepted", False)}


class ResearchTools(MusicTools):
    def __init__(self, run_dir, spec, model=None, worker_provider=None, sandbox_factory=DockerSandbox):
        super().__init__(run_dir, spec, model)
        self.run_dir = self.run_dir.resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.worker_provider = worker_provider or CodexProvider(model, effort="high")
        self.sandbox_factory = sandbox_factory
        configured = spec.get("worker", {})
        if set(configured) - set(DEFAULT_WORKER_POLICY):
            raise ValueError("Unknown worker policy fields")
        self.policy = {**DEFAULT_WORKER_POLICY, **configured}
        for key in ("max_steps", "max_seconds", "command_timeout", "model_call_timeout", "cpus"):
            if type(self.policy[key]) is not int or self.policy[key] <= 0:
                raise ValueError(f"Invalid worker limit: {key}")
        if type(self.policy["network"]) is not bool:
            raise ValueError("Worker network policy must be boolean")
        if not isinstance(self.policy["image"], str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./:@-]*", self.policy["image"]):
            raise ValueError("Invalid worker image")
        if not isinstance(self.policy["memory"], str) or not re.fullmatch(r"[1-9][0-9]*[mg]", self.policy["memory"]):
            raise ValueError("Invalid worker memory limit")
        self.contract = self.contract_fingerprint()
        contract_path = self.run_dir / "evaluation-contract.json"
        if contract_path.exists():
            if json.loads(contract_path.read_text()) != self.contract:
                raise ValueError("Protected evaluation contract changed; start a new research run")
        else:
            atomic_json(contract_path, self.contract)

    def contract_fingerprint(self):
        import importlib.metadata
        return {"spec_hash": digest(self.spec), "manifest_hash": digest(self.manifest),
                "baseline_hash": digest(self.baseline),
                "code": {name: sha((ROOT / name).read_bytes()) for name in EVALUATOR_FILES},
                "dependencies": {name: importlib.metadata.version(name)
                                 for name in ("music21", "converter21", "verovio", "rapidfuzz")}}

    def assert_originals(self):
        super().assert_originals()
        if hasattr(self, "contract") and self.contract_fingerprint() != self.contract:
            raise ValueError("Protected evaluator changed during this run")

    def experiment_config(self, argument):
        cfg = json.loads(argument)
        if not isinstance(cfg, dict) or set(cfg) != {"mode", "parent", "approach", "objective", "success_criteria"}:
            raise ValueError("Assignment requires mode, parent, approach, objective and success_criteria")
        for key in ("approach", "objective", "success_criteria"):
            if not isinstance(cfg[key], str) or not 10 <= len(cfg[key].strip()) <= 3000:
                raise ValueError(f"Assignment {key} must be specific (10–3000 characters)")
        if cfg["mode"] not in {"explore", "improve", "debug"}:
            raise ValueError("Choose explore, improve or debug")
        if cfg["mode"] == "explore":
            if cfg["parent"] is not None:
                raise ValueError("Exploration starts a new root; parent must be null")
        elif not isinstance(cfg["parent"], str) or not re.fullmatch(r"exp-[0-9a-f]{12}", cfg["parent"]):
            raise ValueError("Improvement/debugging requires a parent experiment")
        return cfg

    def prepare_assignment(self, decision):
        cfg = self.experiment_config(decision["argument"])
        eid = self.experiment_id(cfg)
        folder = self.run_dir / "experiments" / eid
        assignment = {"system_goal": self.spec["goal"], "task": cfg,
                      "hypothesis": decision["hypothesis"],
                      "expected_observation": decision["expected_observation"],
                      "rationale": decision["why"], "evidence_ids": decision["evidence_ids"],
                      "output_contract": "One output/sample-NNN.krn per inputs/sample-NNN.png",
                      "budget": self.policy}
        evidence = []
        for evidence_id in decision["evidence_ids"][:6]:
            if evidence_id == "goal":
                continue
            try:
                record = self.find_record(evidence_id)
            except ValueError:
                continue
            obs = record["observation"]
            if "melody" in obs and "chords" in obs:
                obs = compact_evaluation(obs)
            evidence.append({"id": evidence_id, "data": json.dumps(obs, ensure_ascii=False)[:3000]})
        assignment["supporting_evidence"] = evidence
        if cfg["parent"]:
            parent = self.run_dir / "experiments" / cfg["parent"]
            self.verify_seal(parent)
            evaluation_path = parent / "evaluation.json"
            assignment["parent_result"] = compact_evaluation(json.loads(evaluation_path.read_text())) if evaluation_path.exists() else None
            assignment["parent_execution"] = json.loads((parent / "receipt.json").read_text())["worker"]
        path = folder / "assignment.json"
        if path.exists() and json.loads(path.read_text()) != assignment:
            raise ValueError("Cannot overwrite an existing worker assignment")
        atomic_json(path, assignment)
        atomic_json(folder / "config.json", cfg)

    def find_record(self, evidence_id):
        index_path = self.run_dir / "evidence" / "index.json"
        if not index_path.exists():
            raise ValueError("No evidence records yet")
        for entry in json.loads(index_path.read_text()):
            record = json.loads((self.run_dir / entry["record"]).read_text())
            if record["observation"]["id"] == evidence_id or any(
                source["id"] == evidence_id for source in record["observation"].get("sources", [])
            ):
                return record
        raise ValueError("Unknown evidence record")

    def execute(self, tool, argument, charge_model, remaining_seconds):
        if tool == "read_record":
            data = json.loads(argument)
            offset = data.get("offset", 0)
            if type(offset) is not int or offset < 0:
                raise ValueError("Invalid evidence offset")
            record = self.find_record(data["id"])
            text = json.dumps(record, ensure_ascii=False)
            return {"id": "record-" + digest(data)[:12], "source_id": data["id"],
                    "offset": offset, "total_characters": len(text), "text": text[offset:offset + 6000]}
        return super().execute(tool, argument, charge_model, remaining_seconds)

    def verify_seal(self, folder):
        folder = Path(folder)
        seal = json.loads((folder / "seal.json").read_text())
        if seal["contract_hash"] != digest(self.contract):
            raise ValueError("Evaluation contract differs from sealed experiment")
        expected_predictions = {f"sample-{index:03}/prediction.krn" for index, _ in self.selected()}
        if set(seal["predictions"]) != expected_predictions:
            raise ValueError("Sealed sample set changed")
        for relative, checksum in {**seal["files"], **seal["predictions"]}.items():
            if sha(read_file(folder, relative, limit=16_000_000)) != checksum:
                raise ValueError("Sealed experiment integrity violation: " + relative)
        if (folder / "receipt.json").exists() and digest(json.loads((folder / "receipt.json").read_text())) != seal["receipt_hash"]:
            raise ValueError("Sealed receipt integrity violation")
        return seal

    def run_experiment(self, cfg, charge_model, remaining_seconds):
        eid = self.experiment_id(cfg)
        folder = self.run_dir / "experiments" / eid
        if (folder / "receipt.json").exists():
            self.verify_seal(folder)
            return json.loads((folder / "receipt.json").read_text())
        assignment = json.loads((folder / "assignment.json").read_text())
        workspace = folder / "worker" / "workspace"
        inputs = workspace / "inputs"
        # Initialization is checkpointed before the worker starts; no host labels
        # or project modules are ever copied into this workspace.
        marker = folder / "worker" / "initialized.json"
        if not marker.exists():
            if workspace.exists():
                shutil.rmtree(workspace)
            inputs.mkdir(parents=True)
            (workspace / "output").mkdir()
            for index, sample in self.selected():
                shutil.copyfile(ROOT / sample["image"], inputs / f"sample-{index:03}.png")
            if cfg["parent"]:
                parent = self.run_dir / "experiments" / cfg["parent"]
                self.verify_seal(parent)
                sources = json.loads((parent / "source-snapshot.json").read_text())
                for relative, content in sources.items():
                    target = workspace_path(workspace, relative)
                    if target.is_relative_to(inputs) or target.is_relative_to(workspace / "output"):
                        raise ValueError("Invalid parent source path")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content)
            atomic_json(marker, {"assignment_hash": digest(assignment)})
        worker = ExperimentWorker(folder / "worker", assignment, self.worker_provider,
                                  self.policy, self.sandbox_factory)
        try:
            outcome = worker.run(charge_model, remaining_seconds)
        except Exception as error:
            outcome = {"status": "execution_failed", "error": str(error)[:2000]}
        # Even a failed worker becomes an immutable branch with a receipt. The
        # coordinator can debug it without getting stuck behind an unscorable run.
        source_path = folder / "worker" / "source-snapshot.json"
        sources = json.loads(source_path.read_text()) if source_path.exists() else {}
        atomic_json(folder / "source-snapshot.json", sources)
        predictions = {}
        statuses = {"ok": 0, "missing_or_invalid": 0}
        for index, sample in self.selected():
            out = folder / f"sample-{index:03}"
            out.mkdir(exist_ok=True)
            error = None
            try:
                raw = read_file(workspace, f"output/sample-{index:03}.krn")
                raw.decode("utf-8")
                if not raw.strip():
                    raise ValueError("Empty prediction")
            except (OSError, ValueError) as exc:
                raw, error = b"", str(exc)[:500]
            pred = out / "prediction.krn"
            pred.write_bytes(raw)
            shutil.copyfile(ROOT / sample["image"], out / "input.png")
            status = "ok" if raw else "missing_or_invalid"
            statuses[status] += 1
            atomic_json(out / "trace.json", {"sample_index": index, "id": sample["id"],
                        "kind": "worker", "reference_access": False, "status": status,
                        "error": error, "output": str(pred), "output_sha256": sha(raw),
                        "source_image_sha256": sample["image_sha256"]})
            predictions[f"sample-{index:03}/prediction.krn"] = sha(raw)
        receipt = {"id": eid, "config": cfg, "samples": len(predictions),
                   "statuses": statuses, "worker": outcome, "evaluated": False,
                   "note": "Frozen worker output; only protected evaluation measures accuracy."}
        # Receipt is published last; a crash while sealing can safely reseal the
        # same completed worker without repeating model calls.
        names = ["assignment.json", "config.json", "source-snapshot.json"]
        names += [f"sample-{i:03}/trace.json" for i, _ in self.selected()]
        atomic_json(folder / "seal.json", {"contract_hash": digest(self.contract),
                    "receipt_hash": digest(receipt), "predictions": predictions,
                    "files": {name: sha((folder / name).read_bytes()) for name in names}})
        atomic_json(folder / "receipt.json", receipt)
        return receipt

    def evaluate(self, eid, remaining_seconds):
        if not re.fullmatch(r"exp-[0-9a-f]{12}", eid):
            raise ValueError("Invalid experiment ID")
        self.assert_originals()
        folder = self.run_dir / "experiments" / eid
        seal = self.verify_seal(folder)
        receipt = json.loads((folder / "receipt.json").read_text())
        if digest(receipt) != seal["receipt_hash"]:
            raise ValueError("Experiment receipt changed")
        # Verify even on a cache hit; never trust a stale evaluation after a mutation.
        cache = folder / "evaluation.json"
        attestation = folder / "evaluation-attestation.json"
        if cache.exists():
            if not attestation.exists():
                # Interrupted after the legacy scorer wrote its cache: recompute.
                cache.unlink()
            else:
                proof = json.loads(attestation.read_text())
                if proof != {"seal_hash": digest(seal), "evaluation_hash": sha(cache.read_bytes())}:
                    raise ValueError("Protected evaluation cache changed")
        result = super().evaluate(eid, remaining_seconds)
        atomic_json(attestation, {"seal_hash": digest(seal), "evaluation_hash": sha(cache.read_bytes())})
        return result
