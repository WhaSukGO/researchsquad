"""1988-vocabulary network definition language: shapes, connection and parameter counts, cost model.

Pure Python, no torch. The vocabulary is deliberately pre-convolution: `local` is an
unshared locally connected layer and `tie` applies the Rumelhart-Hinton-Williams 1986
weight-sharing constraint to the preceding `local` layer. `shared_map` is a macro that is
only available once the ledger has unlocked it (see ledger.py).
"""
import json

OPS={'input','full','local','tie','avg','output','shared_map'}
# LeCun et al. 1989 (Neural Computation): 64,660 connections x 7,291 samples x 23 epochs took 3 days on a Sun-4/260.
RATE_PER_DAY=64660*7291*23/3.0


def parse(spec,macros=()):
    if isinstance(spec,str):spec=json.loads(spec)
    if not isinstance(spec,dict) or set(spec)!={'layers'} or not isinstance(spec['layers'],list):raise ValueError('Spec must be {"layers":[...]}')
    layers=[]
    for raw in spec['layers']:
        if not isinstance(raw,dict) or raw.get('op') not in OPS:raise ValueError('Unknown layer op: '+json.dumps(raw)[:200])
        op=raw['op']
        if op=='shared_map':
            if 'shared_map' not in macros:raise ValueError('shared_map is not in your vocabulary; build it from local + tie, and let the ledger unlock the macro')
            k,s,n=raw.get('k'),raw.get('stride',1),raw.get('n')
            layers.append({'op':'local','k':k,'stride':s,'n':n,'pad':raw.get('pad',k//2 if isinstance(k,int) else 0)})
            layers.append({'op':'tie','group':'all','bias':raw.get('bias','per_unit')})
            continue
        layers.append(dict(raw))
    if not layers or layers[0]['op']!='input' or layers[-1]['op']!='output':raise ValueError('Spec must start with input and end with output')
    return layers


def _pos(v,name):
    if type(v) is not int or v<=0:raise ValueError(name+' must be a positive integer')
    return v


def analyze(spec,macros=()):
    """Return shapes, connections, independent parameters and tied-layer inventory."""
    layers=parse(spec,macros)
    c=h=w=None;connections=0;params=0;report=[];tied=0;prev=None
    for i,l in enumerate(layers):
        op=l['op']
        if op=='input':
            if i!=0 or set(l)!={'op','h','w'}:raise ValueError('input(h,w) only at the start')
            c,h,w=1,_pos(l['h'],'h'),_pos(l['w'],'w');report.append({'op':'input','shape':[c,h,w]})
        elif op=='local':
            if set(l)-{'op','k','stride','n','pad','fan_in'}!=set() or 'k' not in l or 'n' not in l:raise ValueError('local(k, stride, n, pad?, fan_in?)')
            k=_pos(l['k'],'k');s=_pos(l.get('stride',1),'stride');n=_pos(l['n'],'n');p=l.get('pad',k//2)
            if type(p) is not int or p<0:raise ValueError('pad must be a non-negative integer')
            maps=_pos(l.get('fan_in',c),'fan_in')
            if maps>c:raise ValueError('fan_in exceeds the number of input maps')
            oh=(h+2*p-k)//s+1;ow=(w+2*p-k)//s+1
            if oh<=0 or ow<=0:raise ValueError('Kernel larger than input')
            fan=maps*k*k;units=n*oh*ow
            conn=units*(fan+1);connections+=conn;params+=conn
            report.append({'op':'local','k':k,'stride':s,'pad':p,'n':n,'in_maps':c,'fan_in_maps':maps,'shape':[n,oh,ow],'units':units,'fan_in':fan,'connections':conn,'params':conn,'tied':False})
            c,h,w=n,oh,ow
        elif op=='tie':
            if prev is None or prev['op']!='local' or prev['tied']:raise ValueError('tie must directly follow an untied local layer')
            if set(l)-{'op','group','bias'}!=set() or l.get('group','all')!='all' or l.get('bias','per_unit') not in {'per_unit','shared'}:raise ValueError('tie(group=all, bias=per_unit|shared)')
            n=prev['n'];fan=prev['fan_in'];units=prev['units']
            shared=n*fan+(n if l.get('bias','per_unit')=='shared' else units)
            params+=shared-prev['params'];prev['params']=shared;prev['tied']=True;prev['bias']=l.get('bias','per_unit');tied+=1
            report.append({'op':'tie','group':'all','bias':prev['bias'],'params_after_tie':shared})
        elif op=='avg':
            if set(l)!={'op','k'}:raise ValueError('avg(k)')
            k=_pos(l['k'],'k')
            if h%k or w%k:raise ValueError('avg(k) needs divisible input')
            oh,ow=h//k,w//k;conn=c*oh*ow*k*k;connections+=conn
            report.append({'op':'avg','k':k,'shape':[c,oh,ow],'connections':conn,'params':0,'fixed':True})
            h,w=oh,ow
        elif op in ('full','output'):
            if set(l)!={'op','n'}:raise ValueError(op+'(n)')
            n=_pos(l['n'],'n');fan=c*h*w;conn=n*(fan+1);connections+=conn;params+=conn
            report.append({'op':op,'n':n,'shape':[n,1,1],'fan_in':fan,'connections':conn,'params':conn})
            c,h,w=n,1,1
        prev=report[-1]
    if report[-1]['op']!='output':raise ValueError('Spec must end with output')
    return {'layers':report,'connections':connections,'params':params,'tied_layers':tied,'output_units':report[-1]['n']}


def eta_days(connections,samples,epochs):
    return connections*samples*epochs/RATE_PER_DAY


def canonical(spec,macros=()):
    return json.dumps({'layers':parse(spec,macros)},sort_keys=True,separators=(',',':'))
