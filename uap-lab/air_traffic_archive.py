"""Openly licensed public aircraft evidence, kept separate from the private radar feed."""
import contextlib, datetime, hashlib, json, math, re, sqlite3, time, zlib
from pathlib import Path
from urllib.error import HTTPError
import air_traffic as a
PROVIDER='adsb.lol'
LICENSE='https://opendatacommons.org/licenses/odbl/1-0/'
INTERVAL=180  # 480 requests/day, below the anonymous 500/day allowance.
MAX_OFFSET=210

def collect_due(root):
    state_path=a.base(root)/'public-collector-status.json';state=a.read(state_path,{})
    now=time.time()
    if now<state.get('next_attempt',0):return
    # Persist the budget before networking, so restarts do not burst requests.
    a.atomic(state_path,dict(status='requesting',next_attempt=now+INTERVAL))
    try:
        config=a.settings(root)
        url=f"https://api.adsb.lol/v2/point/{config['latitude']}/{config['longitude']}/{math.ceil(config['radius_nm'])}"
        snap=a.normalize(a.fetch_json(url),config,time.time())
        snap.update(provider=PROVIDER,provider_url='https://www.adsb.lol/',license='ODbL-1.0',license_url=LICENSE)
        a.store(root,snap,namespace='public-')
        a.atomic(state_path,dict(status='collecting',epoch=snap['sampled_epoch'],aircraft=len(snap['aircraft']),next_attempt=now+INTERVAL))
    except Exception as error:
        delay=INTERVAL
        if isinstance(error,HTTPError):
            if error.code in (400,401,403,404):delay=3600
            if error.code==429:
                with contextlib.suppress(ValueError):delay=max(delay,float(error.headers.get('Retry-After','3600')))
        a.atomic(state_path,dict(status='retrying',error=type(error).__name__,next_attempt=now+delay))

def public_sample(sample):
    """Allowlist; never export a radar address/center, a secret, or private-provider data."""
    if not isinstance(sample,dict) or sample.get('provider')!=PROVIDER or sample.get('license')!='ODbL-1.0':return None
    if not a.number(sample.get('sampled_epoch')):return None
    result={k:sample[k] for k in ('sampled_epoch','received_epoch') if k in sample}
    result['aircraft']=[{k:r[k] for k in ('hex','flight','r','t','latitude','longitude','position_epoch','altitude_ft','speed_knots','track_deg') if k in r} for r in sample.get('aircraft',[])]
    return result

def attach_public(root,folder,event):
    path=Path(folder)/'air-traffic-public.json'
    if path.exists():return
    sample=a.at_time(root,event.get('detected_epoch'),namespace='public-',max_age=MAX_OFFSET)
    clean=public_sample(sample)
    value=dict(schema=1,provider=PROVIDER,license='ODbL-1.0',license_url=LICENSE,
               event_id=event.get('id'),detection_epoch=event.get('detected_epoch'),
               status='available' if clean else 'unavailable',samples=[clean] if clean else [])
    a.atomic(path,value)

def epoch(value):
    if a.number(value):return value
    if isinstance(value,str):
        try:return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
        except ValueError:pass
    return None

def bundle(root,folder,manifest):
    folder=Path(folder);target=folder/'air-traffic.json';old=a.read(target,{})
    start=epoch(manifest.get('started_epoch')) or epoch(manifest.get('started_at'))
    end=epoch(manifest.get('ended_epoch')) or epoch(manifest.get('stopped_epoch')) or epoch(manifest.get('ended_at')) or epoch(manifest.get('completed_at'))
    known_end=end is not None
    if end is None:end=start
    samples={};events={}
    if old.get('schema')==1 and old.get('provider')==PROVIDER and old.get('license')=='ODbL-1.0':
        for s in old.get('samples',[]):
            cleaned=public_sample(dict(s,provider=PROVIDER,license='ODbL-1.0'))
            if cleaned:samples[cleaned['sampled_epoch']]=cleaned
        events={r['event_id']:r for r in old.get('detections',[]) if r.get('event_id')}
    if start and end and end>=start:
        try:
            with contextlib.closing(a.database(root,namespace='public-')) as db:
                rows=db.execute('SELECT body FROM snapshots WHERE epoch>=? AND epoch<=? ORDER BY epoch',(start-MAX_OFFSET,end)).fetchall()
            for row in rows:
                clean=public_sample(json.loads(zlib.decompress(row[0])))
                if clean:samples[clean['sampled_epoch']]=clean
        except (OSError,sqlite3.Error,ValueError,zlib.error):pass
    # Reviewed object ids identify their preserved capture-time public sidecars.
    annotations=a.read(folder/'review-annotations.json',{}).get('annotations',[])
    ids={r.get('event_id') for r in annotations}
    for key in ids:
        if not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{32}',key):continue
        side=a.read(Path(root)/'notifications/outbox'/key/'air-traffic-public.json',{})
        if side.get('provider')!=PROVIDER or side.get('license')!='ODbL-1.0':continue
        stamps=[]
        for s in side.get('samples',[]):
            clean=public_sample(dict(s,provider=PROVIDER,license='ODbL-1.0'))
            if clean:samples[clean['sampled_epoch']]=clean;stamps.append(clean['sampled_epoch'])
        events[key]=dict(event_id=key,detection_epoch=side.get('detection_epoch'),sample_epochs=stamps,status='available' if stamps else 'unavailable')
    ordered=sorted(samples);gaps=[]
    if start and end:
        cursor=start
        for stamp in ordered:
            if stamp+MAX_OFFSET<start or stamp>end:continue
            if stamp>cursor:gaps.append(dict(start_epoch=cursor,end_epoch=min(stamp,end)))
            cursor=max(cursor,stamp+MAX_OFFSET)
        if cursor<end:gaps.append(dict(start_epoch=cursor,end_epoch=end))
    value=dict(schema=1,session_id=folder.name,provider=PROVIDER,provider_url='https://www.adsb.lol/',
      attribution='Aircraft data © ADSB.lol contributors, licensed under ODbL 1.0.',license='ODbL-1.0',license_url=LICENSE,
      status='available' if samples else 'unavailable',window=dict(start_epoch=start,end_epoch=end,end_known=known_end),
      sampling_interval_seconds=INTERVAL,maximum_context_offset_seconds=MAX_OFFSET,coverage_gaps=gaps,
      qualification='Timestamped regional aircraft reports, not identification of a visual object. Sampling gaps and non-reporting aircraft are possible. Positions are not extrapolated. Radar center and address are excluded.',
      samples=[samples[k] for k in ordered],detections=sorted(events.values(),key=lambda r:r['event_id']))
    if value!=old:a.atomic(target,value)
    return target
