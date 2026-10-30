"""Maintainer-owned architecture and isolated Fashion-MNIST inference adapter."""
import argparse
import gzip
import json
from pathlib import Path


def build_model():
    import torch.nn as nn
    return nn.Sequential(nn.Conv2d(1,32,3,padding=1),nn.ReLU(),nn.MaxPool2d(2),
        nn.Conv2d(32,64,3,padding=1),nn.ReLU(),nn.MaxPool2d(2),nn.Flatten(),
        nn.Linear(64*7*7,1024),nn.ReLU(),nn.Dropout(.2),nn.Linear(1024,10))


def images(path):
    import numpy as np
    import torch
    with gzip.open(path,'rb') as f:raw=f.read()
    if int.from_bytes(raw[:4],'big')!=2051:raise ValueError('Invalid IDX image magic')
    n=int.from_bytes(raw[4:8],'big')
    if len(raw)!=16+n*784:raise ValueError('Invalid IDX image size')
    return torch.from_numpy(np.frombuffer(raw,offset=16,dtype=np.uint8).copy()).reshape(n,1,28,28).float()/255


def labels(path):
    import numpy as np
    import torch
    with gzip.open(path,'rb') as f:raw=f.read()
    n=int.from_bytes(raw[4:8],'big')
    if int.from_bytes(raw[:4],'big')!=2049 or len(raw)!=8+n:raise ValueError('Invalid IDX labels')
    return torch.from_numpy(np.frombuffer(raw,offset=8,dtype=np.uint8).copy()).long()


def evaluate(weights,test_images,test_labels):
    import torch
    from safetensors.torch import load_file
    torch.set_num_threads(2);torch.manual_seed(1337)
    x=images(test_images);y=labels(test_labels);model=build_model().eval()
    def metrics():
        correct=0;loss=0
        with torch.inference_mode():
            for i in range(0,len(y),256):
                logits=model(x[i:i+256]);target=y[i:i+256]
                correct+=int((logits.argmax(1)==target).sum())
                loss+=float(torch.nn.functional.cross_entropy(logits,target,reduction='sum'))
        return {'accuracy':correct/len(y),'loss':loss/len(y),'samples':len(y)}
    baseline=metrics();model.load_state_dict(load_file(str(weights)),strict=True)
    trained=metrics()
    return {'accepted':trained['accuracy']>=.80 and trained['accuracy']>baseline['accuracy'],
            'test':trained,'untrained':baseline,'scope':'Fixed short-run training validation, not architecture research or multi-seed comparison'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--weights');p.add_argument('--images');p.add_argument('--labels');p.add_argument('--compare')
    a=p.parse_args()
    if a.compare:
        from safetensors.torch import load_file
        first=load_file(a.weights);second=load_file(a.compare)
        assert set(first)==set(second)
        delta=max(float((first[k]-second[k]).abs().max()) for k in first)
        print(json.dumps({'max_abs_difference':delta,'identical':delta==0}))
    else:print(json.dumps(evaluate(a.weights,a.images,a.labels)))
