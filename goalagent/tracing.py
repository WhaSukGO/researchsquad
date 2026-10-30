"""Local execution traces of observable inputs/outputs, never hidden model reasoning."""
import argparse
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import uuid
from .contracts import atomic_json


def redact(value):
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if re.search(r'^(authorization|password|api_key|access_token|refresh_token|secret)$',k,re.I)
                    else redact(v)) for k,v in value.items()}
    if isinstance(value,list):return [redact(v) for v in value]
    if isinstance(value,str):
        value=re.sub(r'(?i)Bearer\s+[A-Za-z0-9._~+/=-]+','Bearer [REDACTED]',value)
        value=re.sub(r'\b(?:sk-proj-|github_pat_|ghp_)[A-Za-z0-9_-]+','[REDACTED]',value)
        return re.sub(r'(?i)((?:api_key|password|access_token|secret)\s*[=:]\s*)[^\s,;]+',r'\1[REDACTED]',value)
    return value


class Trace:
    def __init__(self, folder):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
    def start(self,kind,name,*,parent=None,agent=None,data=None):
        sid=uuid.uuid4().hex
        self.write(sid,{'id':sid,'parent':parent,'agent':agent,'kind':kind,'name':name,
            'started_at':datetime.now(timezone.utc).isoformat(),'status':'RUNNING','input':data})
        return sid
    def write(self,sid,record):atomic_json(self.folder/(sid+'.json'),redact(record))
    def end(self,sid,output=None,error=None):
        record=json.loads((self.folder/(sid+'.json')).read_text())
        record.update(ended_at=datetime.now(timezone.utc).isoformat(),status='ERROR' if error else 'COMPLETED',
                      output=output,error=str(error) if error else None)
        self.write(sid,record)
    def records(self):
        return sorted([json.loads(p.read_text()) for p in self.folder.glob('*.json')],key=lambda x:x['started_at'])
    def export(self,path):
        records=self.records();payload=json.dumps(records,ensure_ascii=False).replace('<','\\u003c')
        html='''<!doctype html><meta charset="utf-8"><title>ResearchSquad trace</title>
<style>body{font:15px system-ui;margin:30px;background:#101720;color:#e3eaf2}input{padding:12px;width:70%}
details{border:1px solid #34465a;padding:12px;margin:10px 0;border-radius:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere}
.ERROR{border-color:#eb8181}small{color:#9db6ce}</style><h1>ResearchSquad execution trace</h1>
<p>Observable prompts, tool grants, explicit decisions and outcomes. Hidden reasoning is not recorded.
Recorded alternatives are model-reported proposals, not an exhaustive list of internal candidates.</p>
<input id="q" placeholder="Filter agent, tool, job, stage, error…"><div id="rows"></div>
<script type="application/json" id="data">'''+payload+'''</script><script>
const data=JSON.parse(document.getElementById('data').textContent), box=document.getElementById('rows');
function row(r){const d=document.createElement('details');d.className=r.status;const s=document.createElement('summary');
s.textContent=`${r.started_at} | ${r.agent||'host'} | ${r.kind}: ${r.name} | ${r.status}`;d.append(s);
const p=document.createElement('pre');p.textContent=JSON.stringify(r,null,2);d.append(p);return d}
function draw(){box.replaceChildren();const query=document.getElementById('q').value.toLowerCase();
if(query){for(const r of data)if(JSON.stringify(r).toLowerCase().includes(query))box.append(row(r));return}
const nodes=new Map(data.map(r=>[r.id,row(r)]));for(const r of data){const parent=nodes.get(r.parent);(parent||box).append(nodes.get(r.id))}}
document.getElementById('q').oninput=draw;draw();</script>'''
        Path(path).write_text(html,encoding='utf-8');return {'spans':len(records),'path':str(path)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();print(json.dumps(Trace(Path(args.run_dir)/'traces').export(args.output)))
