"""Trusted container PID 1: bounded logs/time/output; child has no root privileges."""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time


def main():
    config=json.loads(Path('/control/job.json').read_text())
    start=time.monotonic();reason=None;total=0
    process=subprocess.Popen(config['command'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        start_new_session=True,user=config['uid'],group=config['gid'],extra_groups=(),cwd='/workspace/output',
        env={**os.environ,'HOME':'/tmp','PYTHONUNBUFFERED':'1'})
    selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
    try:
        while process.poll() is None:
            size=sum(p.stat().st_size for p in Path('/workspace/output').rglob('*') if p.is_file() and not p.is_symlink())
            if time.monotonic()-start>config['max_seconds']:reason='TIME_LIMIT'
            if size>config['max_output_bytes']:reason='OUTPUT_LIMIT'
            if total>16_000_000:reason='LOG_LIMIT'
            if reason:break
            for key,_ in selector.select(.2):
                chunk=os.read(key.fileobj.fileno(),8192)
                if chunk:total+=len(chunk);os.write(1,chunk)
        if reason:os.killpg(process.pid,signal.SIGKILL)
        code=process.wait()
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        os.set_blocking(process.stdout.fileno(),False)
        tail=process.stdout.read(16000)
        if tail:os.write(1,tail)
        Path('/workspace/output/.job-result.json').write_text(json.dumps({
            'exit_code':code,'reason':reason,'elapsed_seconds':time.monotonic()-start}))
        return 124 if reason else (0 if code==0 else 1)
    finally:
        if process.poll() is None:os.killpg(process.pid,signal.SIGKILL)


if __name__=='__main__':raise SystemExit(main())
