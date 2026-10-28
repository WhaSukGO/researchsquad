"""Control-flow tests use scripted model decisions; Docker tests run real containers.

No test claims that a scripted transcription is a live model accuracy result.
"""
import copy
import json
import os
from pathlib import Path

import pytest

from goalagent.contracts import atomic_json, digest
from goalagent.coordinator import CoordinatorRunner
from goalagent.research import ResearchTools, DEFAULT_WORKER_POLICY
from goalagent.sandbox import DockerSandbox, workspace_path, read_file
from goalagent.worker import ExperimentWorker


SPEC = json.loads(Path("goals/music-research.json").read_text())
KERN = "**kern\t**mxhm\n*clefG2\t*\n*k[]\t*\n4c\tC:maj\n*-\t*-\n"


def decision(tool, arg="", ids=None):
    return {"tool": tool, "argument": json.dumps(arg) if isinstance(arg, dict) else arg,
            "why": "Test the measured melody failure with a controlled intervention",
            "hypothesis": "Changing this approach reduces melody errors",
            "expected_observation": "Lower melody error rate without a chord regression",
            "evidence_ids": ids or ["goal"]}


def assignment(mode="explore", parent=None, objective="Implement a first candidate recognition pipeline"):
    return {"mode": mode, "parent": parent, "objective": objective,
            "approach": "A generated Python recognition implementation",
            "success_criteria": "Produce valid kern for every assigned input and compare melody errors"}


def action(tool, argument):
    return {"tool": tool, "argument": json.dumps(argument) if isinstance(argument, dict) else argument,
            "why": "Complete the local implementation task"}


class Scripted:
    model = "test-double"
    def __init__(self, actions):
        self.actions = iter(actions)
        self.prompts = []
    def call(self, prompt, *args, **kwargs):
        self.prompts.append(prompt)
        return next(self.actions), {"test_double": True}


class FakeSandbox:
    """No host code execution: the fixture writes a constant prediction only."""
    calls = 0
    def __init__(self, workspace, policy):
        self.workspace = Path(workspace)
    def preflight(self):
        return {"image_id": "fixture"}
    def cleanup(self):
        pass
    def run(self, script, log_path, timeout):
        type(self).calls += 1
        for image in (self.workspace / "inputs").glob("*.png"):
            (self.workspace / "output" / (image.stem + ".krn")).write_text(KERN)
        return {"exit_code": 0, "tail": "fixture execution completed"}


class SmallResearch(ResearchTools):
    def selected(self):
        return [(1, self.manifest[0])]


def worker_actions():
    return [action("write_file", {"path": "main.py", "content": "# fixture source\n"}),
            action("run", "python main.py"),
            action("finish", {"summary": "Produced candidate; accuracy is unmeasured", "files": ["main.py"]})]


def setup_tools(tmp_path, actions=None, sandbox=FakeSandbox, spec=None):
    spec = copy.deepcopy(spec or SPEC)
    provider = Scripted(actions if actions is not None else worker_actions())
    tools = SmallResearch(tmp_path, spec, model="test-double", worker_provider=provider,
                          sandbox_factory=sandbox)
    return tools, provider


def run_candidate(tools, cfg=None):
    cfg = cfg or assignment()
    tools.prepare_assignment(decision("run_experiment", cfg))
    receipt = tools.run_experiment(cfg, lambda: None, lambda: 120)
    return receipt["id"], receipt


def test_generated_worker_scored_by_protected_evaluator_and_cached(tmp_path):
    tools, provider = setup_tools(tmp_path)
    eid, receipt = run_candidate(tools)
    assert receipt["worker"]["status"] == "submitted"
    result = tools.evaluate(eid, lambda: 120)
    assert result["samples"] == 1 and result["parseable"] == 1
    assert result["transposition_failures"] == 0
    assert not result["musician_accepted"] and not result["chord_timing_audited"]
    assert result["melody"]["errors"] > 0  # worker cannot claim its way to success
    tools.run_experiment(assignment(), lambda: pytest.fail("Replayed model call"), lambda: 120)
    assert len(provider.prompts) == 3
    assert tools.evaluate(eid, lambda: 120) == result


@pytest.mark.parametrize("artifact", ["sample-001/prediction.krn", "sample-001/trace.json", "config.json",
                                      "evaluation.json", "receipt.json", "source-snapshot.json"])
def test_tampering_rejected_even_after_evaluation_cache_exists(tmp_path, artifact):
    tools, _ = setup_tools(tmp_path)
    eid, _ = run_candidate(tools)
    tools.evaluate(eid, lambda: 120)
    path = tmp_path / "experiments" / eid / artifact
    path.write_text(path.read_text() + " ")
    # Whitespace-only receipt/source JSON changes may retain semantic identity;
    # force a semantic change for the receipt, whose seal uses canonical JSON.
    if artifact == "receipt.json":
        value = json.loads(path.read_text()); value["samples"] = 999; atomic_json(path, value)
    with pytest.raises(ValueError, match="integrity|changed"):
        tools.evaluate(eid, lambda: 120)


