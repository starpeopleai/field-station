"""Content-addressed immutable training images, shared through hard links."""
import hashlib,os,stat,tempfile,json,time,fcntl
from pathlib import Path

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def store_image(path,data,pool):
 path,pool=Path(path),Path(pool);key=hashlib.sha256(data).hexdigest();obj=pool/key[:2]/(key+'.png');obj.parent.mkdir(parents=True,exist_ok=True)
 if obj.exists():
  if obj.is_symlink() or digest(obj)!=key:raise ValueError('Training object checksum mismatch')
 else:
  fd,name=tempfile.mkstemp(dir=obj.parent)
  try:
   with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
   os.chmod(name,0o444)
   try:os.link(name,obj)
   except FileExistsError:
    if obj.is_symlink() or digest(obj)!=key:raise ValueError('Training object checksum mismatch')
  finally:Path(name).unlink(missing_ok=True)
 path.parent.mkdir(parents=True,exist_ok=True)
 temporary=path.with_name(path.name+'.link-'+str(os.getpid()))
 try:os.link(obj,temporary);temporary.replace(path)
 finally:temporary.unlink(missing_ok=True)
 return obj

def deduplicate(paths,pool,status=None):
 pool=Path(pool);pool.mkdir(parents=True,exist_ok=True);verified={};seen_inodes=set();report=dict(scanned=0,linked=0,unique_objects=0,reclaimed_bytes=0,started_epoch=time.time(),errors=[])
 def save():
  if status:
   target=Path(status);temp=target.with_suffix('.tmp');temp.write_text(json.dumps(report));temp.replace(target)
 with (pool/'maintenance.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  for path in paths:
   path=Path(path)
   try:
    if path.is_symlink():raise ValueError('Refusing image symlink')
    before=path.stat()
    if not stat.S_ISREG(before.st_mode):continue
    if before.st_dev!=pool.stat().st_dev:raise ValueError('Image pool must share the source filesystem')
    report['scanned']+=1
    inode=(before.st_dev,before.st_ino)
    if inode in seen_inodes:continue
    key=digest(path);now=path.stat()
    if (now.st_ino,now.st_size,now.st_mtime_ns)!=(before.st_ino,before.st_size,before.st_mtime_ns):raise ValueError('Training image changed during verification')
    obj=pool/key[:2]/(key+'.png');obj.parent.mkdir(exist_ok=True)
    if not obj.exists():
     os.link(path,obj);os.chmod(obj,0o444);verified[key]=(obj.stat().st_ino,obj.stat().st_mtime_ns);report['unique_objects']+=1;seen_inodes.add(inode)
    else:
     if obj.is_symlink():raise ValueError('Unsafe training object')
     st=obj.stat();signature=(st.st_ino,st.st_mtime_ns)
     if verified.get(key)!=signature:
      if digest(obj)!=key:raise ValueError('Training object checksum mismatch')
      verified[key]=signature
     if st.st_ino!=before.st_ino:
      tmp=path.with_name(path.name+'.dedup-'+str(os.getpid()))
      try:os.link(obj,tmp);tmp.replace(path)
      finally:tmp.unlink(missing_ok=True)
      report['linked']+=1
      if before.st_nlink==1:report['reclaimed_bytes']+=before.st_blocks*512
     seen_inodes.add((st.st_dev,st.st_ino))
    if report['scanned']%1000==0:report['updated_epoch']=time.time();save()
   except (OSError,ValueError) as e:
    report['errors'].append(dict(path=str(path),error=str(e)));save();raise
  report['finished_epoch']=time.time();save()
 return report
