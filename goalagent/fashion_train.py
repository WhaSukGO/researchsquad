"""Training fixture executed only inside an approved GPU job, not on the host."""
import os
os.environ['CUBLAS_WORKSPACE_CONFIG']=':4096:8'
import argparse
import json
from pathlib import Path
import time
import torch
from safetensors.torch import save_file
from fashion_model import build_model,images,labels


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--epochs',type=int,required=True)
    a=p.parse_args();torch.set_num_threads(4);torch.manual_seed(1337)
    torch.use_deterministic_algorithms(True);torch.backends.cudnn.benchmark=False
    assert torch.cuda.is_available(),'GPU execution is required; CPU fallback is not permitted'
    device='cuda';model=build_model().to(device);opt=torch.optim.Adam(model.parameters(),lr=.001)
    x=images(Path(a.data)/'images.gz');y=labels(Path(a.data)/'labels.gz')
    # Final 5,000 official training examples are validation; official test files are absent.
    train_x=x[:-5000].to(device);train_y=y[:-5000].to(device)
    val_x=x[-5000:].to(device);val_y=y[-5000:].to(device)
    initial=next(model.parameters()).detach().cpu().clone();begin=0;steps=0;history=[]
    resume=Path('/checkpoints/resume')
    if resume.exists():
        c=torch.load(resume,map_location=device,weights_only=True)
        model.load_state_dict(c['model']);opt.load_state_dict(c['optimizer'])
        begin=c['epoch'];steps=c['steps'];history=c['history'];initial=c['initial'].cpu()
        torch.set_rng_state(c['torch_rng'].cpu());torch.cuda.set_rng_state_all([t.cpu() for t in c['cuda_rng']])
    start=time.monotonic();finite=True
    for epoch in range(begin,a.epochs):
        model.train();order=torch.randperm(len(train_y));total=0
        for i in range(0,len(order),512):
            indices=order[i:i+512].to(device);opt.zero_grad(set_to_none=True)
            loss=torch.nn.functional.cross_entropy(model(train_x[indices]),train_y[indices]);loss.backward()
            finite=finite and bool(torch.isfinite(loss)) and all(bool(torch.isfinite(v.grad).all()) for v in model.parameters() if v.grad is not None)
            if not finite:raise ValueError('Non-finite training loss/gradient')
            opt.step();steps+=1;total+=float(loss.detach())*len(indices)
        model.eval();correct=0
        with torch.inference_mode():
            for i in range(0,len(val_y),256):correct+=int((model(val_x[i:i+256]).argmax(1)==val_y[i:i+256]).sum())
        history.append({'epoch':epoch+1,'loss':total/len(train_y),'validation_accuracy':correct/len(val_y),'optimizer_steps':steps})
        state={'model':model.state_dict(),'optimizer':opt.state_dict(),'epoch':epoch+1,'steps':steps,
            'history':history,'initial':initial,'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all()}
        torch.save(state,'checkpoint.tmp');os.replace('checkpoint.tmp','checkpoint.pt')
        print(json.dumps(history[-1]),flush=True)
    torch.cuda.synchronize()
    save_file({k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()},'weights.safetensors')
    delta=float((next(model.parameters()).detach().cpu()-initial).norm())
    result={'device':torch.cuda.get_device_name(),'torch':torch.__version__,'cuda':torch.version.cuda,
        'resumed_from_epoch':begin,'completed_epochs':a.epochs,'optimizer_steps':steps,'finite_gradients':finite,
        'parameter_delta_norm':delta,'peak_vram_bytes':torch.cuda.max_memory_allocated(),
        'elapsed_seconds':time.monotonic()-start,'history':history,'train_samples':len(train_y),'validation_samples':len(val_y)}
    Path('training.json').write_text(json.dumps(result,indent=2));assert delta>0


if __name__=='__main__':main()