def test_worker_cannot_read_or_write_outside_workspace(tmp_path):
    workspace = tmp_path / "worker" / "workspace"
    (workspace / "inputs").mkdir(parents=True)
    secret = tmp_path / "reference.krn"; secret.write_text("protected reference")
    (workspace / "escape").symlink_to(tmp_path, target_is_directory=True)
    worker = ExperimentWorker(tmp_path / "worker", {}, Scripted([]), DEFAULT_WORKER_POLICY, FakeSandbox)
    for path in ("../reference.krn", str(secret), "escape/reference.krn"):
        with pytest.raises(ValueError):
            worker.execute(action("read_file", {"path": path}), 1)
        with pytest.raises(ValueError):
            worker.execute(action("write_file", {"path": path, "content": "changed"}), 1)
    with pytest.raises(ValueError, match="read-only"):
        worker.execute(action("write_file", {"path": "inputs/answer.krn", "content": "x"}), 1)
    assert secret.read_text() == "protected reference"


def test_nonregular_and_hardlinked_artifacts_rejected(tmp_path):
    (tmp_path / "a").write_text("data")
    os.link(tmp_path / "a", tmp_path / "b")
    with pytest.raises(ValueError, match="regular"):
        read_file(tmp_path, "b")
    os.mkfifo(tmp_path / "pipe")
    with pytest.raises(ValueError, match="regular"):
        read_file(tmp_path, "pipe")


def test_prediction_symlink_is_a_failure_not_label_access(tmp_path):
    class SymlinkSandbox(FakeSandbox):
        def run(self, *args):
            secret = tmp_path / "secret.krn"; secret.write_text("MUST NOT COPY")
            (self.workspace / "output" / "sample-001.krn").symlink_to(secret)
            return {"exit_code": 0}
    tools, _ = setup_tools(tmp_path, sandbox=SymlinkSandbox)
    eid, receipt = run_candidate(tools)
    assert receipt["statuses"]["missing_or_invalid"] == 1
    assert (tmp_path / "experiments" / eid / "sample-001" / "prediction.krn").read_bytes() == b""


def test_pending_worker_action_resumes_without_another_model_decision(tmp_path):
    folder = tmp_path / "worker"
    (folder / "workspace" / "inputs").mkdir(parents=True)
    provider = Scripted([action("finish", {"summary": "done", "files": ["main.py"]})])
    worker = ExperimentWorker(folder, {"objective": "specific"}, provider, DEFAULT_WORKER_POLICY, FakeSandbox)
    worker.state["steps"] = 1
    worker.state["pending"] = action("write_file", {"path": "main.py", "content": "print(42)"})
    worker.save()
    resumed = ExperimentWorker(folder, {"objective": "specific"}, provider, DEFAULT_WORKER_POLICY, FakeSandbox)
    charges = []
    result = resumed.run(lambda: charges.append(1), lambda: 100)
    assert result["status"] == "submitted" and len(charges) == 1
    assert (folder / "workspace" / "main.py").read_text() == "print(42)"


def test_full_coordinator_branching_evidence_and_finished_resume(tmp_path):
    tools, workers = setup_tools(tmp_path, worker_actions() + worker_actions())
    first = assignment()
    first_id = tools.experiment_id(first)
    second = assignment("improve", first_id, "Refine the previous candidate's rhythm representation")
    second_id = tools.experiment_id(second)
    provider = Scripted([
        decision("inspect_dataset"), decision("baseline_summary"), decision("read_evidence", "music-benchmark"),
        decision("run_experiment", first, ["baseline"]), decision("evaluate_experiment", first_id),
        decision("run_experiment", second, [first_id + "-evaluation"]),
        decision("evaluate_experiment", second_id), decision("finish", second_id)])
    runner = CoordinatorRunner(SPEC, tmp_path, provider, tools)
    state = runner.run()
    assert state["status"] == "goal_unmet" and state["model_calls"] == 14
    tree = json.loads((tmp_path / "experiment-tree.json").read_text())
    assert tree[second_id]["parent"] == first_id
    assert tree[second_id]["delta_vs_parent"]["melody_error_rate"] == 0
    assert len(json.loads((tmp_path / "evidence" / "index.json").read_text())) == 8
    assert "prior accuracy" not in workers.prompts[0]
    assert "parent_result" in workers.prompts[3]
    new_provider = Scripted([])
    resumed = CoordinatorRunner(SPEC, tmp_path, new_provider, tools)
    resumed.run()
    assert new_provider.prompts == [] and len(resumed.state["history"]) == 8


