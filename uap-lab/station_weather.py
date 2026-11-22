"""Weather at the private radar center. Archive only weather and timestamps."""
import contextlib
import json
import sqlite3
import time
from pathlib import Path
from datetime import datetime

import air_traffic as traffic

FIELDS = ('temperature_2m', 'relative_humidity_2m', 'pressure_hpa')
UNITS = dict(zip(FIELDS, ('°F', '%', 'hPa')))
INTERVAL = 600
MAX_AGE = 7200


def site(config):
    return [config['latitude'], config['longitude']]


def collect_due(root):
    config = traffic.settings(root)
    directory = traffic.base(root)
    status = directory / 'weather-attempt.json'
    now = time.time()
    previous = traffic.read(status, {})
    if previous.get('site') == site(config) and previous.get('next', 0) > now:
        return
    traffic.atomic(status, {'site': site(config), 'next': now + 120})
    stations = previous.get('stations') if previous.get('site') == site(config) else None
    if not stations:
        point = traffic.fetch_json(f"https://api.weather.gov/points/{config['latitude']:.4f},{config['longitude']:.4f}")
        listing = traffic.fetch_json(point['properties']['observationStations'])
        stations = [item['properties']['stationIdentifier'] for item in listing['features'][:5]]
    sample = None
    for station in stations:
        try:
            obs = traffic.fetch_json(f'https://api.weather.gov/stations/{station}/observations/latest')['properties']
            stamp = datetime.fromisoformat(obs['timestamp'].replace('Z','+00:00')).timestamp()
            if not 0 <= now-stamp <= MAX_AGE:
                continue
            values = {}
            for key, source, unit, factor, offset in (
                ('temperature_2m','temperature','degC',1.8,32),
                ('relative_humidity_2m','relativeHumidity','percent',1,0),
                ('pressure_hpa','barometricPressure','Pa',0.01,0)):
                measure = obs.get(source) or {}
                if traffic.number(measure.get('value')) and measure.get('unitCode','').split(':')[-1] == unit:
                    values[key] = round(measure['value']*factor+offset,2)
            if values and (sample is None or len(values)>len(sample['values'])):
                sample = dict(observed_epoch=stamp, station=station, conditions=obs.get('textDescription',''),values=values)
            if len(values)==3:
                break
        except (OSError,ValueError,KeyError):
            continue
    if not sample:
        return
    sample.update(sample.pop('values'))
    sample['collected_epoch']=int(now)
    with contextlib.closing(sqlite3.connect(directory / 'weather.sqlite')) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS weather(collected INTEGER PRIMARY KEY, body TEXT NOT NULL)')
        db.execute('INSERT OR REPLACE INTO weather VALUES(?,?)', (int(now), json.dumps(sample)))
    traffic.atomic(directory / 'weather-latest.json', dict(site=site(config), sample=sample))
    traffic.atomic(status, {'site': site(config), 'next': now + INTERVAL, 'stations': stations})


def live(root, config, now):
    latest = traffic.read(traffic.base(root) / 'weather-latest.json', {})
    sample = latest.get('sample', {})
    if latest.get('site') == site(config) and 0 <= now - sample.get('observed_epoch', 0) <= MAX_AGE:
        return sample
    return {}


def bundle(root, folder, manifest):
    from air_traffic_archive import epoch
    start = epoch(manifest.get('started_epoch')) or epoch(manifest.get('started_at'))
    end = next((value for key in ('ended_epoch','stopped_epoch','ended_at','completed_at')
                if (value := epoch(manifest.get(key))) is not None), start)
    target = Path(folder) / 'weather.json'
    old = traffic.read(target, {})
    samples = {s['collected_epoch']: s for s in old.get('samples', [])}
    path = traffic.base(root) / 'weather.sqlite'
    if start and end >= start and path.exists():
        with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
            rows = db.execute('SELECT body FROM weather WHERE collected BETWEEN ? AND ? ORDER BY collected',
                              (start - MAX_AGE, end))
            prior = None
            for (body,) in rows:
                sample = json.loads(body)
                if sample['collected_epoch'] < start:
                    if start - sample['observed_epoch'] <= MAX_AGE:
                        prior = sample
                else:
                    samples[sample['collected_epoch']] = sample
            if prior:
                samples[prior['collected_epoch']] = prior
    value = dict(schema=1, source='National Weather Service', source_url='https://www.weather.gov/',
                 kind='nearby station observation', units=UNITS,
                 start_epoch=start, end_epoch=end, status='available' if samples else 'unavailable',
                 samples=[samples[k] for k in sorted(samples)])
    if value != old:
        traffic.atomic(target, value)
    return target
