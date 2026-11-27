"""Recover a missing review crop only when its original checksum is reproduced."""
import hashlib,io,math
from pathlib import Path
from PIL import Image

def verified_crop(image,event):
 bounds=event.get('bounds',[])
 if len(bounds)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) or int(v)!=v for v in bounds):return None
 x,y,w,h=map(int,bounds)
 if min(x,y)<0 or min(w,h)<1 or x+w>image.width or y+h>image.height:return None
 modes=['RGB'] if event.get('source_color_space')=='RGB' else ['L','RGB']
 for mode in modes:
  out=io.BytesIO();image.convert(mode).crop((x,y,x+w,y+h)).save(out,format='PNG');raw=out.getvalue()
  if hashlib.sha256(raw).hexdigest()==event.get('native_crop_sha256'):return raw
 return None

def frames(path,seconds):
 import av
 with av.open(str(path)) as src:
  src.streams.video[0].codec_context.thread_count=1
  src.seek(max(0,int((seconds-.25)*1000000)))
  for frame in src.decode(video=0):
   if frame.pts is None:continue
   t=float(frame.pts*frame.time_base)
   if t>seconds+.003:break
   if abs(t-seconds)<=.003:yield frame.to_image()

def recover(folder,event):
 folder=Path(folder)
 for name in ['color-native-object.png']:
  path=folder/name
  if path.is_file() and not path.is_symlink():
   raw=path.read_bytes()
   if hashlib.sha256(raw).hexdigest()==event.get('native_crop_sha256'):return raw
 for name in ['source-frame.png']:
  path=folder/name
  if path.is_file() and not path.is_symlink():
   with Image.open(path) as image:
    raw=verified_crop(image,event)
    if raw:return raw
 from review_color import sources
 for index,(path,seconds) in enumerate(sources(folder,event)):
  if index>=4:break
  try:
   for image in frames(path,seconds):
    raw=verified_crop(image,event)
    if raw:return raw
  except (OSError,ValueError):continue
 raise ValueError('Original review image could not be recovered. Your label has not been saved.')
