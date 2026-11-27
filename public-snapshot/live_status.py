"""Publish a small, independently refreshed broadcast feed; no detection export needed."""
import argparse,fcntl,json,re,shlex,subprocess,time
from pathlib import Path

EXPORT = '''from pathlib import Path
import json,re,time
p=Path('/Volumes/UFO-Field/station-runtime/youtube/sessions.json')
d=json.loads(p.read_text());active=d.get('active_video_id');entries=d.get('sessions',{})
e=next((v for v in entries.values() if v.get('video_id')==active and v.get('state')=='live'),{})
checked=float(d.get('last_api_check') or e.get('confirmed_live_epoch') or 0)
now=time.time();valid=isinstance(active,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{11}',active))
print(json.dumps(dict(schema=1,active_video_id=active if valid and e and 0<=now-checked<900 else None,confirmed_at=checked,state='live' if valid and e and 0<=now-checked<900 else 'unavailable')))
'''

def publish(runtime,helper,repo='starpeopleai/field-station'):
 runtime.mkdir(parents=True,exist_ok=True)
 with (runtime/'publish.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return
  command='/Users/ufo-field/ufo-field/venv/bin/python -c '+shlex.quote(EXPORT)
  raw=subprocess.check_output(['/usr/bin/python3',str(helper),command],text=True,timeout=45)
  data=json.loads(raw);active=data.get('active_video_id')
  if active is not None and not re.fullmatch(r'[A-Za-z0-9_-]{11}',active):raise ValueError('Invalid public broadcast ID')
  content=json.dumps(data,sort_keys=True,separators=(',',':'))+'\n'
  receipt=runtime/'published.json'
  previous=json.loads(receipt.read_text()) if receipt.exists() else {}
  if previous.get('content')==content:return
  def api(path,body=None):
   args=['gh','api','repos/'+repo+'/'+path]
   if body is not None:args+=['--method','POST','--input','-']
   return json.loads(subprocess.check_output(args,input=None if body is None else json.dumps(body).encode(),timeout=45))
  blob=api('git/blobs',dict(content=content,encoding='utf-8'))
  tree=api('git/trees',dict(tree=[dict(path='live.json',mode='100644',type='blob',sha=blob['sha'])]))
  commit=api('git/commits',dict(message='Current confirmed broadcast',tree=tree['sha'],parents=[]))
  ref='heads/live-status'
  found=subprocess.run(['gh','api','repos/'+repo+'/git/ref/'+ref],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=45)
  if found.returncode==0:
   subprocess.run(['gh','api','repos/'+repo+'/git/refs/'+ref,'--method','PATCH','--input','-'],input=json.dumps(dict(sha=commit['sha'],force=True)).encode(),stdout=subprocess.DEVNULL,check=True,timeout=45)
  else:api('git/refs',dict(ref='refs/'+ref,sha=commit['sha']))
  temp=receipt.with_suffix('.tmp');temp.write_text(json.dumps(dict(content=content,commit=commit['sha'],published_at=time.time())));temp.replace(receipt)
  print(json.dumps(dict(published=True,**data)),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--ssh-helper',type=Path,required=True);a=p.parse_args();publish(a.runtime,a.ssh_helper)
