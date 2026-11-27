"""Conservative deletion guards. Unreadable protection metadata aborts cleanup."""
import fcntl,json
from contextlib import contextmanager
from pathlib import Path


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def reviewed_events(data):
    reviews=Path(data)/'email-reviews'
    manifest=reviews/'training-manifest.json'
    examples=reviews/'examples'
    # Never use the retention reader here: it treats I/O errors as empty data.
    try:
        current=manifest.stat().st_mtime_ns
    except FileNotFoundError:
        current=None
    try:
        changed=examples.stat().st_mtime_ns
    except FileNotFoundError:
        changed=None
    if current is not None and (changed is None or changed<=current):
        rows=read(manifest)['examples']
    else:
        rows=[]
        if changed is not None:
            for folder in examples.iterdir():
                if folder.name.startswith('.') or not folder.is_dir():continue
                record=read(folder/'review.json')
                if record is None:raise ValueError('Missing review protection metadata')
                rows.append(record)
    return {r.get('event_id') for r in rows if r.get('human_confirmed') and not r.get('deleted')}


def review_stamp(data):
    values=[]
    for name in ("training-manifest.json","examples"):
        try:values.append((Path(data)/"email-reviews"/name).stat().st_mtime_ns)
        except FileNotFoundError:values.append(None)
    return tuple(values)


@contextmanager
def bookmark_lease(data):
    with (Path(data)/'starred-objects.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        yield


def protected(data,row):
    data=Path(data);key=row['id'];kind=row['kind']
    if kind not in ('detection','video'):raise ValueError('Invalid cleanup kind')
    stars=read(data/'starred-objects.json',{}).get('objects',{})
    for identity in stars:
        parts=identity.split(':')
        if len(parts)!=3:raise ValueError('Invalid bookmark protection metadata')
        if parts[1]==key:return True
    folder=(data.parent/'notifications/outbox' if kind=='detection' else data/'videos')/key
    if folder.is_symlink():raise ValueError('Unsafe cleanup target')
    meta=read(folder/('event.json' if kind=='detection' else 'video.json'))
    if not isinstance(meta,dict) or not meta:raise ValueError('Missing source protection metadata')
    if meta.get('kind')=='manual_recording' or meta.get('manual_session_id') or meta.get('manual_recording'):return True
    # Session-linked imported videos may represent retained manual/archive data.
    if kind=='video' and meta.get('provenance',{}).get('session_id'):return True
    names={p.name for p in folder.iterdir()}
    if names & {'archive-decision.json','manual-archive-approval.json','manual-internet-archive.json','internet-archive.json'}:return True
    if read(folder/'annotations.json',[]):return True
    review=read(folder/'review.json',{})
    if review.get('completed') or review.get('reviewed_at'):return True
    if read(folder/'review-completion.json',{}).get('completed'):return True
    if kind=='detection':
        direct=read(data/'email-reviews/examples'/key/'review.json',{})
        if direct.get('human_confirmed') and not direct.get('deleted'):return True
    return False
