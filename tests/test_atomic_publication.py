"""Publication boundaries: failures never turn partial data into accepted artifacts."""
import errno
import json
import os
from pathlib import Path

import pytest

from goalagent.artifacts import ArtifactStore
from goalagent.contracts import atomic_bytes,atomic_json


@pytest.mark.parametrize('kind',['json','bytes'])
def test_publication_pins_parent_for_create_replace_and_cleanup(tmp_path,monkeypatch,kind):
    folder=tmp_path/'live';folder.mkdir()
    previous=tmp_path/'opened-parent'
    replace=os.replace
    observed=[]
    def move_parent(source,target,*,src_dir_fd,dst_dir_fd):
        assert src_dir_fd==dst_dir_fd
        observed.append(os.fstat(src_dir_fd).st_ino)
        folder.rename(previous);folder.mkdir()
        (folder/target).write_bytes(b'unrelated-new-mount-view')
        return replace(source,target,src_dir_fd=src_dir_fd,dst_dir_fd=dst_dir_fd)
    monkeypatch.setattr('goalagent.contracts.os.replace',move_parent)
    if kind=='json':atomic_json(folder/'value',{'complete':True})
    else:atomic_bytes(folder/'value',b'complete-binary')
    assert observed==[previous.stat().st_ino]
    assert (previous/'value').read_bytes()==(b'{\n  "complete": true\n}' if kind=='json' else b'complete-binary')
    assert (folder/'value').read_bytes()==b'unrelated-new-mount-view'
    assert sorted(p.name for p in previous.iterdir())==['value']


@pytest.mark.parametrize('failure',['exdev','write','fsync'])
def test_failed_artifact_publication_has_no_record_or_partial_target(tmp_path,monkeypatch,failure):
    if failure=='exdev':
        def blocked(*args,**kwargs):raise OSError(errno.EXDEV,'Injected actual cross-mount refusal')
        monkeypatch.setattr('goalagent.contracts.os.replace',blocked)
    elif failure=='fsync':
        def blocked(*args):raise OSError(errno.ENOSPC,'Injected fsync failure')
        monkeypatch.setattr('goalagent.contracts.os.fsync',blocked)
    else:
        def blocked(path,value):
            from goalagent.contracts import _atomic_file
            def partial(stream):
                stream.write(b'partial');raise OSError(errno.ENOSPC,'Injected partial write')
            _atomic_file(path,partial,mode=0o644)
        monkeypatch.setattr('goalagent.artifacts.atomic_bytes',blocked)
    with pytest.raises(OSError):ArtifactStore(tmp_path/'artifacts').register(b'complete-data',owner='test',path='result.bin')
    assert list((tmp_path/'artifacts').glob('*/content'))==[]
    assert list((tmp_path/'artifacts').glob('*/record.json'))==[]
    assert list((tmp_path/'artifacts').glob('*/.*.tmp'))==[]


def test_json_exdev_is_not_retried_or_copied(tmp_path,monkeypatch):
    path=tmp_path/'state.json';atomic_json(path,{'previous':True});calls=[]
    def blocked(*args,**kwargs):
        calls.append(1);raise OSError(errno.EXDEV,'Injected distinct mount')
    monkeypatch.setattr('goalagent.contracts.os.replace',blocked)
    with pytest.raises(OSError) as error:atomic_json(path,{'next':True})
    assert error.value.errno==errno.EXDEV and len(calls)==1
    assert json.loads(path.read_text())=={'previous':True}
    assert sorted(p.name for p in tmp_path.iterdir())==['state.json']
