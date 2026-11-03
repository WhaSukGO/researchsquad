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

    def preflight(self):
        if not shutil.which('codex'):
            raise RuntimeError('Codex CLI is not on PATH. Start a login shell or configure the provider executable before dispatch; no model call was made.')

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


class MetaProvider:
    """Meta Model API (OpenAI-compatible chat completions, constrained JSON output). Key from META_API_KEY or MODEL_API_KEY."""
    URL = 'https://api.meta.ai/v1/chat/completions'

    def __init__(self, model=None, effort='low'):
        self.model = model or 'muse-spark-1.3'
        self.effort = effort
        self.key = os.environ.get('META_API_KEY') or os.environ.get('MODEL_API_KEY')

    def preflight(self):
        if not self.key:
            raise RuntimeError('META_API_KEY (or MODEL_API_KEY) is not set; no model call was made.')

    def _post(self, body, timeout):
        """One HTTP round trip; retries 429/5xx/network errors with backoff. Other 4xx raise at once."""
        import random, urllib.request, urllib.error
        data = json.dumps(body).encode()
        for attempt in range(5):
            request = urllib.request.Request(self.URL, data=data, method='POST', headers={
                'Authorization': f'Bearer {self.key}', 'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                text = error.read().decode(errors='replace')[:2000]
                if error.code != 429 and error.code < 500:
                    raise RuntimeError(f'Meta API {error.code}: {text}')
                wait = float(error.headers.get('Retry-After') or 0) or 2 ** attempt + random.random()
                last = f'Meta API {error.code}: {text}'
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                wait = 2 ** attempt + random.random(); last = f'Meta API unreachable: {error}'
            time.sleep(wait)
        raise RuntimeError(last + ' (after 5 attempts)')

    def call(self, prompt, schema, folder, *, image=None, timeout=180):
        if image: raise ValueError('MetaProvider does not take images')
        folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=True)
        (folder/'schema.json').write_text(json.dumps(schema)); (folder/'prompt.txt').write_text(prompt)
        body = {'model': self.model, 'messages': [{'role': 'user', 'content': prompt}], 'reasoning_effort': self.effort,
                'response_format': {'type': 'json_schema', 'json_schema': {'name': 'action', 'schema': schema, 'strict': True}}}
        # ponytail: one non-streaming request; switch to stream=True if 504s appear on long calls
        start = time.monotonic()
        status, reply = self._post(body, None if timeout is None or math.isinf(timeout) else timeout)
        content = reply['choices'][0]['message']['content'] or ''
        (folder/'raw.json').write_text(json.dumps(reply)); (folder/'answer.json').write_text(content)
        metadata = {'provider': 'meta-api', 'model': self.model, 'reasoning_effort': self.effort,
                    'elapsed_seconds': time.monotonic()-start, 'exit_code': status, 'usage': reply.get('usage', {}),
                    'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(), 'image_sha256': None,
                    'context_isolation': 'single user message: explicit prompt and schema only', 'os_read_isolation': True,
                    'unexpected_tool_events': [], 'billing': 'Meta Model API pay-as-you-go; usage above is the API report'}
        (folder/'metadata.json').write_text(json.dumps(metadata, indent=2))
        return extract_json(content), metadata


def extract_json(text):
    """The model occasionally prefixes prose to the JSON object; parse from the first brace."""
    start = text.find('{')
    if start < 0: raise RuntimeError(f'Model returned no JSON object: {text[:200]!r}')
    return json.JSONDecoder().raw_decode(text[start:])[0]


def provider_for(model, effort):
    """Pick the provider from the model name (muse-* = Meta) or RSQ_PROVIDER=meta; Codex CLI otherwise."""
    if (model or '').startswith('muse-') or os.environ.get('RSQ_PROVIDER') == 'meta':
        return MetaProvider(model, effort)
    return CodexProvider(model, effort)
