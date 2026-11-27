"""External drive capacity snapshots; no recursive scans or network reads in the UI."""
import json,subprocess,time,threading,plistlib
from pathlib import Path
_CACHE={};_LOCK=threading.Lock()
ROLES={'UFO-Buffer':'Video buffer','UFO-Field-Working-Files':'Field working files','UFO-Training':'Training data and models','UFO-Data':'Observation data','UFO-Archive':'Archives and backups','UFO-Media':'Media','UFO-Working-Files':'Projects and working files','UFO-Temp':'Temporary storage'}
def collect(machine):
 result=subprocess.run(['/bin/df','-kP'],capture_output=True,text=True,timeout=4,check=True)
 pools={}
 try:
  apfs=plistlib.loads(subprocess.run(['/usr/sbin/diskutil','apfs','list','-plist'],capture_output=True,timeout=4,check=True).stdout)
  for pool in apfs.get('Containers',[]):
   for volume in pool.get('Volumes',[]):pools['/dev/'+volume['DeviceIdentifier']]=dict(id=pool['ContainerReference'],capacity=pool['CapacityCeiling'],used=pool['CapacityCeiling']-pool['CapacityFree'])
 except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):pass
 rows=[];totals={}
 for line in result.stdout.splitlines()[1:]:
  parts=line.split(None,5)
  if len(parts)!=6:continue
  device,total,used,free,percent,mount=parts
  if not mount.startswith('/Volumes/') or mount in ('/Volumes/Macintosh HD','/Volumes/Recovery'):continue
  try:total,used,free=[int(n)*1024 for n in (total,used,free)]
  except ValueError:continue
  group=pools.get(device,dict(id=device,capacity=total,used=used));totals[group['id']]=group
  name=Path(mount).name
  rows.append(dict(name=name,machine=machine,role=ROLES.get(name,'External storage'),capacity_bytes=total,used_bytes=used,free_bytes=free,used_percent=round(100*used/total,1) if total else 0))
 return dict(machine=machine,updated_epoch=time.time(),drives=sorted(rows,key=lambda r:r['name']),status='available',total_capacity_bytes=sum(v['capacity'] for v in totals.values()),total_used_bytes=sum(v['used'] for v in totals.values()))
def read(path):
 try:return json.loads(Path(path).read_text())
 except (OSError,ValueError):return {}
def refresh():
 try:_CACHE.update(collect('Field'))
 except (OSError,ValueError,subprocess.SubprocessError):_CACHE['status']='unavailable'
 finally:_LOCK.release()
def status(root):
 if time.time()-_CACHE.get('updated_epoch',0)>30 and _LOCK.acquire(False):threading.Thread(target=refresh,daemon=True).start()
 field=dict(_CACHE) if _CACHE else dict(machine='Field',status='loading',drives=[])
 hq=read(Path(root)/'storage-status/hq.json') or dict(machine='HQ',status='unavailable',drives=[])
 if hq.get('updated_epoch') and time.time()-hq['updated_epoch']>180:hq=dict(hq,status='stale')
 return dict(machines=[field,hq])
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--machine',required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 value=collect(args.machine);args.output.parent.mkdir(parents=True,exist_ok=True);tmp=args.output.with_suffix('.tmp');tmp.write_text(json.dumps(value));tmp.replace(args.output)
