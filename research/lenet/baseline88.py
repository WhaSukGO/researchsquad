"""Hand-designed-feature baseline in the spirit of Denker et al. 1988 (container only, numpy).

Fixed 3x3 oriented edge templates applied at every position (a convolution with hand-chosen
constants), thresholded, then coarse-coded by 4x4 block averaging; plus 4x4 block means of
the raw image. A linear classifier on these 80 features is fitted by ridge least squares
against +/-1 targets. Rejection uses the margin between the two largest outputs. This is a
maintainer-owned adapter, not agent code, and it is the only process that sees the test file
besides the protected evaluator.
"""
import argparse
import gzip
import json
import numpy as np

RATES=('0','0.05','0.09','0.12')
TEMPLATES=np.array([[[-1,-1,-1],[2,2,2],[-1,-1,-1]],[[-1,2,-1],[-1,2,-1],[-1,2,-1]],
                    [[2,-1,-1],[-1,2,-1],[-1,-1,2]],[[-1,-1,2],[-1,2,-1],[2,-1,-1]]],dtype=np.float64)/6.0


def load(path):
    rows=[[float(v) for v in line.split()] for line in gzip.open(path,'rt') if line.strip()]
    data=np.array(rows);return data[:,1:].reshape(-1,16,16),data[:,0].astype(int)


def features(x):
    n=len(x);pad=np.pad(x,((0,0),(1,1),(1,1)),constant_values=-1.0);maps=np.zeros((n,4,16,16))
    for t,k in enumerate(TEMPLATES):
        for i in range(3):
            for j in range(3):maps[:,t]+=k[i,j]*pad[:,i:i+16,j:j+16]
    maps=np.maximum(maps,0.0)
    coarse=maps.reshape(n,4,4,4,4,4).mean(axis=(3,5)).reshape(n,64)
    raw=x.reshape(n,4,4,4,4).mean(axis=(2,4)).reshape(n,16)
    return np.concatenate([coarse,raw,np.ones((n,1))],axis=1)


def curve(outputs,y):
    pred=outputs.argmax(1);top=np.sort(outputs,axis=1);margin=top[:,-1]-top[:,-2]
    order=np.argsort(margin);wrong=(pred!=y)[order];n=len(y);out={}
    for r in RATES:
        k=int(round(float(r)*n));kept=wrong[k:];out[r]=float(kept.mean()) if len(kept) else 0.0
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('--train',required=True);p.add_argument('--test',required=True);p.add_argument('--valid',type=int,default=1000)
    a=p.parse_args()
    x,y=load(a.train);xt,yt=load(a.test);n=len(y)
    f=features(x);ft=features(xt);tr,va=slice(0,n-a.valid),slice(n-a.valid,n)
    targets=-np.ones((n,10));targets[np.arange(n),y]=1.0
    A=f[tr];w=np.linalg.solve(A.T@A+1e-2*np.eye(A.shape[1]),A.T@targets[tr])
    val=curve(f[va]@w,y[va]);test=curve(ft@w,yt)
    def shifted(dx):  # same transform as train_usps.py: move right by dx, blank columns at -1
        s=np.roll(x[va],dx,axis=2);s[:,:,:dx]=-1.0;return s
    base=(f[va]@w).argmax(1);invariance={f'shift{d}':float(((features(shifted(d))@w).argmax(1)==base).mean()) for d in (1,2)}
    print(json.dumps({'accepted':True,'features':int(f.shape[1]-1),'classifier_params':int(w.size),
        'val':{'error':val['0'],'reject_curve':val,'samples':int(a.valid),'invariance':invariance},'test':{'error':test['0'],'reject_curve':test,'samples':int(len(yt))},
        'scope':'Fixed hand-designed templates plus a least-squares classifier; a 1988-style baseline stand-in, not a reproduction of the Denker system'}))


if __name__=='__main__':main()
