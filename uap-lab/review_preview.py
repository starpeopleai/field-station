"""Human corrections of exact, server-generated live preview images."""
import hashlib,io,re,time
from pathlib import Path
from PIL import Image
from model_settings import read
from email_training import store_review

def save_correction(data,value):
 data=Path(data);key=value.get('id','');label=value.get('label');request=value.get('request_id','')
 if not isinstance(key,str) or not re.fullmatch('preview-[a-f0-9]{32}',key):raise ValueError('Invalid preview frame')
 if label not in ('anomalous','not_anomalous') or not isinstance(request,str) or not re.fullmatch('[a-f0-9]{32}',request):raise ValueError('Invalid correction')
 sample=key[8:];root=data/'model-inspector/live-preview'
 previous=read(data/'email-reviews/examples'/sample/'review.json',{})
 receipt=read(data/'email-reviews/history'/(hashlib.sha256(('live_preview_review:'+request).encode()).hexdigest()+'.json'),{})
 if receipt:
  if receipt.get('sample_id')!=sample or receipt.get('label')!=label:raise ValueError('Correction request already used')
  return dict(saved=True,id=key,label=label)
 metadata=read(root/(key+'.json'),{})
 if previous and previous.get('source_preview_id')==key:
  raw=(data/'email-reviews/examples'/sample/'native-object.png').read_bytes();metadata=previous
 else:
  if not metadata:raise ValueError('Preview expired. Refresh the frames before reviewing.')
  raw=(root/(key+'.png')).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=metadata.get('native_crop_sha256'):raise ValueError('Preview image verification failed')
 with Image.open(io.BytesIO(raw)) as im:w,h=im.size
 record=dict(schema=1,event_id=sample,sample_id=sample,source_preview_id=key,source='live_preview_review',message_id=request,reviewer='station_web_ui',reviewed_epoch=time.time(),label=label,human_confirmed=True,binary_anomalous=label=='anomalous',multiclass_ready=True,generation=metadata['generation'],pts_seconds=metadata.get('pts_seconds'),detected_epoch=metadata.get('detected_epoch'),captured_epoch=metadata.get('detected_epoch'),bounds=[0,0,w,h],native_crop_sha256=metadata['native_crop_sha256'],source_color_space='RGB',review_scope='full_frame',model=metadata.get('model','live-preview'))
 store_review(data,record,raw)
 from detection_library import invalidate
 invalidate()
 return dict(saved=True,id=key,label=label)
