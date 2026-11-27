"""Reviewed email crops enter appearance training; no invented temporal ground truth."""
import hashlib,json,io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image,ImageChops
from classification_taxonomy import LABELS,canonical_label

def reviewed_examples(data,workers=1,prepared=False):
 root=Path(data)/'email-reviews'
 def load(p):
  r=json.loads(p.read_text());r.setdefault('original_label',r.get('label'));r['label']=canonical_label(r.get('label'))
  if r.get('deleted') or r.get('label') not in LABELS or not r.get('human_confirmed'):return None
  image=p.parent/'native-object.png'
  if image.is_symlink():raise ValueError('Email training crop integrity failure')
  raw=image.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=r['native_crop_sha256']:raise ValueError('Email training crop integrity failure')
  provenance='original'
  color_meta=p.parent/'color-review.json';color_image=p.parent/'color-native-object.png'
  if color_meta.is_file() and color_image.is_file() and not color_meta.is_symlink() and not color_image.is_symlink():
   color=json.loads(color_meta.read_text())
   if color.get('original_crop_sha256')==r['native_crop_sha256'] and color.get('event_id')==r['event_id'] and color.get('bounds')==r.get('bounds'):
    replacement=color_image.read_bytes()
    if hashlib.sha256(replacement).hexdigest()!=color['color_crop_sha256']:raise ValueError('Recovered color crop integrity failure')
    raw=replacement;image=color_image;provenance='verified_color_recovery'
  with Image.open(io.BytesIO(raw)) as source:
   w,h=source.size
   result=dict(id=r.get('sample_id',r['event_id']),label=r['label'],image=image,group='generation:'+r['generation'],native_width=w,native_height=h,review=r,color_provenance=provenance)
   if prepared:
    im=source.convert('RGB');bands=im.split();color=provenance=='verified_color_recovery' or r.get('source_color_space')=='RGB' or bool(ImageChops.difference(bands[0],bands[1]).getbbox() or ImageChops.difference(bands[1],bands[2]).getbbox());result['input_color_space']='RGB' if color else 'legacy_grayscale';out=io.BytesIO();im.save(out,format='PNG')
    result.update(normalized_png=out.getvalue(),pixel_sha256=hashlib.sha256(f'{w}x{h}:RGB:'.encode()+im.tobytes()).hexdigest())
  return result
 paths=sorted((root/'examples').glob('*/review.json'))
 if workers<=1:return [r for p in paths if (r:=load(p)) is not None]
 with ThreadPoolExecutor(max_workers=min(workers,4)) as pool:return [r for r in pool.map(load,paths) if r is not None]

# A request-local batch holds the existing review lock and publishes its index
# once. Per-object records and retry receipts remain authoritative.
import threading
from contextlib import contextmanager,nullcontext
_REVIEW_BATCH=threading.local()

def current_review_index(data):
 state=getattr(_REVIEW_BATCH,'state',None)
 return state['examples'] if state and state['root']==Path(data)/'email-reviews' else None

def batch_metadata_cache(data):
 state=getattr(_REVIEW_BATCH,'state',None)
 return state.setdefault('archive_metadata',{}) if state and state['root']==Path(data)/'email-reviews' else None

def review_index_stale(root,manifest,examples):
 # A directory creation is not a committed review. Each committed change writes
 # a unique history receipt before publishing the manifest, under review.lock.
 stamp=manifest.stat().st_mtime_ns
 history=root/'history'
 if history.is_dir():return history.stat().st_mtime_ns>stamp
 return examples.stat().st_mtime_ns>stamp

def read_committed_review(path):
 try:return json.loads(path.read_text())
 except FileNotFoundError:return None  # Interrupted mkdir has no committed label.

def replay_review_receipts(root,manifest,rows):
 # Recovery after an interrupted batch must not reopen every historical crop.
 # Receipts identify the changed samples; their current records are authoritative.
 import re,os
 stamp=manifest.stat().st_mtime_ns;changed=set()
 with os.scandir(root/'history') as entries:
  for entry in entries:
   if not entry.name.endswith('.json') or entry.stat().st_mtime_ns<stamp-1000000000:continue
   receipt=json.loads(Path(entry.path).read_text());key=receipt.get('sample_id',receipt.get('event_id'))
   if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{32}',key):raise ValueError('Invalid review recovery receipt')
   changed.add(key)
 if not changed:raise ValueError('Review index requires full recovery')
 indexed={r.get('sample_id',r.get('event_id')):r for r in rows}
 if None in indexed:raise ValueError('Legacy review index requires full recovery')
 for key in changed:
  current=read_committed_review(root/'examples'/key/'review.json')
  if current is None:indexed.pop(key,None)
  else:indexed[key]=current
 return list(indexed.values())

