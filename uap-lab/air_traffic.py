"""Private ADS-B context. No automatic visual identification or public redistribution."""
import argparse, contextlib, fcntl, hashlib, json, math, os, sqlite3, time, uuid, zlib
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

DEFAULT = dict(address='Stanford Dish, Stanford, CA', latitude=37.4083, longitude=-122.179,
               radius_nm=15 / 1.150779448, enabled=True)
PROVIDER='adsb.fi'
PROVIDER_URL='https://adsb.fi/'
MAX_AGE=30
POLL=15

def read(path, default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError, ValueError):return default

def atomic(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('w') as f: os.chmod(temp,0o600);json.dump(value,f,allow_nan=False)
        temp.replace(path)
    finally:
        with contextlib.suppress(FileNotFoundError):temp.unlink()

def base(root):return Path(root)/'air-traffic'
def settings(root):return read(base(root)/'settings.json',dict(DEFAULT))
def center_id(config):
    return hashlib.sha256(json.dumps([config['latitude'],config['longitude'],config['radius_nm']]).encode()).hexdigest()[:16]

def number(value):return isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value)
def fetch_json(url):
    request=Request(url,headers={'User-Agent':'StarPeople-FieldStation/1.0 (+https://starpeople.ai)','Accept':'application/json'})
    with urlopen(request,timeout=8) as response:
        raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError('Response too large')
        return json.loads(raw)

def save_settings(root, value):
    address=value.get('address')
    if not isinstance(address,str) or not 3<=len(address.strip())<=250 or any(ord(c)<32 for c in address):
        raise ValueError('Enter an address or landmark.')
    address=address.strip(); directory=base(root);directory.mkdir(parents=True,exist_ok=True)
    with (directory/'settings.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        config=settings(root)
        radius=value.get('radius_miles',config['radius_nm']*1.150779448)
        if not number(radius) or not 1<=radius<=100:raise ValueError('Radar radius must be between 1 and 100 miles.')
        config['radius_nm']=radius/1.150779448
        if address==config['address']:
            config['updated_epoch']=time.time();atomic(directory/'settings.json',config)
            return config
        if address.casefold() in ('stanford dish','the stanford dish',DEFAULT['address'].casefold()):
            lat,lon=DEFAULT['latitude'],DEFAULT['longitude'];resolved=DEFAULT['address']
        else:
            # Submit-only geocoding: no autocomplete or keystroke requests.
            gate=directory/'geocode-last.json';last=read(gate,{})
            if time.time()-last.get('epoch',0)<2:raise ValueError('Please wait a moment before resolving another address.')
            atomic(gate,{'epoch':time.time()})
            results=fetch_json('https://nominatim.openstreetmap.org/search?'+urlencode(dict(q=address,format='jsonv2',limit=1)))
            if not isinstance(results,list) or not results:raise ValueError('Address not found. Include the city and state.')
            lat,lon=float(results[0]['lat']),float(results[0]['lon']);resolved=str(results[0]['display_name'])[:500]
            if not -90<=lat<=90 or not -180<=lon<=180:raise ValueError('Invalid location result.')
        config.update(address=address,latitude=lat,longitude=lon,resolved_address=resolved,updated_epoch=time.time())
        atomic(directory/'settings.json',config)
        return config

def normalize(payload, config, now):
    timestamp=payload.get('now')
    if not number(timestamp):raise ValueError('Missing feed timestamp')
    timestamp=timestamp/1000 if timestamp>1e11 else timestamp
    if not -5<=now-timestamp<=MAX_AGE:raise ValueError('Stale aircraft feed')
    if not isinstance(payload.get('ac'),list):raise ValueError('Invalid aircraft feed')
    aircraft=[]
    for raw in payload['ac'][:5000]:
        lat,lon,seen=raw.get('lat'),raw.get('lon'),raw.get('seen_pos')
        if not all(number(v) for v in (lat,lon,seen)) or not -90<=lat<=90 or not -180<=lon<=180 or not 0<=seen<=MAX_AGE:continue
        if raw.get('alt_baro')=='ground':continue
        p1,p2=math.radians(config['latitude']),math.radians(lat)
        dp=p2-p1;dl=math.radians(lon-config['longitude'])
        distance_nm=3440.065*2*math.asin(min(1,math.sqrt(math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2)))
        if distance_nm>config['radius_nm']:continue
        position_epoch=timestamp-seen
        if now-position_epoch>MAX_AGE:continue
        row={k:str(raw[k]).strip()[:40] for k in ('hex','flight','r','t') if raw.get(k) is not None}
        if not row.get('hex'):continue
        row.update(latitude=lat,longitude=lon,position_epoch=position_epoch)
        for source,dest in [('alt_baro','altitude_ft'),('gs','speed_knots'),('track','track_deg')]:
            if number(raw.get(source)):row[dest]=raw[source]
        if 'track_deg' in row:row['track_deg']%=360
        aircraft.append(row)
    return dict(schema=1,status='available',provider=PROVIDER,provider_url=PROVIDER_URL,
                received_epoch=now,sampled_epoch=timestamp,center_id=center_id(config),
                center=dict(address=config['address'],latitude=config['latitude'],longitude=config['longitude']),
                radius_nm=config['radius_nm'],aircraft=aircraft)

def database(root, writable=False, namespace=""):
    path=base(root)/(namespace+'history.sqlite')
    if writable:
        db=sqlite3.connect(path,timeout=.1)
        db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA busy_timeout=100')
        db.execute('CREATE TABLE IF NOT EXISTS snapshots(epoch REAL PRIMARY KEY,center_id TEXT NOT NULL,body BLOB NOT NULL)')
    else:db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.1)
    return db

