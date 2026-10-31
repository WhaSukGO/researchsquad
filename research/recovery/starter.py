"""Training executable supplied for incident reproduction and recovery."""
import os
os.environ['CUBLAS_WORKSPACE_CONFIG']=':4096:8'
import argparse
import json
from pathlib import Path
import time
import torch
from safetensors.torch import save_file
from fashion_model import images,labels
from fashion_study_models import build

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--epochs',type=int,default=3);p.add_argument('--control',action='store_true');a=p.parse_args()
    torch.set_num_threads(4);torch.manual_seed(1337);torch.use_deterministic_algorithms(True);torch.backends.cudnn.benchmark=False
    assert torch.cuda.is_available(),'CUDA required'
    spec={'family':'mlp','width':16,'hidden':256,'dropout':.2}
    model=build(spec).cuda();optimizer=torch.optim.Adam(model.parameters(),lr=.001)
    x=images(Path(a.data)/'images.gz');y=labels(Path(a.data)/'labels.gz')
    train_x=x[:55000].cuda();train_y=y[:55000].cuda();val_x=x[55000:].cuda();val_y=y[55000:].cuda()
    # INPUT_TRANSFORM
    begin=0;steps=0;history=[];resume=Path('/checkpoints/resume')
    if resume.exists():
        saved=torch.load(resume,map_location='cuda',weights_only=True)
        model.load_state_dict(saved['model']);optimizer.load_state_dict(saved['optimizer'])
        begin=saved['epoch'];steps=saved['steps'];history=saved['history']
        torch.set_rng_state(saved['torch_rng'].cpu());torch.cuda.set_rng_state_all([v.cpu() for v in saved['cuda_rng']])
    print(json.dumps({'resumed_from_epoch':begin,'restored_optimizer_steps':steps,'input_shape':list(train_x.shape),'device':torch.cuda.get_device_name()}),flush=True)
    for epoch in range(begin,a.epochs):
        model.train();order=torch.randperm(len(train_y));total=0
        for i in range(0,len(order),512):
            ids=order[i:i+512].cuda();optimizer.zero_grad(set_to_none=True);logits=model(train_x[ids])
            loss=torch.nn.functional.cross_entropy(logits,train_y[ids])
            if not bool(torch.isfinite(loss)):
                diagnostic={'epoch':epoch+1,'step':steps,'loss':str(float(loss.detach())),
                    'logits_min':float(logits.detach().min()),'logits_max':float(logits.detach().max()),'input_finite':bool(torch.isfinite(train_x[ids]).all())}
                Path('failure.json').write_text(json.dumps(diagnostic));print(json.dumps(diagnostic),flush=True)
                raise FloatingPointError('non-finite training loss before backward; inspect failure.json')
            loss.backward()
            if not all(bool(torch.isfinite(v.grad).all()) for v in model.parameters() if v.grad is not None):raise FloatingPointError('non-finite gradient')
            optimizer.step();steps+=1;total+=float(loss.detach())*len(ids)
        model.eval();correct=0
        with torch.inference_mode():
            for i in range(0,len(val_y),256):correct+=int((model(val_x[i:i+256]).argmax(1)==val_y[i:i+256]).sum())
        history.append({'epoch':epoch+1,'loss':total/len(train_y),'validation_accuracy':correct/len(val_y),'optimizer_steps':steps})
        saved={'model':model.state_dict(),'optimizer':optimizer.state_dict(),'epoch':epoch+1,'steps':steps,'history':history,
            'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all()}
        torch.save(saved,'checkpoint.tmp');os.replace('checkpoint.tmp','checkpoint.pt')
        print(json.dumps(history[-1]),flush=True)
        # CHECKPOINT_BOUNDARY
    save_file({k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()},'weights.safetensors',metadata={'spec':json.dumps(spec)})
    Path('metrics.json').write_text(json.dumps({'spec':spec,'seed':1337,'optimizer':'Adam','lr':.001,'batch_size':512,
        'train_samples':55000,'validation_samples':5000,'resumed_from_epoch':begin,'optimizer_steps':steps,'finite_gradients':True,'history':history},indent=2))

if __name__=='__main__':main()
