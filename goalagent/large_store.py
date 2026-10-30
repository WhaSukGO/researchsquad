"""Streaming immutable blobs for datasets/models, independent of text artifact limits."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from .contracts import atomic_json, digest
from .sandbox import workspace_path


class LargeStore:
    def __init__(self,folder,max_bytes=8_000_000_000):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True);self.max_bytes=max_bytes
    def register(self,source,*,kind,metadata=None):
        source=Path(source);fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        temporary=None
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>self.max_bytes:
                raise ValueError('Expected bounded regular large artifact, no links')
            h=hashlib.sha256();size=0
            with tempfile.NamedTemporaryFile(dir=self.folder,delete=False) as out:
                temporary=Path(out.name)
                with os.fdopen(fd,'rb',closefd=False) as src:
                    while chunk:=src.read(1024*1024):
                        size+=len(chunk)
                        if size>self.max_bytes:raise ValueError('Large artifact exceeds budget')
                        h.update(chunk);out.write(chunk)
                out.flush();os.fsync(out.fileno())
            if size!=info.st_size or os.fstat(fd).st_mtime_ns!=info.st_mtime_ns:
                raise ValueError('Source changed while registering')
            record={'kind':kind,'bytes':size,'sha256':h.hexdigest(),'metadata':metadata or {}}
            bid='blob-'+digest(record);dest=self.folder/bid;dest.mkdir(exist_ok=True)
            if not (dest/'content').exists():temporary.replace(dest/'content')
            record['id']=bid;atomic_json(dest/'record.json',record)
            self.verify(record)
            return record
        finally:
            os.close(fd)
            if temporary and temporary.exists():temporary.unlink()
    def verify(self,record):
        if record['id']!='blob-'+digest({k:v for k,v in record.items() if k!='id'}):raise ValueError('Blob metadata changed')
        folder=workspace_path(self.folder,record['id']);path=workspace_path(folder,'content')
        if path.stat().st_size!=record['bytes']:raise ValueError('Blob size changed')
        h=hashlib.sha256()
        with path.open('rb') as f:
            while chunk:=f.read(1024*1024):h.update(chunk)
        if h.hexdigest()!=record['sha256']:raise ValueError('Blob content changed')
        return path
