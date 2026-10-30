"""Worker execution boundary. Only a disposable workspace is mounted in Docker.

The host owns policy, logs, labels and evaluator code. Workers get no Docker
socket, host credentials, project checkout or host environment variables.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import subprocess
import time


def workspace_path(root, relative):
    """Reject traversal and every symlink component, including the final file."""
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise ValueError("Expected a relative workspace path")
    parts = PurePosixPath(relative).parts
    if PurePosixPath(relative).is_absolute() or ".." in parts or not parts:
        raise ValueError("Path escapes workspace")
    root = Path(root).resolve()
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlinks are not accepted at the host boundary")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Path escapes workspace")
    return path


def read_file(root, relative, limit=1_000_000):
    path = workspace_path(root, relative)
    # Detached jobs can still mutate output directories: pin every parent with
    # openat/O_NOFOLLOW, not just the final filename, to avoid symlink races.
    relative_parts=path.relative_to(Path(root).resolve()).parts
    directory=os.open(Path(root).resolve(),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in relative_parts[:-1]:
            next_directory=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            os.close(directory);directory=next_directory
        fd=os.open(relative_parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
    finally:os.close(directory)
    try:
        import stat
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise ValueError("Expected a bounded regular file with one link")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            result = stream.read(limit + 1)
        if len(result) > limit:
            raise ValueError("File exceeds artifact size limit")
        return result
    finally:
        os.close(fd)


def log_summary(path):
    """Bounded first diagnostic plus tail; full output remains retrievable on disk."""
    path = Path(path)
    first = ''
    with path.open('rb') as stream:
        for raw in stream:
            line = raw.decode('utf-8', errors='replace').strip()
            if any(word in line.lower() for word in ('error', 'exception', 'failed', 'not found', 'denied')):
                first = line[:1200]
                break
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - 4000))
        tail = stream.read(4000).decode('utf-8', errors='replace')
    return {'log': str(path), 'bytes': path.stat().st_size, 'first_diagnostic': first, 'tail': tail}


class DockerSandbox:
    def __init__(self, workspace, policy):
        self.workspace = Path(workspace).resolve()
        self.policy = policy
        self.name = "goalagent-" + hashlib.sha256(str(self.workspace).encode()).hexdigest()[:20]

    def preflight(self):
        subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                       check=True, capture_output=True, timeout=15)
        result = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", self.policy["image"]],
                                check=True, capture_output=True, text=True, timeout=15)
        return {"image_id": result.stdout.strip(), "policy": self.policy}

    def cleanup(self):
        # A deterministic per-workspace name also cleans up a container orphaned
        # when the host process died. Never remove containers owned by other runs.
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True, timeout=15)

    def command(self, script):
        command = ["docker", "run", "--rm", "--name", self.name,
                "--network", "bridge" if self.policy.get("network", False) else "none",
                "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--pids-limit", "128", "--memory", self.policy["memory"],
                "--cpus", str(self.policy["cpus"]), "--user", f"{os.getuid()}:{os.getgid()}",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m", "--env", "HOME=/tmp",
                "--env", "PYTHONPATH=/workspace/vendor", "--workdir", "/workspace",
                "--mount", f"type=bind,src={self.workspace},dst=/workspace",
                "--mount", f"type=bind,src={self.workspace / 'inputs'},dst=/workspace/inputs,readonly",
                ]
        if (self.workspace / 'baselines').exists():
            command += ['--mount', f'type=bind,src={self.workspace / "baselines"},dst=/workspace/baselines,readonly']
        if self.policy.get('managed_environment'):
            command += ['--env', 'TMPDIR=/workspace/tmp', '--env', 'PYTHONNOUSERSITE=1',
                        '--env', 'PIP_NO_INDEX=1', '--env', 'PIP_REQUIRE_VIRTUALENV=1']
        return command + [self.policy['image'], '/bin/sh', '-lc', script]

    def run(self, script, log_path, timeout):
        self.cleanup()
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        timed_out = False
        # Stream to disk, not PIPE/communicate: large logs never enter RAM/context.
        # A hard log cap terminates a command that would fill the artifact store.
        with log_path.open("wb") as log:
            process = subprocess.Popen(self.command(script), stdout=log, stderr=subprocess.STDOUT)
            try:
                while process.poll() is None:
                    if time.monotonic() - started >= timeout or log_path.stat().st_size > 16_000_000:
                        timed_out = True
                        self.cleanup()
                        process.kill()
                        break
                    time.sleep(0.1)
                process.wait(timeout=15)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                self.cleanup()
        return {"exit_code": process.returncode, "interrupted": timed_out,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                **log_summary(log_path)}
