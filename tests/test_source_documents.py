import json
import pytest
from goalagent.source_documents import search_request,present
from goalagent.claim_checks import successful

def test_discovery_is_metadata_not_reading_and_query_is_encoded():
    provider,url=search_request(json.dumps({'provider':'crossref','query':'dropout & neural'}))
    assert provider=='crossref' and '%26' in url
    raw=json.dumps({'message':{'items':[{'title':['A paper'],'URL':'https://journal/paper','DOI':'10/x'}]}}).encode()
    result=present(raw,url,provider)
    assert result['format']=='search_metadata' and 'Discovery metadata only' in result['text']
    assert 'A paper' in result['text']
    with pytest.raises(ValueError):search_request('{"provider":"shell","query":"x"}')

def test_raw_code_preserves_operators_and_html_exposes_links():
    code=b'if x < 3:\n    print("<p>literal</p>")\n'
    assert present(code,'https://raw.githubusercontent.com/org/repo/sha/train.py')['text']==code.decode()
    result=present(b'<h1>Paper</h1><a href="/full.pdf">PDF</a>','https://journal/paper')
    assert 'https://journal/full.pdf' in result['text']

def test_pdf_requires_approved_parser_and_blocked_is_not_success():
    with pytest.raises(ValueError,match='immutable'):present(b'%PDF-1.7','https://journal/full.pdf',path='/tmp/file')
    result=present(b'<form id="challenge-form">blocked</form>','https://search')
    assert result['status']=='access_blocked' and not successful({'observation':result})

def test_owner_network_roles_and_excluded_data_urls(tmp_path):
    from test_team import make,instance,action
    team=make(tmp_path);team.task.update(network=True,network_roles=['researcher'],source_deny_patterns=['t10k'])
    assert team.policy(team.definitions['researcher'])['network']
    assert not team.policy(team.definitions['experiment_engineer'])['network']
    researcher=instance(team,'researcher')
    with pytest.raises(ValueError,match='excluded'):researcher.execute(action('web_fetch','https://example.org/t10k-labels.gz'),1)
