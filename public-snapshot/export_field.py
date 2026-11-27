"""Export a public snapshot through the onion boundary; never include source files."""
import base64,importlib.util,io,json,os,re,sys,time,urllib.request,zipfile
from pathlib import Path
from urllib.parse import urlsplit

PRIVATE=re.compile(r'token|csrf|password|secret|credential|authorization|cookie|email|latitude|longitude|coordinates|serial_number|device_serial',re.I)
PATHS=re.compile(r'/(?:Users|Volumes|home)/[^\s"\'<>]*')
IPS=re.compile(r'\b(?:100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])|192\.168|10\.\d+)\.\d+\.\d+(?::\d+)?\b')
def clean(v):
 if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if not PRIVATE.search(k) and k not in ('review_url','free_bytes','original_path','source_path','hostname','host','ip')}
 if isinstance(v,list):return [clean(x) for x in v]
 if isinstance(v,str):return IPS.sub('[private address]',PATHS.sub('[private path]',v))
 return v

def public_broadcasts(ledger,now):
 sessions=ledger.get('sessions',{})
 active=ledger.get('active_video_id')
 valid=lambda value:isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_-]{11}',value)
 entries=[e for e in sessions.values() if isinstance(e,dict) and valid(e.get('video_id'))]
 confirmed=next((e for e in entries if e['video_id']==active and e.get('state')=='live'),None)
 broadcasts=[dict(video_id=e['video_id'],start=e['start'],end=e['end']) for e in entries if e.get('end',0)>now-86400]
 result=dict(sessions=broadcasts)
 if confirmed:result['active_video_id']=active
 return result

def export(root,app,public):
 spec=importlib.util.spec_from_file_location('public_boundary',public/'readonly.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 files={};assets=set();failures=[]
 def get(path,port=8093):
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+path,timeout=30) as r:return r.read()
 for page in ('/','/label-videos','/models','/metrics'):
  raw=get(page).decode();files['pages/'+('index' if page=='/' else page[1:])+'.html']=raw.encode()
  assets.update(re.findall(r'(?:src|href)=["\'](/[^"\'?#]+\.(?:js|css|png|svg|webp|woff2))(?:\?[^"\']*)?["\']',raw))
 assets.update(['/starpeople-mark.png','/favicon.png','/fonts/license.txt','/public-readonly.js','/public-readonly.css','/ufo-engraving.png'])
 done=set()
 while assets-done:
  asset=sorted(assets-done)[0];done.add(asset)
  if not re.fullmatch(r'/[a-zA-Z0-9_./-]+',asset) or '..' in asset:raise ValueError('Unsafe asset')
  # Include only static UI assets; this also covers newer UI files missing from the old proxy.
  path=(public if asset.startswith('/public-readonly.') else app/'static')/asset.lstrip('/')
  if not path.is_file():
   try:raw=get(asset)
   except Exception:failures.append(asset);continue
  else:raw=path.read_bytes()
  files[asset.lstrip('/')]=raw
  if asset.endswith('.css'):
   for ref in re.findall(r'url\(["\']?([^\)"\']+)',raw.decode()):
    if ref.startswith('data:') or '://' in ref:continue
    assets.add(ref if ref.startswith('/') else '/'+str(Path(asset.lstrip('/')).parent/ref))
 for route in sorted(mod.JSON_ROUTES):
  if mod.JSON_ROUTES[route] or route in ('/api/labeled-frames/token',):continue
  try:files['responses/'+route[5:].replace('/','-')+'.json']=json.dumps(clean(json.loads(get(route))),allow_nan=False,separators=(',',':')).encode()
  except Exception:failures.append(route)
 # Publish only boolean control states, never private transmitter/operator setup.
 controls={}
 for route,key,source_key in [('/api/settings','live_streaming','live_streaming'),('/api/ce5','ce5_playing','playing')]:
  try:
   state=json.loads(get(route,8091));value=state.get(source_key)
   if isinstance(value,bool):controls[key]=value
  except Exception:pass
 files['camera-controls.json']=json.dumps(controls).encode()
 os.environ['UAP_LAB_DATA']=str(root);os.environ['CAPTURE_STATION_ROOT']=str(root.parent);os.environ['XDG_RUNTIME_DIR']=str(root.parent/'station-runtime');sys.path.insert(0,str(app));import lab,detection_library
 lab.DATA=root;lab.STATION=root.parent
 src=Path(detection_library.__file__).read_text();needle="if row['kind'] in ('detection','review')"
 if needle not in src:raise ValueError('Export contract changed')
 exec(compile(src.replace(needle,"if row['kind'] in ('detection','review','video','preserved')"),str(detection_library.__file__),'exec'),detection_library.__dict__)
 rows=detection_library.listing(root,wait=True,export=True)
 fields=('id','kind','video_id','sample_id','created','label','human_reviewed','image_url','frame_url','model_label','starred')
 rows=[{k:r[k] for k in fields if k in r} for r in rows]
 # Archive links are derived from publication receipts, not arbitrary user URLs.
 from archive_links import attach
 for start in range(0,len(rows),500):
  batch=[r for r in rows[start:start+500] if r.get('label')=='anomalous']
  attach(root,batch)
 import sqlite3
 from model_settings import state
 from object_model_scores import identity
 models=state(root)['models']
 score_path=root/'model-inspector/object-scores.sqlite'
 saved={}
 if score_path.exists():
  with sqlite3.connect(score_path.as_uri()+'?mode=ro',uri=True,timeout=2) as db:
   saved={r[0]:(r[1],r[2]) for r in db.execute('SELECT id,signature,results FROM scores')}
 for row in rows:
  old=saved.get(row['id']);results=json.loads(old[1]) if old and old[0]==identity(row,models) and old[1] else {}
  row['model_classifications']=[dict(results.get(m['lane'],{'state':'pending' if m.get('available') else 'unavailable'}),lane=m['lane'],version=m.get('version'),settings_revision=m.get('settings_revision',0)) for m in models]
 files['objects.json']=json.dumps(clean(rows),separators=(',',':')).encode()
 try:
  manual=json.loads(get('/api/objects?view=manual_recordings&limit=100',8091))
  files['manual.json']=json.dumps(clean(manual),separators=(',',':')).encode()
 except Exception:failures.append('manual recordings')
 try:files['camera.jpg']=get('/api/live/frame')
 except Exception:failures.append('camera frame')
 # Only public broadcast IDs and session times leave the station.
 try:
  ledger=json.loads((root.parent/'station-runtime/youtube/sessions.json').read_text())
  files['responses/youtube.json']=json.dumps(public_broadcasts(ledger,time.time())).encode()
 except (OSError,ValueError,KeyError):failures.append('youtube sessions')
 files['snapshot.json']=json.dumps(dict(schema=1,captured_epoch=time.time(),objects=len(rows),unavailable=failures)).encode()
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for name,raw in files.items():z.writestr(name,raw)
 print(base64.b64encode(out.getvalue()).decode())
if __name__=='__main__':export(Path('/Volumes/UFO-Field/uap-lab'),Path('/Users/ufo-field/ufo-field/uap-lab'),Path('/Volumes/UFO-Field/station-runtime/public-access'))
