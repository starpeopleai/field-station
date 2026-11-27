"""Bounded HQ scoring queue; HTTP only reads small SQLite records, never models."""
import base64,hashlib,io,json,sqlite3,time
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from model_settings import read,state

from contextlib import contextmanager

@contextmanager
def connect(data,timeout=.25):
 p=Path(data)/'model-inspector/object-scores.sqlite';p.parent.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(p,timeout=timeout)
 try:
  if db.execute('PRAGMA journal_mode').fetchone()[0]!='wal':db.execute('PRAGMA journal_mode=WAL')
  # This is a derived score/metrics cache. Durable reviewed snapshots remain in
  # the authoritative review records; avoid an external-disk fsync per cache row.
  db.execute('PRAGMA synchronous=NORMAL')
  db.execute('CREATE TABLE IF NOT EXISTS scores (id TEXT PRIMARY KEY, signature TEXT, row TEXT, results TEXT, requested REAL, retry REAL DEFAULT 0)')
  db.execute('CREATE TABLE IF NOT EXISTS prediction_history (id TEXT, signature TEXT, scored REAL, crop TEXT, captured REAL, results TEXT, PRIMARY KEY(id,signature))')
  with db:yield db
 finally:db.close()

def identity(row,models):
 return hashlib.sha256(json.dumps(['review-box-v1',row['id'],row.get('image_url'),row.get('created'),[(m['lane'],m.get('version'),m.get('settings_revision')) for m in models]],sort_keys=True).encode()).hexdigest()

def attach(data,value):
 models=state(data)['models'];items=value.get('items',[])
 try:
  with connect(data) as db:
   for row in items:
    if row.get('kind')=='manual_recording':continue
    signature=identity(row,models);existing=db.execute('SELECT signature,results,requested FROM scores WHERE id=?',(row['id'],)).fetchone()
    results=json.loads(existing[1]) if existing and existing[0]==signature and existing[1] else {}
    if not existing or existing[0]!=signature:
     db.execute('INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,0)',(row['id'],signature,json.dumps(row),None,time.time()))
    row['model_classifications']=[dict(results.get(m['lane'],{'state':'pending' if m.get('available') else 'unavailable'}),lane=m['lane'],version=m.get('version'),settings_revision=m.get('settings_revision',0)) for m in models]
 except sqlite3.Error:
  for row in items:row['model_classifications']=[dict(lane=m['lane'],state='pending') for m in models]
 return value

def crop(data,row):
 data=Path(data);q=parse_qs(urlsplit(row['image_url']).query)
 if row['kind']=='preview':
  import re
  if not re.fullmatch(r'preview-[a-f0-9]{32}',row['id']):raise ValueError('Invalid preview frame')
  folder=data/'model-inspector/live-preview';p=folder/(row['id']+'.png');expected=row.get('native_crop_sha256')
 elif row['kind']=='detection':
  folder=data.parent/'notifications/outbox'/row['id'];event=read(folder/'event.json',{});p=folder/event.get('native_crop','native-object.png')
  if p.name!='native-object.png':raise ValueError('Unexpected native crop')
  expected=event.get('native_crop_sha256')
 elif row['kind']=='review':
  aid=q['annotation'][0];folder=data/'email-reviews/examples'/aid;record=read(folder/'review.json',{})
  if record.get('deleted'):raise ValueError('Review removed')
  p=folder/'native-object.png';expected=record.get('native_crop_sha256');color=read(folder/'color-review.json',{})
  if color.get('original_crop_sha256')==expected and color.get('bounds')==record.get('bounds') and (folder/'color-native-object.png').exists():p=folder/'color-native-object.png';expected=color.get('color_crop_sha256')
 else:
  from labeled_frames import gallery_image
  p=gallery_image(q['source'][0],q['id'][0],q['annotation'][0]);folder=p.parent;expected=None
 if p.is_symlink() or not p.resolve().is_relative_to(folder.resolve()) or p.stat().st_size>4*1024**2:raise ValueError('Unsafe crop')
 raw=p.read_bytes()
 if expected and hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Crop checksum mismatch')
 return raw

def geometry(data,row):
 """Use the original proposal inside its saved context, or the human's crop."""
 q=parse_qs(urlsplit(row['image_url']).query);key=row['id'] if row['kind']=='detection' else q.get('id',[''])[0]
 if row['kind'] not in ('detection','review'):return dict(scope='annotated_crop')
 event=read(Path(data).parent/'notifications/outbox'/key/'event.json',{})
 if row['kind']=='review':
  aid=q.get('annotation',[''])[0];record=read(Path(data)/'email-reviews/examples'/aid/'review.json',{})
  if aid!=key or record.get('bounds')!=event.get('bounds'):return dict(scope='annotated_crop')
 bounds=event.get('bounds');detection=event.get('detection_bounds')
 if not bounds or not detection:return dict(scope='annotated_crop')
 bx,by,bw,bh=bounds;x,y,w,h=detection
 if min(w,h)<=0 or min(x-bx,y-by)<0 or x+w>bx+bw or y+h>by+bh:raise ValueError('Invalid detection crop geometry')
 return dict(scope='detection_context',box=[x-bx,y-by,w,h],context_size=[bw,bh],captured_epoch=event.get('detected_epoch'))

def batch(data,limit=32):
 items=[]
 with connect(data,timeout=5) as db:
  rows=db.execute('SELECT id,signature,row FROM scores WHERE results IS NULL AND retry<? ORDER BY requested DESC LIMIT ?',(time.time(),limit)).fetchall()
 for key,signature,serialized in rows:
  try:
   row=json.loads(serialized);raw=crop(data,row);items.append(dict(id=key,signature=signature,sha256=hashlib.sha256(raw).hexdigest(),image=base64.b64encode(raw).decode(),geometry=geometry(data,row)))
  except (OSError,ValueError,KeyError):
   with connect(data) as db:db.execute('UPDATE scores SET retry=? WHERE id=? AND signature=?',(time.time()+300,key,signature))
 return items

def finish(data,items):
 with connect(data,timeout=5) as db:
  for item in items:
   changed=db.execute('UPDATE scores SET results=? WHERE id=? AND signature=?',(json.dumps(item['results'],allow_nan=False),item['id'],item['signature'])).rowcount
   if changed and item.get('sha256'):
    row=db.execute('SELECT row FROM scores WHERE id=?',(item['id'],)).fetchone();metadata=json.loads(row[0])
    if metadata.get('kind')=='preview':continue
    captured=item.get('geometry',{}).get('captured_epoch') or metadata.get('created')
    db.execute('INSERT OR IGNORE INTO prediction_history VALUES (?,?,?,?,?,?)',(item['id'],item['signature'],time.time(),item['sha256'],captured,json.dumps(item['results'],allow_nan=False)))
 return len(items)


def decorate(data,value):
 """Optional model comparison must never prevent reviewing or labeling a frame."""
 try:return attach(data,value)
 except (OSError,ValueError,KeyError,TypeError) as exc:
  import logging
  logging.getLogger(__name__).error('Model thumbnail results unavailable: %s',exc)
  for row in value.get('items',[]):
   if row.get('kind')!='manual_recording':row['model_classifications']=[dict(lane=lane,state='unavailable') for lane in ('human','experimental','hybrid','machine','rotation')]
  return value
