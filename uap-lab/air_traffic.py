"""Private ADS-B context. No automatic visual identification or public redistribution."""
import argparse, contextlib, fcntl, hashlib, json, math, os, sqlite3, time, uuid, zlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
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

def resolve_address(root,address):
    directory=base(root)
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
    return lat,lon,resolved

def save_settings(root, value):
    if value.get('action') in ('add_landmark','remove_landmark'):return update_landmark(root,value)
    address=value.get('address')
    if not isinstance(address,str) or not 3<=len(address.strip())<=250 or any(ord(c)<32 for c in address):
        raise ValueError('Enter an address or landmark.')
    address=address.strip(); directory=base(root);directory.mkdir(parents=True,exist_ok=True)
    with (directory/'settings.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        config=settings(root)
        radius=value.get('radius_miles',config['radius_nm']*1.150779448)
        if not number(radius) or not 1<=radius<=100:raise ValueError('Radar radius must be between 1 and 100 miles.')
        azimuth=value.get('camera_azimuth_deg',config.get('camera_azimuth_deg'))
        if azimuth is not None and (not number(azimuth) or not 0<=azimuth<360):raise ValueError('Camera azimuth must be 0–359.9° clockwise from true north, or blank.')
        elevation=value.get('camera_elevation_deg',config.get('camera_elevation_deg'))
        if elevation is not None and (not number(elevation) or not -90<=elevation<=90):raise ValueError('Camera elevation must be between −90° and 90°, or blank.')
        config['camera_elevation_deg']=elevation
        config['camera_azimuth_deg']=azimuth
        config['radius_nm']=radius/1.150779448
        if address==config['address']:
            config['updated_epoch']=time.time();atomic(directory/'settings.json',config)
            return config
        lat,lon,resolved=resolve_address(root,address)
        config.update(address=address,latitude=lat,longitude=lon,resolved_address=resolved,updated_epoch=time.time())
        atomic(directory/'settings.json',config)
        return config

def update_landmark(root,value):
    directory=base(root);directory.mkdir(parents=True,exist_ok=True)
    with (directory/'settings.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        config=settings(root);items=list(config.get('landmarks',[]))
        if value['action']=='remove_landmark':
            items=[r for r in items if r['id']!=value.get('id')]
        else:
            address=value.get('address');label=value.get('label','')
            if not isinstance(address,str) or not 3<=len(address.strip())<=250 or any(ord(c)<32 for c in address):raise ValueError('Enter a landmark address.')
            if not isinstance(label,str) or len(label)>60 or any(ord(c)<32 for c in label):raise ValueError('Use a landmark name of up to 60 characters.')
            address=address.strip();label=label.strip() or address.split(',')[0][:60]
            if any(r['address'].casefold()==address.casefold() for r in items):raise ValueError('This landmark is already saved.')
            if len(items)>=20:raise ValueError('You can save up to 20 landmarks.')
            lat,lon,resolved=resolve_address(root,address)
            items.append(dict(id=uuid.uuid4().hex,label=label,address=address,resolved_address=resolved,latitude=lat,longitude=lon))
        config['landmarks']=items;config['updated_epoch']=time.time()
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
    if result.get('center_id')!=center_id(config):return dict(status='waiting',aircraft=[],center=dict(address=config['address'],resolved_address=config.get('resolved_address',config['address']),latitude=config['latitude'],longitude=config['longitude']),radius_nm=config['radius_nm'],landmarks=config.get('landmarks',[]),camera_azimuth_deg=config.get('camera_azimuth_deg'),camera_elevation_deg=config.get('camera_elevation_deg'))
    result['center']=dict(address=config['address'],resolved_address=config.get('resolved_address',config['address']),latitude=config['latitude'],longitude=config['longitude'])
    result['landmarks']=config.get('landmarks',[])
    result['camera_azimuth_deg']=config.get('camera_azimuth_deg')
    result['camera_elevation_deg']=config.get('camera_elevation_deg')
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

def region_key(config):
    return hashlib.sha256(json.dumps([config['latitude'],config['longitude']]).encode()).hexdigest()[:16]

def public_region(root):
    value=read(base(root)/'radar-region.json',{})
    if value.get('center_key')!=region_key(settings(root)) or value.get('status')!='known':return dict(status='unknown')
    return {k:value[k] for k in ('status','county','state','country')}

def refresh_region(root):
    config=settings(root);key=region_key(config);path=base(root)/'radar-region.json';old=read(path,{})
    if old.get('center_key')==key and (old.get('status')=='known' or time.time()<old.get('retry_after',0)):return
    directory=base(root)
    with (directory/'settings.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        gate=directory/'geocode-last.json'
        if time.time()-read(gate,{}).get('epoch',0)<2:return
        atomic(gate,dict(epoch=time.time()))
        value=dict(status='unknown',center_key=key,retry_after=time.time()+3600)
        try:
            response=fetch_json('https://nominatim.openstreetmap.org/reverse?'+urlencode(dict(lat=config['latitude'],lon=config['longitude'],format='jsonv2',zoom=10,addressdetails=1)))
            address=response.get('address',{});county=address.get('county');country=str(address.get('country_code','')).upper()
            state=address.get('ISO3166-2-lvl4','').removeprefix(country+'-') or address.get('state')
            if all(isinstance(v,str) and 0<len(v)<=120 and not any(ord(c)<32 for c in v) for v in (county,state,country)):
                value.update(status='known',county=county,state=state,country=country)
        except (OSError,ValueError,TypeError):pass
        atomic(path,value)

def collect_auxiliary(root):
    # Public-provider and geocoding latency must not delay private radar reports.
    try:
        from air_traffic_archive import collect_due
        collect_due(root)
        refresh_region(root)
    except Exception:
        pass

def poll(root):
    failures=0;private_next=0;auxiliary=None
    with ThreadPoolExecutor(max_workers=1,thread_name_prefix='air-context') as pool:
        while True:
            started=time.monotonic()
            if started>=private_next:
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
                    started=time.monotonic()  # Honor backoff after a failed request.
                private_next=started+delay
            if auxiliary is None or auxiliary.done():auxiliary=pool.submit(collect_auxiliary,root)
            time.sleep(max(.1,min(POLL,private_next-time.monotonic())))

def run(root):
    root=Path(root).resolve()
    if not str(root).startswith('/Volumes/') or not Path('/Volumes',root.parts[2]).is_mount():raise SystemExit('External field storage unavailable')
    base(root).mkdir(parents=True,exist_ok=True)
    with (base(root)/'collector.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        poll(root)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args();run(args.root)
