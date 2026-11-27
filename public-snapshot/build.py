"""Build the public UI and compact dataset on an external SSD, never copy recordings."""
import argparse,concurrent.futures,hashlib,json,os,re,shutil,time
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from PIL import Image,ImageOps
from export_field import clean

def write(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,separators=(',',':'),allow_nan=False))
def version_assets(raw,out):
 def replace(match):
  path=out/match[2].lstrip('/')
  if not path.is_file():return match[0]
  return match[1]+match[2]+'?snapshot='+hashlib.sha256(path.read_bytes()).hexdigest()[:12]
 return re.sub(r"((?:src|href)=[\"'])(/[^\"'?#]+\.(?:js|css))(?:\?[^\"']*)?",replace,raw)

def build(source,out,training):
 training=training.resolve();import fcntl
 pin=(training/'backup-read.lock').open('a');fcntl.flock(pin,fcntl.LOCK_SH)
 out.mkdir(parents=True,exist_ok=True);(out/'media').mkdir(exist_ok=True)
 # Fonts have nested directories; copy exact exported static files, never private source trees.
 for p in source.rglob('*'):
  rel=p.relative_to(source)
  if p.is_file() and rel.parts[0] not in ('pages','responses') and p.suffix in ('.js','.css','.woff2','.png','.jpg','.webp','.svg','.txt'):
   dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
 shell=out/'app-shell.js';js=shell.read_text()
 hash_marker="function showModelStatus(hash,state){"
 pip_marker="function renderBadge(){"
 if hash_marker not in js or pip_marker not in js:raise ValueError('Snapshot UI status contract changed')
 js=js.replace(hash_marker,hash_marker+"if(window.FIELD_PUBLIC_SNAPSHOT){if(hash)confirmedModelHash=hash;modelHash.textContent=(confirmedModelHash?confirmedModelHash.slice(0,12):'Model unavailable')+' · at snapshot';modelHash.title='Last confirmed model reported in this saved snapshot.';return;}",1)
 js=js.replace(pip_marker,pip_marker+"if(window.FIELD_PUBLIC_SNAPSHOT){badge.textContent='Snapshot';badge.dataset.state='snapshot';return;}",1)
 js=js.replace(' let instance=null,interrupted=false,failures=0,dialog=null,focus=null;', ' if(window.FIELD_PUBLIC_SNAPSHOT)return;\n let instance=null,interrupted=false,failures=0,dialog=null,focus=null;',1)
 shell.write_text(js)
 app=out/'app.js';js=app.read_text()
 marker="$ ('rfStatus').textContent=".replace('$ (','$(')
 if marker not in js:raise ValueError('RF status renderer contract changed')
 js=js.replace(marker,marker+"window.FIELD_PUBLIC_SNAPSHOT?'Saved RF snapshot':",1)
 js=js.replace("if(!fresh){ctx.fillStyle=palette.ink;", "if(!fresh&&!window.FIELD_PUBLIC_SNAPSHOT){ctx.fillStyle=palette.ink;")
 app.write_text(js)
 shutil.copy2(Path(__file__).with_name('snapshot.js'),out/'snapshot.js')
 for name in ('LICENSE','LICENSE-CONTENT.txt','CONTENT-LICENSE.md','NOTICE.md','THIRD_PARTY_NOTICES.md'):
  license_file=Path(__file__).parent.parent/name
  if license_file.is_file():shutil.copy2(license_file,out/name)
 for name in ('public-readonly.js','public-readonly.css'):shutil.copy2(Path(__file__).parent.parent/'public-access'/name,out/name)
 for name in ('rf-experiment.js','rf-experiment.css'):shutil.copy2(Path(__file__).parent.parent/'uap-lab/static'/name,out/name)
 for p in (source/'pages').glob('*.html'):
  raw=p.read_text().replace('<head>','<head><script src="/snapshot.js"></script>',1)
  if p.stem=='index':raw=raw.replace('</head>','<link rel="stylesheet" href="/rf-experiment.css"><script defer src="/rf-experiment.js"></script></head>',1)
  raw=version_assets(raw,out)
  dest=out/'index.html' if p.stem=='index' else out/p.stem/'index.html';dest.parent.mkdir(exist_ok=True);dest.write_text(raw)
 rows=json.loads((source/'objects.json').read_text());rows.sort(key=lambda r:(r.get('created',0),r['id']),reverse=True)
 annotation_cache={};cache_lock=__import__('threading').Lock()
 def image_for(row):
  key=hashlib.sha256(row['id'].encode()).hexdigest();dest=out/'media'/(key+'.webp')
  fallback=source/'media'/(key+'.webp')
  if fallback.is_file():shutil.copy2(fallback,dest);return '/media/'+dest.name
  q=parse_qs(urlsplit(row.get('image_url','')).query);kind=q.get('source',[''])[0];vid=q.get('id',[''])[0];aid=q.get('annotation',[''])[0]
  if kind=='review':
   folder=training/'email-reviews/examples'/aid
   record=folder/'review.json'
   if not record.is_file():return None
   r=json.loads(record.read_text())
   if r.get('deleted') or r.get('event_id')!=vid:return None
   image=folder/'native-object.png';color=folder/'color-native-object.png';meta=folder/'color-review.json'
   if color.is_file() and meta.is_file():
    m=json.loads(meta.read_text())
    if m.get('original_crop_sha256')==r.get('native_crop_sha256') and m.get('event_id')==vid:image=color
  elif kind in ('video','preserved'):
   folder=training/'videos'/vid
   with cache_lock:
    if vid not in annotation_cache:
     p=folder/'annotations.json';annotation_cache[vid]={a['id']:a for a in json.loads(p.read_text())} if p.exists() else {}
    a=annotation_cache[vid].get(aid)
   if not a:return None
   image=folder/a['image']
   if not image.resolve().is_relative_to(folder.resolve()):return None
  else:return None
  if not image.is_file():return None
  if not dest.exists() or dest.stat().st_mtime<image.stat().st_mtime:
   with Image.open(image) as im:
    im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((320,320));im.save(dest,'WEBP',quality=78,method=3,exif=b'')
  return '/media/'+dest.name
 missing=[];counts={k:0 for k in ('all','anomalous','not_anomalous','human_reviewed','needs_review','human_reviewed_anomalous','starred')}
 def prepare(row):
  try:image=image_for(row)
  except (OSError,ValueError,KeyError):image=None
  r=clean(row);r['image_url']=r['frame_url']=image or '/unavailable.svg'
  if not image:missing.append(r['id'])
  return r
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:rows=list(pool.map(prepare,rows))
 for r in rows:
  counts['all']+=1;counts[r['label']]+=1;counts['human_reviewed' if r['human_reviewed'] else 'needs_review']+=1;counts['starred']+=bool(r.get('starred'));counts['human_reviewed_anomalous']+=r['human_reviewed'] and r['label']=='anomalous'
 model_sets=[];model_indices={}
 for row in rows:
  models=row.get('model_classifications',[]);key=json.dumps(models,sort_keys=True)
  if key not in model_indices:model_indices[key]=len(model_sets);model_sets.append(models)
  row['model_classifications']=model_indices[key]
 wanted={Path(r['image_url']).name for r in rows}
 for image in (out/'media').glob('*.webp'):
  if image.name not in wanted:image.unlink()
 fields=sorted({k for r in rows for k in r});manual=json.loads((source/'manual.json').read_text()) if (source/'manual.json').exists() else {'items':[],'total':0}
 # Manual video binaries stay on the field/archive volumes; public links are retained.
 for r in manual.get('items',[]):
  r.pop('review_url',None);r.pop('video_url',None);r['image_url']=r['frame_url']='/unavailable.svg'
 sources={'detections':len(rows),'manual_recordings':manual.get('total',0)}
 write(out/'snapshot/objects.json',dict(model_sets=model_sets,fields=fields,rows=[[r.get(k) for k in fields] for r in rows],counts=counts,source_counts=sources))
 write(out/'snapshot/manual.json',manual)
 write(out/'snapshot/camera-controls.json',json.loads((source/'camera-controls.json').read_text()) if (source/'camera-controls.json').exists() else {})
 meta=json.loads((source/'snapshot.json').read_text());meta.update(routes={},missing_thumbnails=len(missing))
 for p in (source/'responses').glob('*.json'):
  # Route names are recorded separately because hyphenated API names are legitimate.
  route='/api/'+p.stem
  for prefix in ('live-','model-publication-','recognition-'):
   if p.stem.startswith(prefix):route='/api/'+prefix[:-1]+'/'+p.stem[len(prefix):]
  dest=out/'snapshot'/p.name;write(dest,clean(json.loads(p.read_text())));meta['routes'][route]='/snapshot/'+p.name
 write(out/'snapshot/manifest.json',meta)
 write(source/'missing-thumbnails.json',missing)
 (out/'unavailable.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240" viewBox="0 0 320 240"><rect width="320" height="240" fill="#17191e"/><text x="160" y="120" text-anchor="middle" fill="#ccc" font-family="sans-serif" font-size="13">Frame unavailable in snapshot</text></svg>')
 (out/'CNAME').write_text('data.starpeople.ai\n');(out/'.nojekyll').touch()
 print(json.dumps(dict(objects=len(rows),missing_thumbnails=len(missing),bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file()))))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--training',type=Path,required=True);a=p.parse_args();build(a.source,a.output,a.training)
