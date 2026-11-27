"""Preserved machine-label evidence, independent of the bounded collection cache."""
import hashlib,json,os,time,shutil
from pathlib import Path
from PIL import Image

def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value));temp.replace(path)

def preserve(root,rows,frames):
 corpus=root/'corpus';images=corpus/'images';images.mkdir(parents=True,exist_ok=True)
 path=corpus/'manifest.json';existing=json.loads(path.read_text()) if path.exists() else {}
 for row in rows:
  if row.get('human_confirmed') or row.get('label_source','machine')!='machine':raise ValueError('Human label cannot enter machine-label corpus')
  source=frames/(row['id']+'.png')
  if not source.is_file():continue
  with Image.open(source) as im:
   im=im.convert('RGB');digest=hashlib.sha256(f'{im.width}x{im.height}:RGB:'.encode()+im.tobytes()).hexdigest()
  if digest!=row['pixel_sha256']:raise ValueError('Machine crop pixel checksum mismatch')
  key=hashlib.sha256(json.dumps([row['id'],digest,row['label'],row.get('teacher_version')]).encode()).hexdigest()
  target=images/(key+'.png')
  if not target.exists():shutil.copyfile(source,target)
  existing.setdefault(key,dict(row,image='images/'+key+'.png',label_source='machine',human_confirmed=False,preserved_epoch=time.time()))
 save(path,existing)
 return existing

def machine_dataset(root,code,human_source):
 """Use the same reviewed foundation for scheduled and manual training."""
 from cascade_training import build_snapshot
 base=json.loads((Path(human_source)/'dataset.json').read_text())
 manifest=root/'corpus/manifest.json'
 source=json.loads(manifest.read_text()) if manifest.exists() else {}
 identity=hashlib.sha256(json.dumps([base['fingerprint'],source],sort_keys=True).encode()).hexdigest()
 frozen=root/'inputs'/(identity+'.json')
 if not frozen.exists():save(frozen,source)
 cfg=dict(code=str(code),lanes={'machine':{'root':str(root)}})
 cycle=dict(id=identity,stable_source=str(human_source),inputs={'machine':str(frozen)})
 folder=build_snapshot(cfg,cycle,'machine');data=json.loads((folder/'dataset.json').read_text())
 save(root/'dataset-current.json',dict(directory=str(folder),fingerprint=data['fingerprint'],examples=len(data['samples']),blockers=data['blockers'],training_lane='machine_only',human_training_counts=data['human_training_counts']))
 return folder,data['blockers']
