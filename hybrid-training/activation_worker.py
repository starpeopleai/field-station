"""Deliver explicit live-model selections; never select a model automatically."""
import base64,fcntl,hashlib,json,os,shlex,subprocess,sys,tarfile,time
from pathlib import Path
from model_inspector_sync import read,rpc,folder_for
PREFIX="import sys,json;from pathlib import Path;sys.path[:0]=['/Users/ufo-field/ufo-field/uap-lab','/Users/ufo-field/ufo-field/uap-lab/recognition'];from model_activation import update,status,next_request;from model_settings import read;data=Path('/Volumes/UFO-Field-Working-Files/uap-lab');"

def remote(cfg,code):return json.loads(rpc(cfg,PREFIX+code))
def change(cfg,job,**fields):return remote(cfg,'print(json.dumps(update(data,'+repr(job['id'])+',**'+repr(fields)+')))')

def upload(archive,destination):
 credentials={}
 for line in Path('/Users/ufo-files-agent/m6-field.creds').read_text().splitlines():
  key,sep,value=line.partition(':')
  if sep:credentials[key.strip().lower()]=value.strip()
 env=os.environ.copy();env.update(SSH_ASKPASS='/Users/ufo-files-agent/field-migration/ssh-askpass.py',SSH_ASKPASS_REQUIRE='force',DISPLAY='codex-ssh-askpass')
 command=['/usr/bin/ssh','-o','ConnectTimeout=15','-o','NumberOfPasswordPrompts=1','-o','StrictHostKeyChecking=accept-new',credentials['username']+'@'+credentials['ip'],shlex.join(['/bin/sh','-c','cat > '+shlex.quote(destination)])]
 with archive.open('rb') as stream:subprocess.run(command,stdin=stream,env=env,start_new_session=True,check=True,timeout=300,capture_output=True)

def cycle(cfg):
 root=Path(cfg['root']);root.mkdir(parents=True,exist_ok=True)
 with (root/'activation-worker.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return
  job=remote(cfg,"print(json.dumps(next_request(data)))")
  if job.get('phase') not in ('queued','preparing','activating','monitoring'):return
  try:
   if job['phase']=='monitoring':
    live=remote(cfg,'print(json.dumps(status(data)))')
    if live['lane']!=job['lane'] or live['version']!=job['version']:
     change(cfg,job,phase='failed',error='Another deployment replaced this selection.');return
    if live['ready']:change(cfg,job,phase='live',error=None,confirmed_epoch=time.time())
    elif time.time()-job.get('activated_epoch',time.time())>180:change(cfg,job,phase='failed',error='Runtime has not confirmed activation. Check the station status before retrying.')
    return
   training=read(Path(cfg['human_root'])/'status.json',{})
   if training.get('phase') in ('snapshotting','preparing','training','evaluating','activating','activation_pending'):
    change(cfg,job,phase='queued',error='Waiting for the current training deployment to finish.');return
   lane=job['lane'];lane_root=Path(cfg[{'human':'human_root','experimental':'experimental_root','hybrid':'hybrid_root','machine':'machine_root','rotation':'rotation_root'}[lane]])
   folder=folder_for(lane_root,job['version'],read(lane_root/'status.json',{}))
   work=root/'activations'/job['id'];work.mkdir(parents=True,exist_ok=True)
   change(cfg,job,phase='preparing',error=None)
   dataset=read(folder/'dataset.json');row=next(r for r in dataset['samples'] if (folder/r['image']).is_file());probe=folder/row['image']
   if probe.is_symlink() or not probe.resolve().is_relative_to(folder.resolve()):raise ValueError('Unsafe runtime probe')
   (work/'probe.png').write_bytes(probe.read_bytes())
   archive=work/'selected.tar.gz'
   with tarfile.open(archive,'w:gz') as tar:
    for name in ('candidate.mlpackage','candidate-policy.json','candidate-weights.pt'):tar.add(folder/name,arcname=name)
    tar.add(work/'probe.png',arcname='probe.png')
   digest=hashlib.sha256(archive.read_bytes()).hexdigest();destination='/Volumes/UFO-Field-Working-Files/model-selections/'+job['id']
   remote(cfg,"p=Path("+repr(destination)+");assert Path('/Volumes/UFO-Field-Working-Files').is_mount();p.mkdir(parents=True,exist_ok=True);print('{}')")
   upload(archive,destination+'/selected.tar.gz')
   remote(cfg,"import hashlib,tarfile;p=Path("+repr(destination)+");a=p/'selected.tar.gz';assert hashlib.sha256(a.read_bytes()).hexdigest()=="+repr(digest)+";\nwith tarfile.open(a) as t:t.extractall(p,filter='data')\na.unlink();print('{}')")
   archive.unlink();change(cfg,job,phase='activating',error=None)
   remote(cfg,"sys.path.insert(0,'/Users/ufo-field/ufo-field/uap-lab/auto_training');from activate_selected import activate;print(json.dumps(activate(data,Path("+repr(destination)+"),"+repr(job['id'])+")))")
  except Exception as exc:change(cfg,job,phase='failed',error=str(exc)[:500]);raise
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--config',required=True);a=p.parse_args();cycle(read(a.config))
