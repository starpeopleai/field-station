"""Track operator-selected lights in image space and render a separate evidence derivative."""
import fcntl
import json
import math
import os
import re
import tempfile
import threading
import uuid
from pathlib import Path

from review_playback import native_path


def folder(data, key):
    if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{32}', key):
        raise ValueError('Invalid detection')
    return Path(data).parent / 'archive-tags/starred-bundles/overlays' / key


def read(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def write(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
        json.dump(value, f, separators=(',', ':'))
    os.replace(f.name, path)


def status(data, key):
    base = folder(data, key)
    spec = read(base / 'request.json')
    if not spec:
        return {}
    job = base / spec['revision']
    return dict(spec, **read(job / 'status.json'))


def submit(data, body):
    import av
    key = body['id']
    base = folder(data, key)
    source = native_path(data, key)
    if not source.is_file():
        raise ValueError('Original recording unavailable')
    with av.open(str(source)) as c:
        stream = c.streams.video[0]
        width, height = stream.width, stream.height
        duration = float(stream.duration * stream.time_base) if stream.duration else c.duration / av.time_base
    start, anchor, end = (float(body[k]) for k in ('start','anchor','end'))
    points = body['points']
    if not 0 <= start <= anchor < end <= duration + .005:
        raise ValueError('Select lights on a frame inside the playback range')
    if not isinstance(points, list) or not 2 <= len(points) <= 16:
        raise ValueError('Choose between two and sixteen lights')
    seeds = []
    for x, y in points:
        if not (0 <= x < width and 0 <= y < height) or any(math.hypot(x-a,y-b)<4 for a,b in seeds):
            raise ValueError('Choose distinct lights inside the frame')
        seeds.append([min(width-1, round(x)), min(height-1, round(y))])
    base.mkdir(parents=True, exist_ok=True)
    revision = uuid.uuid4().hex
    job = base / revision
    job.mkdir()
    spec = dict(revision=revision, anchor=anchor, start=start, end=min(end,duration), points=seeds)
    if body.get('prediction') is True:
        spec['prediction'] = True
        previous = status(data, key)
        if body.get('from_revision'):
            if previous.get('revision') != body['from_revision'] or previous.get('state') != 'ready':
                raise ValueError('Formation changed. Reload before exporting.')
            if any(spec[k] != previous[k] for k in ('start','end','anchor','points')):
                raise ValueError('Saved formation range or points changed')
            spec['from_revision'] = previous['revision']
    write(job/'status.json', dict(state='queued'))
    write(base/'request.json', spec)
    threading.Thread(target=process, args=(data,key), daemon=True).start()
    return status(data,key)


def locate(gray, predicted, radius):
    """Snap to a compact local brightness peak above the surrounding sky noise."""
    import cv2
    import numpy as np
    x,y = predicted
    left,top=max(0,round(x)-radius),max(0,round(y)-radius)
    patch=gray[top:min(gray.shape[0],round(y)+radius+1),left:min(gray.shape[1],round(x)+radius+1)]
    if min(patch.shape, default=0)<5:
        return None
    residual=patch.astype('float32')-float(np.median(patch))
    threshold=max(8., 5.*1.4826*float(np.median(np.abs(residual))))
    n,labels,stats,centers=cv2.connectedComponentsWithStats((residual>threshold).astype('uint8'))
    options=[]
    for j in range(1,n):
        if not 2<=stats[j,cv2.CC_STAT_AREA]<=120:
            continue
        px,py=centers[j]+[left,top]
        distance=math.hypot(px-x,py-y)
        if distance<=radius:
            options.append((distance,round(px),round(py)))
    return list(min(options)[1:]) if options else None


def sample_frames(container, stream, low, high):
    container.seek(max(0,int(low/float(stream.time_base))-1),stream=stream)
    last=-math.inf
    for f in container.decode(stream):
        t=float(f.time)
        if t>=high:break
        if t>=low and t-last>=.075:
            yield t,f.to_ndarray(format='gray')
            last=t


def track(source, spec):
    import av
    rows=[]
    with av.open(str(source)) as c:
        s=c.streams.video[0]
        c.seek(max(0,int((spec['anchor']-.002)/float(s.time_base))),stream=s)
        f=next(f for f in c.decode(s) if float(f.time)>=spec['anchor']-.002)
        anchor=float(f.time)
        gray=f.to_ndarray(format='gray')
        seeds=[locate(gray,p,15) for p in spec['points']]
        if any(p is None for p in seeds) or len(set(map(tuple,seeds)))!=len(seeds):
            raise ValueError('A selected light is indistinct. Choose a clearer frame or click closer to its center.')
        rows.append([anchor,seeds])
        for direction,limit in ((-1,spec['start']),(1,spec['end'])):
            last=[(anchor,p,0.,0.) for p in seeds]
            edge=anchor
            while direction*(limit-edge)>0:
                other=edge+direction*min(1.,abs(limit-edge))
                batch=sample_frames(c,s,min(edge,other),max(edge,other))
                for t,img in (reversed(list(batch)) if direction<0 else batch):
                    if abs(t-anchor)<.004:continue
                    observed=[]
                    for i,(prev,p,vx,vy) in enumerate(last):
                        dt=t-prev
                        q=None
                        if abs(dt)<=.24:
                            q=locate(img,(p[0]+vx*dt,p[1]+vy*dt),10)
                        if q and q not in observed:
                            last[i]=(t,q,.5*vx+.5*(q[0]-p[0])/dt,.5*vy+.5*(q[1]-p[1])/dt)
                        else:q=None
                        observed.append(q)
                    rows.append([t,observed])
                edge=other
    return sorted(rows)


def segments(points):
    return [(a,b) for a,b in zip(points,points[1:]+points[:1]) if a and b]


def dashed_line(img, p, q):
    import cv2
    dx,dy=q[0]-p[0],q[1]-p[1]
    length=math.hypot(dx,dy)
    if length<1:return
    for start in range(0,math.ceil(length),16):
        ends=[tuple(round(a+d*u/length) for a,d in zip(p,(dx,dy)))
              for u in (start,min(start+8,length))]
        cv2.line(img,*ends,(20,195,235),1,cv2.LINE_AA)


def render(source, output, spec, rows, predictions=None):
    import av
    import cv2
    from bisect import bisect_left
    times=[r[0] for r in rows]
    with av.open(str(source)) as c, av.open(str(output),'w',options={'movflags':'+faststart'}) as dest:
        s=c.streams.video[0]
        enc=dest.add_stream('libx264',rate=s.average_rate or 30)
        enc.width,enc.height,enc.pix_fmt=s.width,s.height,'yuv420p'
        enc.codec_context.time_base=s.time_base
        enc.options={'preset':'veryfast','crf':'18','threads':'2'}
        c.seek(max(0,int(spec['start']/float(s.time_base))-1),stream=s)
        first=None
        for f in c.decode(s):
            t=float(f.time)
            if t<spec['start']-.001:continue
            if t>=spec['end']:break
            if first is None:first=f.pts
            i=bisect_left(times,t)
            lo=max(i-1,0);hi=min(i,len(rows)-1)
            a,b=rows[lo],rows[hi]
            alpha=max(0,min(1,(t-a[0])/(b[0]-a[0]))) if hi!=lo else 0
            points=[tuple(round(x+(y-x)*alpha) for x,y in zip(p,q)) if p and q else None
                    for p,q in zip(a[1],b[1])]
            img=f.to_ndarray(format='bgr24')
            predicted=set()
            if predictions is not None:
                for j,p in enumerate(points):
                    if p is not None:continue
                    left=a[1][j] or predictions[lo][j]
                    right=b[1][j] or predictions[hi][j]
                    if left and right:
                        points[j]=tuple(round(x+(y-x)*alpha) for x,y in zip(left,right))
                        predicted.add(j)
            for j,p in enumerate(points):
                k=(j+1)%len(points)
                q=points[k]
                if not p or not q:continue
                if j in predicted or k in predicted:
                    dashed_line(img,p,q)
                    continue
                cv2.line(img,p,q,(20,195,235),1,cv2.LINE_AA)
            for j,p in enumerate(points):
                if not p:continue
                if j in predicted:
                    cv2.drawMarker(img,p,(20,195,235),cv2.MARKER_DIAMOND,16,1,cv2.LINE_AA)
                    continue
                cv2.circle(img,p,7,(20,195,235),1,cv2.LINE_AA)
            cv2.putText(img,'Formation overlay | dashed = predicted' if predictions is not None else 'Formation overlay',(20,34),cv2.FONT_HERSHEY_SIMPLEX,.7,(20,195,235),1,cv2.LINE_AA)
            frame=av.VideoFrame.from_ndarray(img,format='bgr24')
            frame.pts,frame.time_base=f.pts-first,s.time_base
            for packet in enc.encode(frame):dest.mux(packet)
        if first is None:raise ValueError('No frames in the selected range')
        for packet in enc.encode():dest.mux(packet)


def process(data,key):
    base=folder(data,key)
    with (base.parent/'render.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        spec=read(base/'request.json')
        job=base/spec['revision']
        if read(job/'status.json').get('state') in ('ready','error'):return
        try:
            write(job/'status.json',dict(state='tracking'))
            source=native_path(data,key)
            if spec.get('from_revision'):
                previous=base/spec['from_revision']
                rows=read(previous/'tracks.json')['tracks']
                if not (job/'formation-overlay.mp4').exists():
                    os.link(previous/'formation-overlay.mp4',job/'formation-overlay.mp4')
            else:
                rows=track(source,spec)
                render(source,job/'building.mp4',spec,rows)
                (job/'building.mp4').replace(job/'formation-overlay.mp4')
            if spec.get('prediction'):
                from formation_prediction import predict
                estimates=predict(rows)
                render(source,job/'building.mp4',spec,rows,estimates)
                (job/'building.mp4').replace(job/'formation-predicted.mp4')
                write(job/'formation-predictions.json',dict(revision=spec['revision'],
                      method='constant relative image-plane velocity; measured reference points only',
                      coordinates='native image pixels',max_horizon_seconds=8,
                      predictions=[[row[0],est] for row,est in zip(rows,estimates)]))
            write(job/'tracks.json',dict(spec,coordinates='native image pixels',tracks=rows))
            write(job/'status.json',dict(state='ready'))
        except Exception as e:
            (job/'building.mp4').unlink(missing_ok=True)
            write(job/'status.json',dict(state='error',error=str(e)[:240]))