def test_branch_contract_and_budget_enforced(tmp_path):
    tools, _ = setup_tools(tmp_path)
    runner = CoordinatorRunner(SPEC, tmp_path, Scripted([]), tools)
    runner.state["known_evidence"] += ["dataset", "baseline", "evidence-source"]
    with pytest.raises(ValueError, match="Parent"):
        runner.validate_action(decision("run_experiment", assignment("improve", "exp-123456abcdef")))
    first = assignment()
    runner.validate_action(decision("run_experiment", first, ["baseline"]))
    with pytest.raises(ValueError, match="Identical"):
        runner.validate_action(decision("run_experiment", first))
    with pytest.raises(ValueError, match="Evaluate"):
        runner.validate_action(decision("run_experiment", assignment(objective="Explore a different recognition method")))


def test_global_model_budget_also_limits_worker_calls(tmp_path):
    spec = copy.deepcopy(SPEC); spec["budget"]["max_model_calls"] = 1
    tools, provider = setup_tools(tmp_path, spec=spec)
    runner = CoordinatorRunner(spec, tmp_path, Scripted([]), tools)
    cfg = assignment(); tools.prepare_assignment(decision("run_experiment", cfg))
    result = tools.run_experiment(cfg, runner.charge_model, runner.remaining_seconds)
    assert runner.state["model_calls"] == 1 and len(provider.prompts) == 1
    assert result["worker"]["status"] == "budget_exhausted"
    snapshot = json.loads((tmp_path / "experiments" / result["id"] / "source-snapshot.json").read_text())
    assert "main.py" in snapshot  # debugging retains partial work


def test_changed_evaluator_contract_refused(tmp_path, monkeypatch):
    tools, _ = setup_tools(tmp_path)
    original = tools.contract_fingerprint
    monkeypatch.setattr(tools, "contract_fingerprint", lambda: {**original(), "changed": True})
    with pytest.raises(ValueError, match="evaluator changed"):
        tools.assert_originals()


def test_failed_branch_can_be_debugged_without_fake_accuracy(tmp_path):
    actions = [action("write_file", {"path": "main.py", "content": "# failed candidate\n"}),
               action("finish", {"summary": "Implementation incomplete", "files": ["main.py"]}),
               action("run", "python main.py"),
               action("finish", {"summary": "Repaired the execution", "files": ["main.py"]})]
    tools, _ = setup_tools(tmp_path, actions)
    parent, _ = run_candidate(tools)
    runner = CoordinatorRunner(SPEC, tmp_path, Scripted([]), tools)
    runner.state["experiments"] = [parent]
    runner.state["known_evidence"] += ["dataset", "baseline", "evidence-source", parent]
    cfg = assignment("debug", parent, "Repair the missing prediction-writing stage of the parent")
    d = decision("run_experiment", cfg, [parent])
    runner.validate_action(d)
    tools.prepare_assignment(d)
    receipt = tools.run_experiment(cfg, lambda: None, lambda: 100)
    assert receipt["statuses"]["ok"] == 1
    child = tmp_path / "experiments" / receipt["id"]
    assert (child / "worker" / "workspace" / "main.py").read_text() == "# failed candidate\n"
    assert not runner.state["evaluations"]  # execution repair is not a measurement


def test_assignments_require_measurement_citations_and_specific_goals(tmp_path):
    tools, _ = setup_tools(tmp_path)
    runner = CoordinatorRunner(SPEC, tmp_path, Scripted([]), tools)
    runner.state["known_evidence"] += ["dataset", "baseline", "evidence-source"]
    with pytest.raises(ValueError, match="must cite baseline"):
        runner.validate_action(decision("run_experiment", assignment(), ["goal"]))
    with pytest.raises(ValueError, match="specific worker objective"):
        runner.validate_action(decision("run_experiment", assignment(objective=SPEC["goal"]), ["baseline"]))


def test_old_evidence_is_retrievable_after_context_compaction(tmp_path):
    tools, _ = setup_tools(tmp_path)
    runner = CoordinatorRunner(SPEC, tmp_path, Scripted([]), tools)
    for step in range(1, 12):
        runner.state["history"].append({"step": step, "decision": decision("inspect_dataset"),
                                        "observation": {"id": f"evidence-{step}", "content": "x" * 15000}})
    context = runner.context()
    assert len(context["history"]) == 8
    assert context["history"][0]["observation"]["truncated"]
    first = tools.execute("read_record", json.dumps({"id": "evidence-1", "offset": 0}), None, None)
    second = tools.execute("read_record", json.dumps({"id": "evidence-1", "offset": 6000}), None, None)
    assert len(first["text"]) == len(second["text"]) == 6000
    assert first["total_characters"] > 15000
    with pytest.raises(ValueError, match="Unknown evidence"):
        tools.find_record("../../research/data/answer.krn")


