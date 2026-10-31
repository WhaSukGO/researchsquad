"""Frozen USPS training job for netlang specs (container only, CPU).

Historical loss: mean squared error against +/-1 targets through tanh outputs
(LeCun et al. 1989). Optimizer is plain SGD with momentum, a modern stand-in for the
stochastic diagonal Levenberg-Marquardt used then. Writes metrics.json, training.jsonl
and weights.safetensors to /workspace/output. The gradient check is an LLM-independent
proof that the tied (shared) kernel gradient equals the sum of per-position gradients.
"""
import argparse
import json
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from safetensors.torch import save_file
from netlang_torch import build, load_usps, evaluate, Tied

SEED=1988;VALID=1000


def grad_check(model,x,y):
    """Central finite difference on one tied kernel entry vs autograd, in float64."""
    tied=[m for m in model.body if isinstance(m,Tied)]
    if not tied:return None
    model=model.double();xb=x[:64].double();tb=F.one_hot(y[:64],10).double()*2-1
    def loss():return F.mse_loss(model(xb),tb)
    model.zero_grad();loss().backward();layer=tied[0];auto=float(layer.weight.grad.flatten()[0])
    eps=1e-5
    with torch.no_grad():
        flat=layer.weight.view(-1);orig=float(flat[0])
        flat[0]=orig+eps;up=float(loss());flat[0]=orig-eps;down=float(loss());flat[0]=orig
    numeric=(up-down)/(2*eps);denom=max(abs(auto),abs(numeric),1e-12);rel=abs(auto-numeric)/denom
    model.float();model.zero_grad()
    return {'autograd':auto,'finite_difference':numeric,'relative_error':rel,'tolerance':1e-4,'passed':rel<1e-4,
            'statement':'d loss / d (shared kernel weight) computed by backpropagation equals the central finite difference'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--spec',required=True);p.add_argument('--epochs',type=int,required=True)
    p.add_argument('--net-id',required=True);p.add_argument('--dataset-id',required=True)
    p.add_argument('--lr',type=float,default=0.02);p.add_argument('--batch-size',type=int,default=32)
    a=p.parse_args();assert 1<=a.epochs<=30
    out=Path('/workspace/output');out.mkdir(parents=True,exist_ok=True);log=(out/'training.jsonl').open('w',buffering=1)
    def emit(v):
        t=json.dumps(v,allow_nan=False);print(t,flush=True);log.write(t+'\n')
    started=time.perf_counter();torch.set_num_threads(2);torch.manual_seed(SEED)
    x,y=load_usps(Path('/datasets')/a.dataset_id/'zip.train.gz')
    n=len(y);tx,ty=x[:n-VALID],y[:n-VALID];vx,vy=x[n-VALID:],y[n-VALID:]
    spec=json.loads(a.spec);model=build(spec);params=sum(p.numel() for p in model.parameters())
    emit({'event':'start','net_id':a.net_id,'parameters':params,'connections':model.analysis['connections'],'train_count':int(len(ty)),'validation_count':VALID,'torch':torch.__version__})
    check=grad_check(model,tx,ty)
    if check:emit({'event':'grad_check',**check})
    opt=torch.optim.SGD(model.parameters(),lr=a.lr,momentum=0.9);gen=torch.Generator().manual_seed(SEED);history=[]
    for epoch in range(1,a.epochs+1):
        model.train();order=torch.randperm(len(ty),generator=gen);total=0.0
        for i in range(0,len(ty),a.batch_size):
            idx=order[i:i+a.batch_size];target=F.one_hot(ty[idx],10).float()*2-1
            opt.zero_grad(set_to_none=True);loss=F.mse_loss(model(tx[idx]),target)
            if not torch.isfinite(loss):raise RuntimeError('Nonfinite loss')
            loss.backward();opt.step();total+=float(loss.detach())*len(idx)
        val=evaluate(model,vx,vy)
        row={'epoch':epoch,'train_mse':total/len(ty),'val_error':val['error'],'val_reject_curve':val['reject_curve'],'elapsed_seconds':time.perf_counter()-started}
        history.append(row);emit({'event':'epoch',**row})
    final=evaluate(model,vx,vy)
    def shifted(dx):
        x=torch.roll(vx,shifts=dx,dims=3);x[:,:,:,:dx]=-1.0;return x
    model.eval()
    with torch.inference_mode():
        base=model(vx).argmax(1);invariance={f'shift{d}':float((model(shifted(d)).argmax(1)==base).float().mean()) for d in (1,2)}
    state={k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()}
    save_file(state,str(out/'weights.safetensors'),metadata={'spec':json.dumps(spec)})
    metrics={'net_id':a.net_id,'spec':a.spec,'dataset_id':a.dataset_id,'parameters':params,'connections':model.analysis['connections'],
             'epochs':a.epochs,'seed':SEED,'lr':a.lr,'batch_size':a.batch_size,'loss':'mse_pm1_tanh','optimizer':'sgd_momentum_0.9',
             'train_count':int(len(ty)),'validation_count':VALID,'per_epoch':history,'val_error':final['error'],'reject_curve':final['reject_curve'],
             'grad_check':check,'invariance':invariance,'elapsed_seconds':time.perf_counter()-started,'official_test_accessed':False}
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2,allow_nan=False)+'\n')
    emit({'event':'complete','val_error':final['error'],'elapsed_seconds':metrics['elapsed_seconds']});log.close()


if __name__=='__main__':main()
