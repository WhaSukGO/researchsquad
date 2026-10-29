"""Host file boundaries and real Docker isolation for configured agents."""
import os
import pytest
from goalagent.sandbox import DockerSandbox, read_file
from goalagent.team import BASE
from tests.test_team import make, instance, action

POLICY = {'image': BASE, 'network': False, 'memory': '2g', 'cpus': 2}


def test_worker_cannot_read_or_write_outside_workspace(tmp_path):
    team = make(tmp_path / 'team')
    worker = instance(team, 'experiment_engineer')
    workspace = worker.workspace
    secret = tmp_path / "reference.krn"; secret.write_text("protected reference")
    (workspace / "escape").symlink_to(tmp_path, target_is_directory=True)
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


@pytest.mark.skipif(os.environ.get("GOALAGENT_DOCKER_TESTS") != "1", reason="Set GOALAGENT_DOCKER_TESTS=1 for real Docker execution")
def test_real_docker_isolation_timeout_and_log_receipt(tmp_path):
    workspace = tmp_path / "workspace"; (workspace / "inputs").mkdir(parents=True)
    (workspace / "inputs" / "sentinel").write_text("read-only")
    policy = {**POLICY, "network": False}
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


def test_managed_commands_protect_baselines_and_disable_network(tmp_path):
    team = make(tmp_path / 'team')
    agent = instance(team, 'experiment_engineer')
    (agent.workspace / 'baselines').mkdir()
    command = DockerSandbox(agent.workspace, {**POLICY, 'managed_environment': True}).command('python experiment.py')
    assert command[command.index('--network') + 1] == 'none'
    assert any('dst=/workspace/baselines,readonly' in value for value in command)
    assert '--read-only' in command and 'PIP_NO_INDEX=1' in command
    with pytest.raises(ValueError, match='read-only'):
        agent.execute(action('write_file', {'path': 'baselines/result.krn', 'content': 'fake'}), 1)


def test_engineer_reports_missing_environment_and_preserves_progress(tmp_path):
    from tests.test_team import Scripted
    team = make(tmp_path / 'team')
    agent = instance(team, 'experiment_engineer')
    agent.provider = Scripted([
        action('write_file', {'path': 'main.py', 'content': '# progress'}),
        action('request_environment', 'Need scipy==1.16.2; import scipy is unavailable'),
    ])
    outcome = agent.run(lambda: None, lambda: 100)
    assert outcome['status'] == 'environment_blocked'
    assert (agent.workspace / 'main.py').read_text() == '# progress'
    assert 'scipy' in agent.state['history'][-1]['observation']['requirements']
