"""Shared review-card pins and stable pin-aware pagination."""
import base64
import fcntl
import json
import time
from pathlib import Path

from retired_data import read, save


def pin_key(key):
    if ':' not in key:
        return f'review:{key}:{key}'
    return key


def update(data, body):
    from detection_actions import object_folder
    from manual_recordings import SID
    data = Path(data)
    key, enabled = body.get('id'), body.get('pinned')
    if not isinstance(key, str) or type(enabled) is not bool:
        raise ValueError('Choose a recording and pin state')
    if key.startswith('manual:'):
        sid = key[7:]
        if not SID.fullmatch(sid) or not any(r.get('session_id') == sid for r in read(data/'live/manual-sessions.json', [])):
            raise ValueError('Unknown manual recording')
    else:
        object_folder(data, key)
    path = data/'review-pins.json'
    with path.with_suffix('.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        pins = read(path, {})
        if enabled:
            pins.setdefault(pin_key(key), time.time())
        else:
            pins.pop(pin_key(key), None)
        save(path, pins)
    return dict(id=key, pinned_at=pins.get(pin_key(key), 0))


def order(data, rows, before):
    """Input rows already have descending capture-time and ID order."""
    pins = read(Path(data)/'review-pins.json', {})
    if pins:
        top, rest = [], []
        for row in rows:
            stamp = pins.get(pin_key(row['id']))
            if stamp:
                top.append(dict(row, pinned_at=stamp))
            else:
                rest.append(row)
        rows = sorted(top, key=lambda row: row['pinned_at'], reverse=True) + rest
    if not before:
        return rows
    try:
        boundary = json.loads(base64.urlsafe_b64decode(before))
        if len(boundary) == 2:
            boundary.insert(0, 0)
        stamp, created, key = boundary
        if not isinstance(stamp,(int,float)) or not isinstance(created,(int,float)) or not isinstance(key,str):
            raise ValueError()
    except (TypeError, ValueError, AttributeError):
        raise ValueError('Invalid object cursor') from None
    return [r for r in rows if (r.get('pinned_at',0),r['created'],r['id']) < (stamp,created,key)]


def cursor(row):
    return base64.urlsafe_b64encode(json.dumps([row.get('pinned_at',0),row['created'],row['id']]).encode()).decode()
