"""Bounded public-source presentation; a retrieved challenge is not search evidence."""
from html.parser import HTMLParser
from urllib.parse import urljoin


def source_status(source):
    lowered=source.lower()
    if any(marker in lowered for marker in ('anomaly-modal', 'id="challenge-form"', "id='challenge-form'", 'cf-chl-')):
        return 'access_blocked'
    return 'retrieved'


def readable_html(source,url):
    class Reader(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.hidden=0;self.parts=[]
        def handle_starttag(self,tag,attrs):
            if tag in {'script','style'}:self.hidden+=1
            if self.hidden:return
            if tag in {'p','div','li','br','h1','h2','h3','tr','title'}:self.parts.append('\n')
            if tag=='a':
                href=dict(attrs).get('href','')
                if href:self.parts.append(' ['+urljoin(url,href)+'] ')
        def handle_endtag(self,tag):
            if tag in {'script','style'}:self.hidden=max(0,self.hidden-1)
            if not self.hidden and tag in {'p','div','li','h1','h2','h3','tr'}:self.parts.append('\n')
        def handle_data(self,data):
            if not self.hidden:self.parts.append(data)
    reader=Reader();reader.feed(source)
    return '\n'.join(' '.join(line.split()) for line in ''.join(reader.parts).splitlines() if line.strip())