def replay_pending_reviews(root,rows):
 indexed={r.get('sample_id',r.get('event_id')):r for r in rows}
 for marker in (root/'pending-index').glob('*.json'):
  key=marker.stem
  import re
  if not re.fullmatch('[a-f0-9]{32}',key):raise ValueError('Invalid pending review key')
  current=read_committed_review(root/'examples'/key/'review.json')
  if current is not None:indexed[key]=current
 return list(indexed.values())

def clear_pending_reviews(root):
 for marker in (root/'pending-index').glob('*.json'):marker.unlink()

@contextmanager
def review_batch(data):
 import fcntl,time
 root=Path(data)/'email-reviews';root.mkdir(parents=True,exist_ok=True)
 if getattr(_REVIEW_BATCH,'state',None):raise RuntimeError('Nested review batch')
 with (root/'review.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);manifest=root/'training-manifest.json';examples=root/'examples';dirty=False
  try:
   rows=json.loads(manifest.read_text())['examples']
   if (root/'pending-index/enabled').exists():
    if any((root/'pending-index').glob('*.json')):rows=replay_pending_reviews(root,rows);dirty=True
   elif review_index_stale(root,manifest,examples):
    rows=replay_review_receipts(root,manifest,rows);dirty=True
  except (OSError,KeyError,ValueError):
   from concurrent.futures import ThreadPoolExecutor
   paths=[p/'review.json' for p in examples.iterdir()] if examples.exists() else []
   with ThreadPoolExecutor(max_workers=4) as pool:rows=[r for r in pool.map(read_committed_review,paths) if r is not None]
   dirty=True
  state=dict(root=root,examples=rows,dirty=dirty);_REVIEW_BATCH.state=state
  try:yield
  finally:
   try:
    if state['dirty']:
     rows=state['examples'];value=dict(updated_epoch=time.time(),examples=[{k:v for k,v in r.items() if k!='pre_review_models'} for r in rows],classes=sorted({e['label'] for e in rows if e.get('multiclass_ready') and not e.get('deleted')}))
     temp=manifest.with_suffix('.tmp');temp.write_text(json.dumps(value,allow_nan=False));temp.replace(manifest)
     clear_pending_reviews(root)
   finally:del _REVIEW_BATCH.state

def store_review(data,record,crop_bytes):
 import fcntl,time
 root=Path(data)/'email-reviews';root.mkdir(parents=True,exist_ok=True)
 def save(path,value):
  path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,allow_nan=False));temp.replace(path)
 state=getattr(_REVIEW_BATCH,'state',None)
 if state and state['root']!=root:raise ValueError('Review batch root mismatch')
 with nullcontext() if state else (root/'review.lock').open('a') as lock:
  if not state:fcntl.flock(lock,fcntl.LOCK_EX)
  key=hashlib.sha256((record['source']+':'+record['message_id']).encode()).hexdigest();audit=root/'history'/(key+'.json')
  if audit.exists():return 'already_imported'
  import re
  sample_id=record.get('sample_id',record['event_id'])
  if not re.fullmatch('[a-f0-9]{32}',sample_id):raise ValueError('Invalid training example ID')
  from object_omission import omitted
  object_id=record['event_id'] if sample_id==record['event_id'] else 'review:'+record['event_id']+':'+sample_id
  if omitted(data,object_id):raise ValueError('Object was deleted')
  manifest=root/'training-manifest.json';examples_root=root/'examples';indexed=None
  try:
   if not state and examples_root.stat().st_mtime_ns<=manifest.stat().st_mtime_ns:
    indexed=json.loads(manifest.read_text())['examples']
    if (root/'pending-index/enabled').exists():indexed=replay_pending_reviews(root,indexed)
  except (OSError,KeyError,ValueError):pass
  if state:indexed=state['examples']
  target=root/'examples'/sample_id;target.mkdir(parents=True,exist_ok=True);p=target/'review.json';previous=json.loads(p.read_text()) if p.exists() else {}
  if record['reviewed_epoch']>=previous.get('reviewed_epoch',0):
   if (root/'pending-index/enabled').exists():save(root/'pending-index'/(sample_id+'.json'),dict(sample_id=sample_id))
   from review_model_metrics import freeze,commit_review
   record=freeze(data,record,previous)
   temp=target/'native-object.tmp';temp.write_bytes(crop_bytes);temp.replace(target/'native-object.png');save(p,record)
   commit_review(data,record)
  save(audit,dict(record,previous=previous))
  if indexed is None:examples=[json.loads(p.read_text()) for p in (root/'examples').glob('*/review.json')]
  else:
   examples=[r for r in indexed if r.get('sample_id',r.get('event_id'))!=sample_id]
   examples.append(json.loads(p.read_text()))
  if state:state.update(examples=examples,dirty=True)
  else:save(root/'training-manifest.json',dict(updated_epoch=time.time(),examples=[{k:v for k,v in r.items() if k!='pre_review_models'} for r in examples],classes=sorted({e['label'] for e in examples if e.get('multiclass_ready') and not e.get('deleted')})))
  if not state:clear_pending_reviews(root)
  return 'imported'
