"""Transport status must not turn a search challenge into research evidence."""
import json

from goalagent.claim_checks import successful
from goalagent.web_sources import source_status, readable_html
from goalagent.team import Team
from goalagent.agent import Agent
from test_team import task, FakeSandbox, Scripted, action


def test_known_challenge_is_blocked_even_with_http_200_and_exit_zero():
    blocked=source_status('<html><form id="challenge-form"><div class="anomaly-modal">Verify</div></form></html>')
    assert blocked=='access_blocked'
    assert not successful({'observation':{'status':blocked,'result':{'exit_code':0}}})
    assert source_status('<h1>Audiveris</h1><p>Actual source text</p>')=='retrieved'


def test_html_excerpt_preserves_source_links_without_styles_and_scripts():
    text=readable_html('<style>huge css</style><script>tracking()</script><h1>Sources</h1>'
        '<a href="/manual">Official manual</a><p>A&amp;B</p>','https://example.org/start')
    assert 'https://example.org/manual' in text and 'Official manual' in text and 'A&B' in text
    assert 'huge css' not in text and 'tracking()' not in text


def test_web_response_is_named_per_action_and_challenge_cannot_satisfy_search(tmp_path):
    class ResponseSandbox(FakeSandbox):
        calls=0
        def run(self,command,log,timeout):
            self.calls+=1
            raw=('<form id="challenge-form" class="anomaly-modal">Verify</form>' if self.calls==1
                 else '<h1>Actual official document</h1><a href="/manual">Manual</a>')
            (self.workspace/f'web-source-{self.calls:03}.html').write_text(raw)
            return {'exit_code':0,'interrupted':False,'tail':raw}
    value=task();value['network']=True
    team=Team(tmp_path,value,sandbox_factory=ResponseSandbox)
    config=team.definitions['researcher']
    worker=Agent(team.folder/'agents'/'transport',{'depth':1},Scripted([]),team.policy(config),
                 config,team.registry,ResponseSandbox)
    worker.state['steps']=1
    blocked=worker.execute(action('web_search','Audiveris official manual'),30)
    assert blocked['status']=='access_blocked' and not successful({'observation':blocked})
    worker.state['steps']=2
    actual=worker.execute(action('web_fetch','https://example.org/'),30)
    assert actual['status']=='retrieved' and 'Actual official document' in actual['text_excerpt']
    assert 'https://example.org/manual' in actual['text_excerpt']
    assert blocked['source_file']!=actual['source_file']
    assert (worker.workspace/blocked['source_file']).read_text().startswith('<form')
    assert (worker.workspace/actual['text_file']).exists()
