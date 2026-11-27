"""Publish a logical queue clear before physical media cleanup."""
import fcntl,json,math,uuid
from pathlib import Path

def mark(data,cutoff,request_id):
 if not isinstance(cutoff,(int,float)) or isinstance(cutoff,bool) or not math.isfinite(cutoff):raise ValueError('Invalid queue cutoff')
 data=Path(data)
 with (data/'review-queue-clear.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  path=data/'review-queue-cleared.json'
  try:old=json.loads(path.read_text())
  except FileNotFoundError:old={}
  if old.get('cutoff_epoch',float('-inf'))>cutoff:return
  tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
  tmp.write_text(json.dumps(dict(cutoff_epoch=cutoff,request_id=request_id,phase='cleanup_pending')));tmp.replace(path)