def store(root, snapshot, namespace=""):
    data=zlib.compress(json.dumps(snapshot,separators=(',',':')).encode())
    with contextlib.closing(database(root,True,namespace)) as db,db:
        db.execute('INSERT OR REPLACE INTO snapshots VALUES(?,?,?)',(snapshot['sampled_epoch'],snapshot['center_id'],data))
        db.execute('DELETE FROM snapshots WHERE epoch<?',(time.time()-72*3600,))
        # Compressed history payload capped at 64 MiB; SQLite reuses its freed pages.
        size=db.execute('SELECT COALESCE(SUM(length(body)),0) FROM snapshots').fetchone()[0]
        if size>64*1024**2:
            for epoch,length in db.execute('SELECT epoch,length(body) FROM snapshots ORDER BY epoch').fetchall():
                db.execute('DELETE FROM snapshots WHERE epoch=?',(epoch,));size-=length
                if size<=60*1024**2:break
    atomic(base(root)/(namespace+'latest.json'),snapshot)

def live(root, now=None):
    now=time.time() if now is None else now
    result=read(base(root)/'latest.json',{'status':'unavailable','aircraft':[]})
    config=settings(root)
    if result.get('center_id')!=center_id(config):return dict(status='waiting',aircraft=[],center=dict(address=config['address'],latitude=config['latitude'],longitude=config['longitude']),radius_nm=config['radius_nm'])
    result['age_seconds']=round(max(0,now-result.get('sampled_epoch',0)),1)
    if result['age_seconds']>MAX_AGE:result.update(status='stale',aircraft=[])
    else:result['aircraft']=[a for a in result.get('aircraft',[]) if 0<=now-a['position_epoch']<=MAX_AGE]
    return result

def at_time(root, epoch, namespace="", max_age=MAX_AGE):
    if not number(epoch) or epoch<=0:return dict(status='unavailable',reason='Capture time unavailable',aircraft=[])
    try:
        with contextlib.closing(database(root,namespace=namespace)) as db:
            # Only measurements taken at or before capture, never present-day data for an old detection.
            row=db.execute('SELECT body FROM snapshots WHERE epoch<=? AND epoch>=? ORDER BY epoch DESC LIMIT 1',(epoch,epoch-max_age)).fetchone()
        if row:
            result=json.loads(zlib.decompress(row[0]));result['detection_epoch']=epoch
            result['aircraft']=[a for a in result['aircraft'] if 0<=epoch-a['position_epoch']<=max_age]
            result['sample_offset_seconds']=round(epoch-result['sampled_epoch'],1)
            return result
    except (OSError,ValueError,sqlite3.Error,zlib.error):pass
    return dict(status='unavailable',reason='No air-traffic sample was recorded at this detection time',detection_epoch=epoch,aircraft=[])

def attach(root, folder, event):
    """Bounded local read only; failures cannot interrupt capture or human labels."""
    path=Path(folder)/'air-traffic.private.json'
    try:
        pose_path = Path(folder) / 'camera-pointing.json'
        if not pose_path.exists():
            config = settings(root)
            updated, detected = config.get('updated_epoch'), event.get('detected_epoch')
            az, elevation = config.get('camera_azimuth_deg'), config.get('camera_elevation_deg')
            if (number(updated) and number(detected) and 0 < updated <= detected <= time.time()
                    and number(az) and 0 <= az < 360 and number(elevation) and -90 <= elevation <= 90):
                atomic(pose_path, dict(updated_epoch=updated, camera_azimuth_deg=az, camera_elevation_deg=elevation))
        if not path.exists():atomic(path,at_time(root,event.get('detected_epoch')))
        from air_traffic_archive import attach_public
        attach_public(root,folder,event)
    except (OSError,ValueError,sqlite3.Error):pass

def detection(root, folder, event):
    return read(Path(folder)/'air-traffic.private.json') or at_time(root,event.get('detected_epoch'))

def collect_once(root):
    config=settings(root)
    url=f"https://opendata.adsb.fi/api/v3/lat/{config['latitude']}/lon/{config['longitude']}/dist/{math.ceil(config['radius_nm'])}"
    snapshot=normalize(fetch_json(url),config,time.time());store(root,snapshot)
    return snapshot

def run(root):
    root=Path(root).resolve()
    if not str(root).startswith('/Volumes/') or not Path('/Volumes',root.parts[2]).is_mount():raise SystemExit('External field storage unavailable')
    base(root).mkdir(parents=True,exist_ok=True)
    with (base(root)/'collector.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        failures=0;private_next=0
        while True:
            if time.time()>=private_next:
                delay=POLL
                try:
                    snap=collect_once(root);failures=0
                    atomic(base(root)/'collector-status.json',dict(status='collecting',epoch=time.time(),aircraft=len(snap['aircraft'])))
                except Exception as error:
                    failures+=1;delay=min(900,15*2**min(failures,6))
                    if isinstance(error,HTTPError):
                        if error.code in (400,401,403,404):delay=3600
                        if error.code==429:
                            with contextlib.suppress(ValueError):delay=max(delay,float(error.headers.get('Retry-After','60')))
                    atomic(base(root)/'collector-status.json',dict(status='retrying',epoch=time.time(),error=type(error).__name__,next_attempt=time.time()+delay))
                private_next=time.time()+delay
            try:
                from air_traffic_archive import collect_due
                collect_due(root)
            except Exception:
                pass  # A public provider failure cannot interrupt the private radar.
            time.sleep(POLL)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args();run(args.root)
