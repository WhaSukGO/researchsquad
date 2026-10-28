"""Model calls through the user's authenticated Codex CLI, with tools disabled.

The model proposes JSON; the host, not the model process, executes registered tools.
"""
from __future__ import annotations
import hashlib
import math
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import tomllib
import tempfile


def configured_model():
    path = Path(os.environ.get('CODEX_HOME', str(Path.home()/'.codex'))) / 'config.toml'
    return tomllib.loads(path.read_text()).get('model') if path.exists() else None


def run_process(command, *, cwd, stdin='', timeout=180):
    """Kill the process group on timeout, not just the immediate child."""
    process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, err = process.communicate(stdin, timeout=None if timeout is None or math.isinf(timeout) else timeout)
        return process.returncode, out, err
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise


class CodexProvider:
    def __init__(self, model=None, effort='low'):
        self.model = model or configured_model()
        self.effort = effort

    def call(self, prompt, schema, folder, *, image=None, timeout=180):
        folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=True)
        schema_file = folder/'schema.json'; schema_file.write_text(json.dumps(schema))
        (folder/'prompt.txt').write_text(prompt)
        output = folder/'answer.json'
        # A fresh directory OUTSIDE the project avoids ancestor instructions and
        # neighboring answer files. This is context isolation, not an OS read jail.
        command = [shutil.which('codex') or 'codex', 'exec', '--ignore-user-config',
                   '--sandbox', 'read-only', '--skip-git-repo-check', '--ephemeral',
                   '-c', 'features.shell_tool=false', '-c', 'web_search="disabled"',
                   '-c', f'model_reasoning_effort="{self.effort}"', '--json',
                   ]
        if self.model: command += ['--model', self.model]
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix='score-agent-input-') as isolated:
            work = Path(isolated)
            shutil.copyfile(schema_file, work/'schema.json')
            command += ['--output-schema', str(work/'schema.json'), '-o', str(work/'answer.json')]
            if image:
                shutil.copyfile(image, work/'input.png')
                command += ['--image', str(work/'input.png')]
            command += ['-']
            code, stdout, stderr = run_process(command, cwd=work, stdin=prompt, timeout=timeout)
            if (work/'answer.json').exists():shutil.copyfile(work/'answer.json',output)
        (folder/'events.jsonl').write_text(stdout)
        (folder/'stderr.log').write_text(stderr)
        usage = {}; tool_events = []
        for line in stdout.splitlines():
            try: event = json.loads(line)
            except json.JSONDecodeError: continue
            if event.get('type') == 'turn.completed': usage = event.get('usage', {})
            item = event.get('item', {})
            # Fail closed for new or unrecognized tool event types as well.
            if item.get('type') and item['type'] not in {'agent_message','reasoning'}:
                tool_events.append(item.get('type'))
        metadata = {'provider':'codex-cli','model':self.model,'reasoning_effort':self.effort,
                    'elapsed_seconds':time.monotonic()-start,'exit_code':code,'usage':usage,
                    'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                    'image_sha256':hashlib.sha256(Path(image).read_bytes()).hexdigest() if image else None,
                    'context_isolation':'fresh temporary directory outside the project; only explicit prompt, schema and optional image',
                    'os_read_isolation':False,
                    'unexpected_tool_events':tool_events,'billing':'Uses existing Codex account; monetary cost unavailable'}
        (folder/'metadata.json').write_text(json.dumps(metadata,indent=2))
        if code or not output.exists():
            raise RuntimeError(f'Codex call failed (exit {code}); see {folder}/stderr.log')
        if tool_events:
            raise RuntimeError('Model used an unregistered tool; refusing result')
        data = json.loads(output.read_text())
        return data, metadata
