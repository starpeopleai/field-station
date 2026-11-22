"""Fit an offline temporal research head to human-reviewed original RGB sequences."""
import hashlib
import json
from collections import Counter

import numpy as np

from temporal_rgb import training_sequences


def features(rgb, seconds, row):
    x,y,w,h=row['review_bounds_xywh']
    left,top,_,_=row['crop_xywh']
    target=rgb[:,y-top:y-top+h,x-left:x-left+w].reshape(len(seconds),-1,3)
    # Follow the brightest pixels inside the reviewed object. Keep the channels
    # together so that brightness and changes in chromaticity remain distinguishable.
    lum=target @ np.array([.2126,.7152,.0722],dtype=np.float32)
    mask=lum>=np.percentile(lum,98,axis=1,keepdims=True)
    color=np.einsum('nt,ntc->nc',mask.astype(np.float32),target)/mask.sum(1)[:,None]
    chroma=color/np.maximum(1,color.sum(1,keepdims=True))
    signals=np.column_stack((color,chroma))
    elapsed=np.diff(seconds)
    if np.any(elapsed<=0):raise ValueError('non-increasing video timestamps')
    slope=np.abs(np.diff(signals,axis=0))/elapsed[:,None]
    return np.concatenate((signals.mean(0),signals.std(0),slope.mean(0)))


def fit(dataset):
    manifest=dataset/'manifest.json'
    signature=hashlib.sha256(manifest.read_bytes()).hexdigest()
    path=dataset/'temporal-research-head.json'
    if path.exists() and json.loads(path.read_text()).get('manifest_sha256')==signature:return
    vectors=[];labels=[];groups=[]
    for rgb,seconds,row in training_sequences(dataset):
        vectors.append(features(rgb,seconds,row))
        labels.append(row['label']);groups.append(row['group'])
    state=dict(manifest_sha256=signature,input='native_rgb24_original_video',scope='offline research',
               class_counts=dict(Counter(labels)),recording_groups=len(set(groups)))
    if len(set(labels))==2:
        counts=Counter(zip(labels,groups));independent=Counter(label for label,_ in counts)
        weights=np.array([1/(independent[label]*counts[label,group]) for label,group in zip(labels,groups)])
        weights*=len(weights)/weights.sum()
        matrix=np.asarray(vectors)
        mean=np.average(matrix,axis=0,weights=weights)
        scale=np.sqrt(np.average((matrix-mean)**2,axis=0,weights=weights))
        scale[scale<1e-8]=1
        design=np.column_stack(((matrix-mean)/scale,np.ones(len(labels))))
        response=np.where(np.asarray(labels)=='anomalous',1.,-1.)
        penalty=np.eye(design.shape[1]);penalty[-1,-1]=0
        coefficients=np.linalg.solve(design.T@(weights[:,None]*design)+penalty,design.T@(weights*response))
        state.update(phase='fit',method='weighted ridge least squares',positive_label='anomalous',
                     mean=mean.tolist(),scale=scale.tolist(),coefficients=coefficients[:-1].tolist(),
                     intercept=float(coefficients[-1]))
    else:state.update(phase='awaiting_both_classes')
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(state));tmp.replace(path)
