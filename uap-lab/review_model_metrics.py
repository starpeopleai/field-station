"""Prospective, immutable model predictions compared with durable human reviews.

No inference or training occurs in the review-save path. Missing pre-review
predictions remain missing, rather than being reconstructed after seeing labels.
"""
import copy,json,math,time
from datetime import datetime
from object_model_scores import connect
from model_settings import LANES,state


def initialize(db):
 db.execute('CREATE TABLE IF NOT EXISTS reviewed_predictions (id TEXT, lane TEXT, version TEXT, revision INTEGER, captured REAL, day TEXT, light TEXT, reviewed REAL, prediction TEXT, label TEXT, deleted INTEGER, PRIMARY KEY(id,lane))')
 db.execute('CREATE TABLE IF NOT EXISTS reviewed_prediction_records (id TEXT PRIMARY KEY, reviewed REAL, payload TEXT)')
 db.execute('CREATE INDEX IF NOT EXISTS reviewed_prediction_period ON reviewed_predictions(captured)')


def freeze(data,record,previous):
 record=copy.deepcopy(record)
 # A later correction changes the ground truth, never its original prediction.
 if previous.get('native_crop_sha256')==record.get('native_crop_sha256') and 'pre_review_models' in previous:
  record['pre_review_models']=copy.deepcopy(previous['pre_review_models']);return record
 cutoff=min(record['reviewed_epoch'],previous.get('reviewed_epoch',record['reviewed_epoch']))
 sample=record.get('sample_id',record['event_id']);event=record['event_id']
 keys=(event if sample==event else 'review:'+event+':'+sample,'review:'+event+':'+sample)
 frozen=dict(first_review_epoch=cutoff,captured_epoch=None,predictions={})
 with connect(data,timeout=2) as db:
  rows=db.execute('SELECT scored,captured,results FROM prediction_history WHERE id IN (?,?) AND crop=? AND scored<=? ORDER BY scored DESC',(*keys,record.get('native_crop_sha256'),cutoff)).fetchall()
  for scored,captured,serialized in rows:
   for lane,prediction in json.loads(serialized).items():
    if lane not in LANES or lane in frozen['predictions']:continue
    if prediction.get('state')!='ready' or prediction.get('label') not in ('anomalous','not_anomalous'):continue
    if prediction.get('scored_epoch',scored)>cutoff:continue
    frozen['predictions'][lane]=dict(prediction,recorded_epoch=scored)
    if frozen['captured_epoch'] is None:frozen['captured_epoch']=captured
 record['pre_review_models']=frozen
 return record


def commit_review(data,record):
 from observation_metrics import TZ,daylight
 frozen=record.get('pre_review_models',{});stamp=frozen.get('captured_epoch');day=light=None
 if isinstance(stamp,(int,float)) and math.isfinite(stamp) and stamp>0:
  local=datetime.fromtimestamp(stamp,TZ);day=local.date().isoformat();rise,setting=daylight(local.date());light='daytime' if rise<=stamp<setting else 'nighttime'
 else:stamp=None
 with connect(data,timeout=2) as db:
  initialize(db)
  db.execute('INSERT INTO reviewed_prediction_records VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET reviewed=excluded.reviewed,payload=excluded.payload WHERE excluded.reviewed>=reviewed_prediction_records.reviewed',(record.get('sample_id',record['event_id']),record['reviewed_epoch'],json.dumps(record,allow_nan=False)))
  for lane in LANES:
   p=frozen.get('predictions',{}).get(lane,{})
   db.execute('INSERT INTO reviewed_predictions VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id,lane) DO UPDATE SET version=excluded.version,revision=excluded.revision,captured=excluded.captured,day=excluded.day,light=excluded.light,reviewed=excluded.reviewed,prediction=excluded.prediction,label=excluded.label,deleted=excluded.deleted WHERE excluded.reviewed>=reviewed_predictions.reviewed',
    (record.get('sample_id',record['event_id']),lane,p.get('version'),p.get('settings_revision',0),stamp,day,light,record['reviewed_epoch'],p.get('label'),record.get('label'),int(bool(record.get('deleted') or not record.get('human_confirmed')))))