def test_pending_coordinator_reuses_completed_worker_receipt(tmp_path):
    tools, provider = setup_tools(tmp_path)
    cfg = assignment()
    eid, _ = run_candidate(tools, cfg)
    runner = CoordinatorRunner(SPEC, tmp_path, Scripted([]), tools)
    runner.state["steps"] = 1
    runner.state["experiments"] = [eid]
    runner.state["pending"] = {"step": 1, "decision": decision("run_experiment", cfg)}
    runner.save()
    runner.run(stop_after=1)
    assert len(provider.prompts) == 3
    assert runner.state["pending"] is None
    assert runner.state["history"][0]["observation"]["id"] == eid


def test_research_audit_detects_modified_evidence(tmp_path):
    from goalagent.audit import audit
    provider = Scripted(worker_actions())
    tools = ResearchTools(tmp_path, SPEC, "test-double", provider, FakeSandbox)
    cfg = assignment(); eid = tools.experiment_id(cfg)
    coordinator = Scripted([decision("inspect_dataset"), decision("baseline_summary"),
                           decision("read_evidence", "music-benchmark"),
                           decision("run_experiment", cfg, ["baseline"]),
                           decision("evaluate_experiment", eid), decision("finish", eid)])
    runner = CoordinatorRunner(SPEC, tmp_path, coordinator, tools)
    runner.run()
    assert audit(tmp_path)["all_checks_passed"]
    entry = json.loads((tmp_path / "evidence" / "index.json").read_text())[0]
    (tmp_path / entry["record"]).write_text("{}")
    assert not audit(tmp_path)["checks"]["protected_research_artifacts_intact"]


def test_legacy_runs_cannot_be_silently_migrated(tmp_path):
    from goalagent.runner import AgentRunner
    from tests.test_goalagent import Domain
    AgentRunner(SPEC, tmp_path, Scripted([decision("finish")]), Domain()).run()
    tools, _ = setup_tools(tmp_path)
    with pytest.raises(ValueError, match="new run directory"):
        CoordinatorRunner(SPEC, tmp_path, Scripted([]), tools)


def test_legacy_runner_cannot_resume_research_state(tmp_path):
    from goalagent.runner import AgentRunner
    tools, _ = setup_tools(tmp_path)
    CoordinatorRunner(SPEC, tmp_path, Scripted([decision("finish")]), tools).run()
    with pytest.raises(ValueError, match="goalagent.coordinator"):
        AgentRunner(SPEC, tmp_path, Scripted([]), tools)


@pytest.mark.skipif(os.environ.get("GOALAGENT_DOCKER_TESTS") != "1", reason="Set GOALAGENT_DOCKER_TESTS=1 for real Docker execution")
def test_real_docker_isolation_timeout_and_log_receipt(tmp_path):
    workspace = tmp_path / "workspace"; (workspace / "inputs").mkdir(parents=True)
    (workspace / "inputs" / "sentinel").write_text("read-only")
    policy = {**DEFAULT_WORKER_POLICY, "network": False}
    sandbox = DockerSandbox(workspace, policy)
    sandbox.preflight()
    host_secret = tmp_path / "secret"; host_secret.write_text("must not be visible")
    script = "\n".join([
        "test ! -e /var/run/docker.sock || exit 11",
        f"test ! -e '{host_secret}' || exit 12",
        "test ! -e /workspace/research || exit 13",
        "if echo hacked > /workspace/inputs/sentinel; then exit 14; fi",
        "if echo hacked > /etc/worker-test; then exit 15; fi",
        "python -c 'print(\"x\" * 20000)'",
    ])
    result = sandbox.run(script, tmp_path / "command.log", 20)
    assert result["exit_code"] == 0 and len(result["tail"]) <= 4000
    assert (tmp_path / "command.log").stat().st_size > 20000
    assert (workspace / "inputs" / "sentinel").read_text() == "read-only"
    timeout = sandbox.run("sleep 30", tmp_path / "timeout.log", 0.5)
    assert timeout["interrupted"] is True


@pytest.mark.skipif(os.environ.get("GOALAGENT_DOCKER_TESTS") != "1", reason="Set GOALAGENT_DOCKER_TESTS=1 for real Docker execution")
def test_real_generated_script_to_protected_score(tmp_path):
    script = "from pathlib import Path\nfor p in Path('inputs').glob('*.png'):\n    (Path('output') / (p.stem + '.krn')).write_text(" + repr(KERN) + ")\n"
    actions = [action("write_file", {"path": "recognize.py", "content": script}),
               action("run", "python recognize.py"),
               action("finish", {"summary": "Executed a fixture recognizer", "files": ["recognize.py"]})]
    tools, _ = setup_tools(tmp_path, actions, DockerSandbox)
    eid, receipt = run_candidate(tools)
    assert receipt["statuses"]["ok"] == 1
    assert tools.evaluate(eid, lambda: 120)["parseable"] == 1
