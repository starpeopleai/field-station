"""Confirm committed request receipts without waiting behind another save batch."""
import hashlib,json,re
from pathlib import Path
from classification_taxonomy import canonical_label

def confirmed(data,item):
    key=item.get('id','');request=item.get('request_id','');label=canonical_label(item.get('label'))
    if label not in ('anomalous','not_anomalous') or not isinstance(request,str) or not re.fullmatch('[a-f0-9]{32}',request):return None
    if isinstance(key,str) and re.fullmatch('[a-f0-9]{32}',key):event=sample=key;prefixes=('quick-label:','object-label:')
    else:
        parts=key.split(':') if isinstance(key,str) else []
        if len(parts)!=3 or parts[0]!='review' or any(not re.fullmatch('[a-f0-9]{32}',v) for v in parts[1:]):return None
        _,event,sample=parts;prefixes=('object-label:',)
    for prefix in prefixes:
        message=prefix+request;digest=hashlib.sha256(('station_web_review:'+message).encode()).hexdigest()
        try:receipt=json.loads((Path(data)/'email-reviews/history'/(digest+'.json')).read_text())
        except (OSError,ValueError):continue
        if (receipt.get('event_id')==event and receipt.get('sample_id',event)==sample
            and receipt.get('message_id')==message and receipt.get('human_confirmed')
            and not receipt.get('deleted') and canonical_label(receipt.get('label'))==label):
            return dict(saved=True,id=key,label=label,request_id=request)
    return None

def cleared(data,item):
    """A user's explicit backlog deletion supersedes stale browser save requests."""
    key=item.get('id','')
    if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{32}',key):return None
    def read(path):
        try:return json.loads(path.read_text())
        except (OSError,ValueError):return {}
    marker=read(Path(data).parent/'notifications/outbox'/key/'label-queue-dismissed.json')
    if (marker.get('dismissed') is not True or marker.get('reason')!='User cleared labeling backlog'
        or not re.fullmatch('[a-f0-9]{32}',str(marker.get('queue_clear_id','')))):return None
    current=read(Path(data)/'email-reviews/examples'/key/'review.json')
    if current.get('human_confirmed') and not current.get('deleted'):return None
    return dict(saved=False,discarded=True,reason='backlog_cleared',id=key,request_id=item.get('request_id'),error='Detection deleted by your backlog clear; no label was saved.')

def split(data,items,reset_before=0):
    done=[];remaining=[]
    for item in items:
        if reset_before and (not isinstance(item.get('queued_at'),(int,float)) or item['queued_at']<=reset_before):
            remaining.append(item);continue
        result=confirmed(data,item) or cleared(data,item)
        if result is None:remaining.append(item)
        else:done.append(result)
    return done,remaining