def rates(row):
 total=sum(row[k] for k in ('tp','fp','tn','fn'));negative=row['fp']+row['tn'];positive=row['tp']+row['fn'];alerts=row['tp']+row['fp']
 return dict(row,reviewed=total,negative_reviews=negative,reviewed_alerts=alerts,rate=row['fp']/negative if negative else None,false_alarm_share=row['fp']/alerts if alerts else None,recall=row['tp']/positive if positive else None,accuracy=(row['tp']+row['tn'])/total if total else None)


def snapshot(data,now=None):
 now=time.time() if now is None else now;series={};models=state(data)['models']
 def entry(lane,version,revision):
  key=f'{lane}:{version}:{revision}'
  if key not in series:series[key]=dict(key=key,lane=lane,label=LANES[lane],version=version,settings_revision=revision,active=any(m['lane']==lane and m.get('version')==version and m.get('settings_revision',0)==revision for m in models),periods={})
  return series[key]
 for m in models:
  if m.get('available'):entry(m['lane'],m['version'],m.get('settings_revision',0))
 with connect(data,timeout=2) as db:
  initialize(db)
  missing=db.execute('SELECT COUNT(DISTINCT id) FROM reviewed_predictions WHERE deleted=0 AND prediction IS NULL').fetchone()[0]
  for days in (1,7,30,0):
   buckets={}
   rows=db.execute('SELECT lane,version,revision,day,light,prediction,label,COUNT(*) FROM reviewed_predictions WHERE deleted=0 AND captured>=? AND captured<=? AND prediction IN (?,?) AND label IN (?,?) GROUP BY lane,version,revision,day,light,prediction,label',(now-days*86400 if days else 0,now,'anomalous','not_anomalous','anomalous','not_anomalous'))
   for lane,version,revision,day,light,prediction,label,count in rows:
    e=entry(lane,version,revision);key=(e['key'],light);bucket=buckets.setdefault(key,{}).setdefault(day,dict(day=day,tp=0,fp=0,tn=0,fn=0));bucket[('t' if prediction==label else 'f')+('p' if prediction=='anomalous' else 'n')]+=count
   for e in series.values():
    e['periods'][str(days)]={}
    for light in ('daytime','nighttime'):
     points=[rates(v) for _,v in sorted(buckets.get((e['key'],light),{}).items())];totals=rates({k:sum(p[k] for p in points) for k in ('tp','fp','tn','fn')});e['periods'][str(days)][light]=dict(totals,points=points)
 for e in series.values():
  e['summaries']={period:rates({k:sum(v[k] for v in lights.values()) for k in ('tp','fp','tn','fn')}) for period,lights in e['periods'].items()}
 timelines=[]
 for lane in LANES:
  entry=dict(lane=lane,periods={})
  for period in ('1','7','30','0'):
   entry['periods'][period]={}
   for light in ('daytime','nighttime'):
    days={}
    for e in series.values():
     if e['lane']!=lane:continue
     for p in e['periods'].get(period,{}).get(light,{}).get('points',[]):
      total=days.setdefault(p['day'],dict(day=p['day'],tp=0,fp=0,tn=0,fn=0,models=[]))
      for k in ('tp','fp','tn','fn'):total[k]+=p[k]
      total['models'].append(dict(version=e['version'],revision=e['settings_revision']))
    points=[rates(p) for _,p in sorted(days.items())]
    entry['periods'][period][light]=dict(rates({k:sum(p[k] for p in points) for k in ('tp','fp','tn','fn')}),points=points)
  timelines.append(entry)
 return dict(updated_epoch=now,timelines=timelines,series=list(series.values()),missing_predictions=missing,scope='Predictions recorded before human review; grouped by trained model and decision settings.')
