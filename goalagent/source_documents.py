"""Public search discovery and bounded document presentation, not semantic truth."""
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
from urllib.parse import quote,urlparse
from .web_sources import readable_html,source_status

def search_request(argument):
    provider='duckduckgo';query=argument
    if argument.lstrip().startswith('{'):
        data=json.loads(argument)
        if set(data)!={'provider','query'} or not isinstance(data['query'],str):raise ValueError('Search needs provider/query')
        provider=data['provider'];query=data['query']
    if not query.strip() or len(query)>2000:raise ValueError('Invalid search query')
    if provider=='duckduckgo':url='https://html.duckduckgo.com/html/?q='+quote(query)
    elif provider=='crossref':url='https://api.crossref.org/works?query.bibliographic='+quote(query)+'&rows=5'
    elif provider=='github':url='https://api.github.com/search/repositories?q='+quote(query)+'&per_page=5'
    else:raise ValueError('Unknown search provider')
    return provider,url

def search_text(raw,provider):
    data=json.loads(raw)
    if provider=='crossref':
        rows=[{'title':i.get('title'),'authors':[a.get('family') for a in i.get('author',[])],
            'DOI':i.get('DOI'),'url':i.get('URL'),'links':i.get('link',[]),'published':i.get('published')}
            for i in data.get('message',{}).get('items',[])]
    else:rows=[{'repository':i.get('full_name'),'url':i.get('html_url'),'description':i.get('description'),
        'default_branch':i.get('default_branch'),'archived':i.get('archived')} for i in data.get('items',[])]
    return json.dumps({'provider':provider,'scope':'Discovery metadata only; open paper/code and read it before attributing findings','results':rows},ensure_ascii=False,indent=2)

def pdf_text(image,path):
    if not isinstance(image,str) or not re.fullmatch(r'(?:sha256:|.+@sha256:)[a-f0-9]{64}',image):raise ValueError('Owner-approved immutable source_reader_image required for PDF extraction')
    script="""from pypdf import PdfReader
import json
r=PdfReader('/document.pdf',strict=True);parts=[];size=0;count=0
for i,p in enumerate(r.pages[:40]):
 t=p.extract_text() or '';t=t[:max(0,200000-size)];parts.append('[PDF page '+str(i+1)+']\\n'+t);size+=len(t);count+=1
 if size>=200000:break
print(json.dumps({'text':'\\n'.join(parts),'pages_total':len(r.pages),'pages_extracted':count,'truncated':count<len(r.pages) or size>=200000}))
"""
    name='rsq-pdf-'+uuid.uuid4().hex[:20]
    try:result=subprocess.run(['docker','run','--name',name,'--rm','--network','none','--read-only','--cap-drop=ALL','--security-opt','no-new-privileges',
        '--memory','1g','--cpus','1','--pids-limit','64','--user',f'{os.getuid()}:{os.getgid()}',
        '--mount',f'type=bind,src={Path(path).resolve()},dst=/document.pdf,readonly',image,'python','-c',script],
        text=True,capture_output=True,timeout=40)
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=10)
    if result.returncode:raise ValueError('PDF extraction failed: '+result.stderr[-1000:])
    data=json.loads(result.stdout)
    if len(data['text'].strip())<100:raise ValueError('No substantial PDF text; scanned PDFs need a separate OCR path')
    return data

def present(raw,url,provider=None,image=None,path=None):
    if raw.startswith(b'%PDF-'):
        data=pdf_text(image,path);return {'status':'retrieved','format':'pdf',**data}
    text=raw.decode('utf-8',errors='replace')
    status=source_status(text)
    if status!='retrieved':return {'status':status,'format':'html','text':readable_html(text,url)}
    if provider in {'crossref','github'}:return {'status':'retrieved','format':'search_metadata','text':search_text(text,provider)}
    plain=urlparse(url).path.endswith(('.py','.json','.md','.txt','.toml','.yaml','.yml'))
    html=not plain and bool(re.search(r'(?i)<(?:!doctype html|html|head|body|title|h1|p|a|form)(?:\s|>)',text))
    if '\x00' in text:raise ValueError('Unsupported binary document')
    readable=readable_html(text,url) if html else text
    return {'status':'retrieved','format':'html' if html else 'text','text':readable[:200000],'truncated':len(readable)>200000}
