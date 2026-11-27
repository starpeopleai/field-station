"""Small independent camera sample; no scheduled detection or review records."""
import base64,hashlib,json,subprocess,sys,threading,time
from pathlib import Path
from model_settings import read,save
_LOCK=threading.Lock();_BUSY=False;_ERROR=None

def samples(data,refresh=False):
 global _BUSY,_ERROR
 root=Path(data)/'model-inspector/live-preview';root.mkdir(parents=True,exist_ok=True)
 doc=read(root/'samples.json',{});now=time.time()
 with _LOCK:
  if _BUSY:return dict(rows=[],preparing=True)
  if refresh or not doc or now-doc.get('sampled_epoch',0)>=300:
   _BUSY=True;_ERROR=None;threading.Thread(target=_prepare,args=(str(data),),daemon=True).start();return dict(rows=[],preparing=True)
  if _ERROR:raise ValueError(_ERROR)
 rows=[r for r in doc.get('rows',[]) if 0<=now-r['detected_epoch']<=300]
 return dict(rows=rows,preparing=False)

def _prepare(data):
 global _BUSY,_ERROR
 root=Path(data)/'model-inspector/live-preview'
 try:
  job=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',data],capture_output=True,text=True,timeout=45)
  if job.returncode:raise ValueError('Camera sampling failed: '+job.stderr[-250:])
  frames=json.loads(job.stdout);rows=[]
  for frame in frames:
   raw=base64.b64decode(frame['image']);digest=hashlib.sha256(raw).hexdigest();key='preview-'+hashlib.sha256((digest+str(frame['epoch'])).encode()).hexdigest()[:32]
   (root/(key+'.png')).write_bytes(raw)
   rows.append(dict(id=key,kind='preview',image_url='/api/model-decision-preview?id='+key,created=frame['epoch'],detected_epoch=frame['epoch'],human_reviewed=False,generation=frame['generation'],pts_seconds=frame['pts_seconds'],native_crop_sha256=digest))
  for row in rows:save(root/(row['id']+'.json'),row)
  old=read(root/'samples.json',{}).get('rows',[]);save(root/'samples.json',dict(rows=rows,sampled_epoch=time.time()))
  keep={r['id'] for r in rows}
  from object_model_scores import connect
  with connect(data) as db:
   for row in old:
    key=row['id']
    if key not in keep and key.startswith('preview-'):
     db.execute('DELETE FROM scores WHERE id=?',(key,))
  for p in root.glob('preview-*.json'):
   if time.time()-p.stat().st_mtime>3600:
    p.with_suffix('.png').unlink(missing_ok=True);p.unlink(missing_ok=True)
 except Exception as exc:
  _ERROR=str(exc)
  save(root/'samples.json',dict(rows=[],sampled_epoch=time.time()))
 finally:
  with _LOCK:_BUSY=False

def capture(data):
 import av,io,os
 from native_frames import timing_rows
 os.nice(10)
 spool=Path(data).parent/'capture-spool';generation=read(spool/'active.json',{})['generation'];folder=spool/generation
 if Path(generation).name!=generation:raise ValueError('Invalid camera generation')
 with (folder/'segments-index.jsonl').open('rb') as f:
  f.seek(0,2);f.seek(max(0,f.tell()-16384));lines=f.read().splitlines()
 entries=[]
 for line in reversed(lines):
  try:entry=json.loads(line)
  except ValueError:continue
  if Path(entry['file']).name!=entry['file']:continue
  if 0<=time.time()-entry['start_epoch']<=300 and (folder/entry['file']).is_file():entries.append(entry)
  if len(entries)==6:break
 frames=[]
 for entry in reversed(entries):
  with (folder/entry['file']).open('rb') as f:raw=f.read(32*1024**2+1)
  if len(raw)>32*1024**2 or hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Camera source verification failed')
  timings=timing_rows(folder,entry['start'],entry['end'])
  with av.open(io.BytesIO(raw)) as container:
   stream=container.streams.video[0];stream.codec_context.thread_count=1
   frame=next(container.decode(stream))
   if frame.pts is None or frame.time_base is None:raise ValueError('Missing camera timestamp')
   pts=entry['start']+float(frame.pts*frame.time_base);timing=min(timings,key=lambda t:abs(t['pts_seconds']-pts))
   if abs(timing['pts_seconds']-pts)>.003:raise ValueError('Camera timestamp mismatch')
   image=frame.to_image().convert('RGB');out=io.BytesIO();image.save(out,format='PNG');encoded=out.getvalue()
   if len(encoded)>4*1024**2:raise ValueError('Camera frame exceeds preview size limit')
   frames.append(dict(epoch=timing['received_epoch'],generation=generation,pts_seconds=pts,image=base64.b64encode(encoded).decode()))
 return frames

if __name__=='__main__':print(json.dumps(capture(sys.argv[2])))
