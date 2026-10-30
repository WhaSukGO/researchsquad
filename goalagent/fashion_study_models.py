"""Trusted declarative model loader; never imports experiment Python."""
import json
from fashion_model import images, labels

def build(spec):
    import torch.nn as nn
    if set(spec)!={'family','width','hidden','dropout'}:raise ValueError('Invalid model spec')
    family,width,hidden,drop=spec['family'],spec['width'],spec['hidden'],spec['dropout']
    if family not in ('mlp','cnn') or width not in (16,32,64) or hidden not in (128,256,512,1024) or not 0<=drop<=.5:raise ValueError('Unsupported model spec')
    if family=='mlp':return nn.Sequential(nn.Flatten(),nn.Linear(784,hidden),nn.ReLU(),nn.Dropout(drop),nn.Linear(hidden,10))
    return nn.Sequential(nn.Conv2d(1,width,3,padding=1),nn.ReLU(),nn.MaxPool2d(2),
        nn.Conv2d(width,width*2,3,padding=1),nn.ReLU(),nn.MaxPool2d(2),nn.Flatten(),
        nn.Linear(width*2*7*7,hidden),nn.ReLU(),nn.Dropout(drop),nn.Linear(hidden,10))

def score(weights,x,y):
    import torch
    from safetensors import safe_open
    from safetensors.torch import load_file
    with safe_open(str(weights),framework='pt') as f:spec=json.loads(f.metadata()['spec'])
    model=build(spec).eval();model.load_state_dict(load_file(str(weights)),strict=True)
    correct=0;loss=0
    with torch.inference_mode():
        for i in range(0,len(y),256):
            out=model(x[i:i+256]);target=y[i:i+256]
            correct+=int((out.argmax(1)==target).sum())
            loss+=float(torch.nn.functional.cross_entropy(out,target,reduction='sum'))
    return {'accuracy':correct/len(y),'loss':loss/len(y),'samples':len(y),'spec':spec}

if __name__=='__main__':
    import argparse
    import torch
    p=argparse.ArgumentParser();p.add_argument('--weights');p.add_argument('--images');p.add_argument('--labels');p.add_argument('--validation',action='store_true')
    a=p.parse_args();torch.set_num_threads(2)
    x=images(a.images);y=labels(a.labels)
    if a.validation:x=x[55000:];y=y[55000:]
    print(json.dumps(score(a.weights,x,y)))
