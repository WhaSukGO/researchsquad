"""Actual search/PDF/code transport readiness; no agent discovery or decisions."""
import json
from pathlib import Path
import subprocess
import urllib.request
from goalagent.team import Team
from goalagent.agent import Agent
from goalagent.contracts import atomic_json

def verify(folder):
    folder=Path(folder).resolve()
    image=subprocess.run(['docker','image','inspect','--format','{{.Id}}','researchsquad-sources:pypdf6.21.4'],capture_output=True,text=True,check=True).stdout.strip()
    task={'goal':'Source transport readiness, not agent research','inputs':{},'network':True,'source_reader_image':image,
        'budget':{'max_calls':1,'max_seconds':300,'max_assignments':2,'max_depth':1}}
    team=Team(folder,task);c=team.definitions['researcher'];agent=Agent(folder/'agents/transport',{'depth':1},None,team.policy(c),c,team.registry)
    sha=json.load(urllib.request.urlopen(urllib.request.Request('https://api.github.com/repos/pytorch/examples/commits/main',headers={'User-Agent':'ResearchSquad/1.0'}),timeout=30))['sha']
    operations=[('web_search',json.dumps({'provider':'crossref','query':'dropout neural networks'})),
        ('web_search',json.dumps({'provider':'github','query':'fashion-mnist pytorch'})),
        ('web_fetch','https://www.jmlr.org/papers/volume15/srivastava14a/srivastava14a.pdf'),
        ('web_fetch','https://raw.githubusercontent.com/pytorch/examples/'+sha+'/mnist/main.py')]
    results=[]
    try:
        for step,(tool,arg) in enumerate(operations,1):
            agent.state['steps']=step
            result=agent.execute({'tool':tool,'argument':arg,'why':'Maintainer transport readiness only; not an agent choice'},90)
            assert result['status']=='retrieved',result
            if step==3:assert result['format']=='pdf' and result['pages_extracted']>2
            if step==4:assert 'class Net' in (agent.workspace/result['text_file']).read_text()
            results.append({k:v for k,v in result.items() if k not in ('text_excerpt','result')})
        atomic_json(folder/'verification.json',{'scope':'Actual network/parser readiness with zero model calls','results':results})
        print(json.dumps(results,indent=2))
    finally:team.close()

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);a=p.parse_args();verify(a.run_dir)
