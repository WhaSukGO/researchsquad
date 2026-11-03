"""MetaProvider: request shape, retry on 429, metadata; provider_for picks by model name."""
import io, json, urllib.error, urllib.request
import pytest
from goalagent import provider as P

SCHEMA={'type':'object','properties':{'tool':{'type':'string','enum':['finish']},'argument':{'type':'string'},'why':{'type':'string'}},'required':['tool','argument','why'],'additionalProperties':False}
ANSWER={'tool':'finish','argument':'{"files":["note.md"]}','why':'done'}

class Reply:
    def __init__(self,body,status=200):self.status=status;self.body=json.dumps(body).encode()
    def read(self):return self.body
    def __enter__(self):return self
    def __exit__(self,*a):return False

def test_call_and_retry(tmp_path,monkeypatch):
    monkeypatch.setenv('META_API_KEY','LLM_1_secret');monkeypatch.setattr(P.time,'sleep',lambda s:None)
    seen=[]
    def fake_urlopen(request,timeout=None):
        seen.append(request)
        if len(seen)==1:raise urllib.error.HTTPError(request.full_url,429,'rate',{'Retry-After':'0'},io.BytesIO(b'{"error":"slow down"}'))
        return Reply({'choices':[{'message':{'content':json.dumps(ANSWER)}}],'usage':{'prompt_tokens':10,'completion_tokens':5}})
    monkeypatch.setattr(urllib.request,'urlopen',fake_urlopen)
    action,meta=P.MetaProvider('muse-spark-1.3','high').call('prompt',SCHEMA,tmp_path/'turn')
    assert action==ANSWER and len(seen)==2
    body=json.loads(seen[-1].data);assert body['model']=='muse-spark-1.3' and body['reasoning_effort']=='high' and body['response_format']['json_schema']['schema']==SCHEMA and body['response_format']['json_schema']['strict'] is True
    assert seen[-1].get_header('Authorization')=='Bearer LLM_1_secret'
    assert meta['provider']=='meta-api' and meta['usage']['prompt_tokens']==10 and meta['exit_code']==200
    assert json.loads((tmp_path/'turn'/'answer.json').read_text())==ANSWER and (tmp_path/'turn'/'metadata.json').exists()

def test_client_error_raises(tmp_path,monkeypatch):
    monkeypatch.setenv('META_API_KEY','k')
    def fake(request,timeout=None):raise urllib.error.HTTPError(request.full_url,400,'bad',{},io.BytesIO(b'{"error":"unsupported"}'))
    monkeypatch.setattr(urllib.request,'urlopen',fake)
    with pytest.raises(RuntimeError,match='400'):P.MetaProvider().call('p',SCHEMA,tmp_path/'t')

def test_prose_prefix_is_stripped():
    assert P.extract_json('Pulling my ledger first. {"tool":"finish","argument":"","why":"x"} trailing')=={'tool':'finish','argument':'','why':'x'}
    with pytest.raises(RuntimeError):P.extract_json('no json here')

def test_provider_for(monkeypatch):
    monkeypatch.delenv('RSQ_PROVIDER',raising=False)
    assert isinstance(P.provider_for('muse-spark-1.3','high'),P.MetaProvider)
    assert isinstance(P.provider_for(None,'low'),P.CodexProvider)
    monkeypatch.setenv('RSQ_PROVIDER','meta');assert isinstance(P.provider_for(None,'low'),P.MetaProvider)
    monkeypatch.delenv('META_API_KEY',raising=False);monkeypatch.delenv('MODEL_API_KEY',raising=False)
    with pytest.raises(RuntimeError):P.MetaProvider().preflight()
