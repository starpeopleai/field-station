"""Human-reviewed nonlinear classifier, qualified by the 2026-11-14 grouped audit.
All feature extraction uses the native Vision path. Human labels are never changed.
"""
from collections import Counter,defaultdict
import numpy as np
ARCHITECTURE='MobileNetV3 Small frozen RGB features + normalized 64-unit nonlinear human-reviewed classifier'
THRESHOLD=.78
RECIPES={
 'human_nonlinear_v1':dict(width=64,epochs=40,positive_mass=.5,threshold=.78),
 'human_nonlinear_v2':dict(width=128,epochs=60,positive_mass=.25,threshold=.43),
}

def recipe_config(name):
    if name not in RECIPES:raise ValueError('Unknown human training recipe')
    return dict(RECIPES[name])

def architecture(name):
    return f"MobileNetV3 Small frozen RGB features + normalized {recipe_config(name)['width']}-unit nonlinear human-reviewed classifier"


def select_rows(rows):
    human=[r for r in rows if r.get('human_confirmed') and r.get('split')=='train']
    labels=defaultdict(set)
    for r in human:labels[r['pixel_sha256']].add(r['label'])
    conflict={p for p,v in labels.items() if len(v)>1}
    return [r for r in human if r['pixel_sha256'] not in conflict],sorted(conflict)

def sample_weights(rows,positive_mass=.5):
    if not 0<positive_mass<1:raise ValueError("Invalid positive class weight")
    groups=Counter((r['label'],r['group']) for r in rows)
    copies=Counter((r['label'],r['pixel_sha256']) for r in rows)
    weights=np.array([groups[(r['label'],r['group'])]**(-.5)/copies[(r['label'],r['pixel_sha256'])] for r in rows])
    for label in {r['label'] for r in rows}:
        mask=np.array([r['label']==label for r in rows]);weights[mask]*=len(rows)*(positive_mass if label=='anomalous' else 1-positive_mass)/weights[mask].sum()
    return weights

def __getattr__(name):
    if name=='ReviewedHead':
        from human_head import ReviewedHead
        return ReviewedHead
    raise AttributeError(name)


def fit_head(x,rows,classes,progress=None,recipe="human_nonlinear_v1"):
    config=recipe_config(recipe)
    import torch
    from torch import nn
    from human_head import ReviewedHead
    if classes!=['anomalous','not_anomalous']:raise ValueError('Nonlinear human recipe requires the binary class order')
    if len(x)!=len(rows) or not all(r.get('human_confirmed') for r in rows):raise ValueError('Human-only native rows required')
    if {r['label'] for r in rows}!=set(classes):raise ValueError('Both reviewed classes required')
    torch.manual_seed(731);mean=np.mean(x,axis=0);std=np.maximum(np.std(x,axis=0),.1)
    head=ReviewedHead(mean,std,width=config["width"]);normalized=torch.tensor(x,dtype=torch.float32)
    target=torch.tensor([r['label']=='anomalous' for r in rows],dtype=torch.float32);weights=torch.tensor(sample_weights(rows,config["positive_mass"]),dtype=torch.float32)
    optimizer=torch.optim.AdamW(head.parameters(),lr=.0005,weight_decay=.01)
    for epoch in range(1,config["epochs"]+1):
        head.train();order=torch.randperm(len(rows))
        for start in range(0,len(rows),1024):
            ids=order[start:start+1024];out=head(normalized[ids]);loss=(nn.functional.binary_cross_entropy_with_logits(out[:,0]-out[:,1],target[ids],reduction='none')*weights[ids]).mean()
            optimizer.zero_grad();loss.backward();optimizer.step()
        if progress:progress(epoch,config["epochs"])
    return head.eval()
