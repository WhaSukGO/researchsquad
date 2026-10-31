"""Container-side builder for netlang specs (torch), plus USPS loading and evaluation.

Runs only inside the training/evaluation containers; never on the host.
"""
import argparse
import gzip
import json
import math

import torch
import torch.nn as nn
import torch.nn.functional as F
from netlang import analyze

RATES=('0','0.05','0.09','0.12')


class Local(nn.Module):
    """Unshared locally connected layer: one weight vector per output unit."""
    def __init__(self,layer):
        super().__init__()
        if layer['fan_in_maps']!=layer['in_maps']:raise ValueError('Untied local layers use all input maps in this implementation')
        n,oh,ow=layer['shape'];self.k=layer['k'];self.s=layer['stride'];self.p=layer['pad'];self.n=n;self.oh=oh;self.ow=ow
        fan=layer['fan_in'];bound=1/math.sqrt(fan)
        self.weight=nn.Parameter(torch.empty(n,oh*ow,fan).uniform_(-bound,bound))
        self.bias=nn.Parameter(torch.zeros(n,oh*ow))
    def forward(self,x):
        u=F.unfold(x,self.k,padding=self.p,stride=self.s)          # (B, C*k*k, L)
        out=torch.einsum('bjl,nlj->bnl',u,self.weight)+self.bias    # (B, n, L)
        return out.reshape(x.shape[0],self.n,self.oh,self.ow)


class Tied(nn.Module):
    """local + tie(all): one kernel per output map (RHW 1986 equal-weight-change constraint)."""
    def __init__(self,layer):
        super().__init__()
        n,oh,ow=layer['shape'];self.k=layer['k'];self.s=layer['stride'];self.p=layer['pad'];self.n=n
        self.c=layer['in_maps'];self.m=layer['fan_in_maps'];fan=layer['fan_in'];bound=1/math.sqrt(fan)
        self.weight=nn.Parameter(torch.empty(n,self.m,self.k,self.k).uniform_(-bound,bound))
        self.bias=nn.Parameter(torch.zeros(n,oh,ow) if layer.get('bias','per_unit')=='per_unit' else torch.zeros(n,1,1))
    def full_weight(self):
        if self.m==self.c:return self.weight
        rows=[]
        for i in range(self.n):
            full=self.weight.new_zeros(self.c,self.k,self.k)
            sel=[(i+j)%self.c for j in range(self.m)]
            full=full.index_copy(0,torch.tensor(sel,device=self.weight.device),self.weight[i])
            rows.append(full)
        return torch.stack(rows)
    def forward(self,x):return F.conv2d(x,self.full_weight(),None,self.s,self.p)+self.bias


class Net(nn.Module):
    def __init__(self,spec):
        super().__init__()
        self.analysis=analyze(spec,('shared_map',));mods=[];layers=self.analysis['layers']
        for l in layers:
            if l['op']=='local':mods.append(Tied(l) if l['tied'] else Local(l))
            elif l['op']=='avg':mods.append(nn.AvgPool2d(l['k']))
            elif l['op'] in ('full','output'):mods.append(nn.Flatten());mods.append(nn.Linear(l['fan_in'],l['n']))
        self.body=nn.ModuleList(mods)
    def forward(self,x):
        for m in self.body:
            x=m(x)
            if not isinstance(m,(nn.AvgPool2d,nn.Flatten)):x=torch.tanh(x)
        return x


def build(spec):return Net(spec)


def load_usps(path):
    rows=[]
    with gzip.open(path,'rt') as f:
        for line in f:
            parts=line.split()
            if not parts:continue
            rows.append([float(v) for v in parts])
    data=torch.tensor(rows,dtype=torch.float32)
    y=data[:,0].long();x=data[:,1:].reshape(-1,1,16,16)
    if x.shape[1:]!=(1,16,16) or int(y.min())<0 or int(y.max())>9:raise ValueError('Unexpected USPS format')
    return x,y


def reject_curve(outputs,y):
    pred=outputs.argmax(1);top2=outputs.topk(2,dim=1).values;margin=(top2[:,0]-top2[:,1])
    order=margin.argsort();wrong=(pred!=y)[order];n=len(y);curve={}
    for r in RATES:
        k=int(round(float(r)*n));kept=wrong[k:]
        curve[r]=float(kept.float().mean()) if len(kept) else 0.0
    return curve


def evaluate(model,x,y):
    model.eval()
    with torch.inference_mode():outputs=torch.cat([model(x[i:i+512]) for i in range(0,len(y),512)])
    curve=reject_curve(outputs,y)
    return {'error':curve['0'],'reject_curve':curve,'samples':int(len(y))}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--weights',required=True);p.add_argument('--data',required=True);p.add_argument('--spec',required=True)
    a=p.parse_args()
    from safetensors.torch import load_file
    torch.set_num_threads(2);torch.manual_seed(0)
    x,y=load_usps(a.data);model=build(json.loads(a.spec))
    model.load_state_dict(load_file(a.weights),strict=True)
    m=evaluate(model,x,y)
    print(json.dumps({'accepted':True,**m,'scope':'Protected held-out USPS test measurement by the host adapter; agent code is not executed'}))
