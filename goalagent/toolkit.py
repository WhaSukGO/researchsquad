"""Host-owned tool implementations shared by configured agents."""
import json
from dataclasses import dataclass
from pathlib import Path
from .contracts import atomic_json, digest
from .sandbox import workspace_path, read_file

@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: object
    version: str = "1"

class ToolRegistry:
    def __init__(self): self.tools = {}
    def register(self, tool):
        if tool.name in self.tools: raise ValueError("Duplicate tool: " + tool.name)
        self.tools[tool.name] = tool
    def catalog(self, names):
        return [{"name": n, "description": self.tools[n].description, "version":self.tools[n].version} for n in names]
    def execute(self, agent, action, timeout):
        if not isinstance(action,dict) or set(action)!={"tool","argument","why"} or not all(isinstance(v,str) for v in action.values()):
            raise ValueError("Invalid action")
        name=action["tool"]
        if name not in agent.config["tools"] or name not in self.tools: raise ValueError("Tool not granted: " + name)
        return self.tools[name].handler(agent,action,timeout)

def workspace_action(self, action, timeout):
    if set(action) != {"tool", "argument", "why"} or not all(isinstance(v, str) for v in action.values()):
        raise ValueError("Invalid worker action")
    tool, argument = action["tool"], action["argument"]
    if tool == 'request_environment':
        if self.config['id']=='music_experiment' and not self.policy.get('managed_environment'):
            raise ValueError('Environment escalation is unavailable in legacy mode')
        if not 10 <= len(argument) <= 2000:
            raise ValueError('Describe the missing dependency and observed failure')
        self.state['status'] = 'environment_blocked'
        return {'status':'environment_blocked','requirements':argument}
    if tool == "run":
        if len(argument) > 32000:
            raise ValueError("Command too large")
        return self.sandbox.run(argument, self.folder / "logs" / f'{self.state["steps"]:03}.log', timeout)
    if tool == "write_file":
        data = json.loads(argument)
        if set(data) != {"path", "content"} or not isinstance(data["content"], str):
            raise ValueError("Invalid write_file fields")
        path = workspace_path(self.workspace, data["path"])
        if any(path.is_relative_to(self.workspace / name) for name in ("inputs", "baselines")):
            raise ValueError("Inputs are read-only")
        if len(data["content"].encode()) > 1_000_000:
            raise ValueError("File too large")
        if path.exists():
            read_file(self.workspace, data["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data["content"])
        self.state.setdefault("written_files", [])
        if data["path"] not in self.state["written_files"]:
            self.state["written_files"].append(data["path"])
        return {"written": data["path"]}
    if tool == "read_file":
        data = json.loads(argument)
        offset, limit = data.get("offset", 0), data.get("limit", 4000)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 8000:
            raise ValueError("Invalid read window")
        raw = read_file(self.workspace, data["path"], limit=16_000_000)
        return {"path": data["path"], "bytes": len(raw), "offset": offset,
                "text": raw[offset:offset + limit].decode("utf-8", errors="replace")}
    if tool == "view_image":
        from PIL import Image
        raw = read_file(self.workspace, argument, limit=16_000_000)
        import io
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 20_000_000:
                raise ValueError("Image exceeds the viewing pixel limit")
            image.verify()
        # Copy to host-owned storage: never pass a worker-controlled path to the CLI.
        target = self.folder / "view.png"
        with Image.open(io.BytesIO(raw)) as image:
            image.convert("RGB").save(target)
        self.state["image"] = str(target)
        return {"attached_image": argument}
    if tool == "finish":
        data = json.loads(argument)
        if set(data) != {"summary", "files"} or not isinstance(data["summary"], str):
            raise ValueError("Invalid finish fields")
        if not isinstance(data["files"], list) or not 1 <= len(data["files"]) <= 32:
            raise ValueError("Submit 1–32 source/config files for reproducibility")
        files = {}
        for relative in data["files"]:
            if not isinstance(relative, str):
                raise ValueError("Submit source/config files, not input or output data")
            target = workspace_path(self.workspace, relative)
            if any(target.is_relative_to(self.workspace / name) for name in ("inputs", "output", "baselines")):
                raise ValueError("Submit source/config files, not input or output data")
            raw = read_file(self.workspace, relative)
            files[relative] = raw.decode("utf-8")
            if sum(len(content.encode()) for content in files.values()) > 8_000_000:
                raise ValueError("Source snapshot exceeds 8 MB")
        # Host-owned source snapshot, never mounted in the worker container.
        atomic_json(self.folder / "source-snapshot.json", files)
        self.state["status"] = "submitted"
        return {"summary": data["summary"][:4000], "source_files": list(files)}
    raise ValueError("Unregistered worker tool")


DESCRIPTIONS = {
 "read_file": 'JSON {path, offset?:0, limit?:4000}; read a bounded workspace file.',
 "write_file": 'JSON {path, content}; write a workspace text file; inputs are read-only.',
 "run": 'Shell command in a disposable Docker container. Full logs stay on disk. Download/install only if the execution policy permits.',
 "view_image": 'Relative workspace image path; attach image to next model call.',
 "request_environment": 'Describe missing capability and observed failure. End assignment with environment_blocked; lead handles repair.',
 "finish": 'JSON {summary, files:[relative source/report paths]}; submit frozen reproducible artifacts. This does not certify the system goal.',
 "list_files": 'JSON {path?:"."}; list workspace files without following symlinks (up to 200).',
 "search_files": 'JSON {text, path?:"."}; literal text search in bounded regular workspace files (up to 50 matching lines).',
}

def inspect_files(agent, action, timeout):
    data=json.loads(action['argument']); root=workspace_path(agent.workspace,data.get('path','.'))
    files=[];matches=[]
    import os
    for directory,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()][:100]
        for name in names:
            p=Path(directory)/name
            if p.is_symlink():continue
            relative=str(p.relative_to(agent.workspace));files.append(relative)
            if action['tool']=='search_files':
                needle=data.get('text')
                if not isinstance(needle,str) or not needle:raise ValueError('Expected search text')
                try:raw=read_file(agent.workspace,relative,limit=250000).decode('utf-8')
                except (OSError,ValueError,UnicodeError):continue
                for number,line in enumerate(raw.splitlines(),1):
                    if needle in line:matches.append({'path':relative,'line':number,'text':line[:300]})
                    if len(matches)>=50:break
            if len(files)>=200 or len(matches)>=50:return {'files':files,'matches':matches,'truncated':True}
    return {'files':files,'matches':matches,'truncated':False}

def default_registry():
    registry=ToolRegistry()
    for name,description in DESCRIPTIONS.items():
        registry.register(Tool(name,description,inspect_files if name in {'list_files','search_files'} else workspace_action))
    return registry
