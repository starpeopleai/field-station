"""Bounded motion replay sandbox. Never modifies capture, settings or review data."""
import bisect,base64,hashlib,json,os,subprocess,sys,threading,time
from pathlib import Path
from detection_settings import DEFAULTS,validate
_LOCK=threading.Lock()
_RESULTS={}
_PENDING=None
_RUNNING=False
_SOURCE_ID=None

def _source(data,refresh):
 global _SOURCE_ID
 root=Path(data)/'detection-preview'
 root.mkdir(exist_ok=True)
 manifest=root/'source.json'
 if not refresh and manifest.exists():
  doc=json.loads(manifest.read_text())
  if doc.get('schema')==2 and all((root/item['cache']).exists() for item in doc['segments']):
   _SOURCE_ID=doc['id'];return doc
 spool=Path(data).parent/'capture-spool';generation=json.loads((spool/'active.json').read_text())['generation']
 if Path(generation).name!=generation:raise ValueError('Invalid capture generation')
 folder=spool/generation
 with (folder/'segments-index.jsonl').open('rb') as f:
  f.seek(0,2);f.seek(max(0,f.tell()-32768));lines=f.read().splitlines()
 entries=[]
 for line in reversed(lines):
  try:item=json.loads(line)
  except ValueError:continue
  if Path(item['file']).name!=item['file']:continue
  source=folder/item['file']
  if source.exists():entries.append(item)
  if len(entries)==8:break
 if len(entries)<3:raise ValueError('Waiting for completed camera footage. Try New frames shortly.')
 entries.reverse();items=[];total=0
 manifest.unlink(missing_ok=True)
 for i,item in enumerate(entries):
  source=folder/item['file'];size=source.stat().st_size;total+=size
  if size>32*1024**2 or total>128*1024**2:raise ValueError('Preview source exceeds its bounded storage limit')
  raw=source.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Preview source changed; try New frames')
  from native_frames import timing_rows
  timings=timing_rows(folder,item['start'],item['end'])
  if not timings:raise ValueError('Original capture timing unavailable for preview')
  name=f'segment-{i}.mkv';(root/name).write_bytes(raw);items.append(dict(item,cache=name,timings=timings))
 doc=dict(schema=2,id=hashlib.sha256(json.dumps(items,sort_keys=True).encode()).hexdigest()[:20],segments=items,generation=generation)
 manifest.write_text(json.dumps(doc));_SOURCE_ID=doc['id'];return doc

def request(data,value):
 global _PENDING,_RUNNING
 values={**DEFAULTS,**validate(value.get('values',{}))};refresh=value.get('refresh') is True
 # Reading/copying footage and all decoding happen in one isolated background job.
 with _LOCK:
  key=hashlib.sha256(json.dumps([values,_SOURCE_ID,time.time() if refresh else None],sort_keys=True).encode()).hexdigest()[:24]
  if key in _RESULTS:return dict(key=key,**_RESULTS[key])
  if _PENDING:
   old=_PENDING[0];_RESULTS[old]=dict(state='error',error='Preview superseded by newer settings.')
  _PENDING=(key,str(data),values,refresh)
  _RESULTS[key]=dict(state='pending')
  if not _RUNNING:
   _RUNNING=True;threading.Thread(target=_work,daemon=True).start()
  return dict(key=key,state='pending')

def status(key):
 with _LOCK:return dict(key=key,**_RESULTS.get(key,dict(state='error',error='Preview expired. Try New frames.')))

def _work():
 global _PENDING,_RUNNING
 while True:
  with _LOCK:
   if _PENDING is None:_RUNNING=False;return
   key,data,values,refresh=_PENDING;_PENDING=None
  try:
   doc=_source(data,refresh)
   job=dict(root=str(Path(data)/'detection-preview'),source=doc,values=values)
   result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker'],input=json.dumps(job),capture_output=True,text=True,timeout=70)
   if result.returncode:raise ValueError('Motion replay failed: '+result.stderr[-350:])
   value=json.loads(result.stdout)
  except Exception as e:value=dict(state='error',error=str(e))
  with _LOCK:
   _RESULTS[key]=value
   for old in list(_RESULTS)[:-4]:
    if _RESULTS[old]['state']!='pending':_RESULTS.pop(old,None)

def replay(job):
 import av,cv2
 from native_motion import NativeMotion
 cv2.setNumThreads(1)
 detector=NativeMotion(job['values']);frames=[];processed=0
 root=Path(job['root']);segments=job['source']['segments'];warmup=min(2,len(segments)-1)
 for index,segment in enumerate(segments):
  last=None;timings=segment.get('timings');pts_values=[t['pts_seconds'] for t in timings] if timings else []
  with av.open(str(root/segment['cache'])) as container:
   stream=container.streams.video[0];stream.codec_context.thread_count=1
   for frame in container.decode(stream):
    if frame.pts is None or frame.time_base is None:raise ValueError('Preview frame has no capture timestamp')
    if frame.width>1920 or frame.height>1080:raise ValueError('Unsupported preview geometry')
    pts=segment['start']+float(frame.pts*frame.time_base);epoch=segment['start_epoch']+pts-segment['start']
    if timings:
     near=bisect.bisect_left(pts_values,pts);options=[i for i in (near-1,near) if 0<=i<len(timings)]
     choice=min(options,key=lambda i:abs(pts_values[i]-pts)) if options else None
     if choice is None or abs(pts_values[choice]-pts)>.003:raise ValueError('Preview frame lacks original capture timing')
     pts=timings[choice]['pts_seconds'];epoch=timings[choice]['received_epoch']
    gray=frame.to_ndarray(format='gray');boxes,meta=detector.update(gray,pts)
    last=(frame,epoch,boxes,meta);processed+=1
    if processed>720:raise ValueError('Preview exceeds native frame budget')
  if index>=warmup and last:
   frame,epoch,boxes,meta=last
   if meta['warming']:raise ValueError('Frame timing reset the motion background; no detection verdict is available')
   image=frame.to_ndarray(format='bgr24');h,w=image.shape[:2]
   for x,y,bw,bh in boxes:cv2.rectangle(image,(x,y),(x+bw,y+bh),(0,220,255),2)
   image=cv2.resize(image,(640,round(h*640/w)));ok,jpeg=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,82])
   if not ok:raise ValueError('Preview image encoding failed')
   frames.append(dict(detected=bool(boxes),regions=len(boxes),epoch=epoch,image='data:image/jpeg;base64,'+base64.b64encode(jpeg).decode()))
 return dict(state='ready',frames=frames[:6],source_id=job['source']['id'],replayed_frames=processed,warmup_segments=warmup)

if __name__=='__main__':
 os.nice(10)
 print(json.dumps(replay(json.load(sys.stdin))))
