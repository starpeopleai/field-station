"""Resolve capture times independently of review and queue insertion times."""
import math
import sqlite3
from contextlib import closing
from pathlib import Path

def bounds(start,end):
    def parse(value):
        if value in (None,''):
            return None
        stamp=float(value)
        if not math.isfinite(stamp):
            raise ValueError('Invalid capture time')
        return stamp
    start,end=parse(start),parse(end)
    if start is not None and end is not None and end<start:
        raise ValueError('End must follow start')
    return start,end

def includes(stamp,start,end):
    return isinstance(stamp,(int,float)) and (start is None or stamp>=start) and (end is None or stamp<end+1)

def filter_objects(data,rows,records,start,end):
    times={}
    path=Path(data)/'observation-metrics/capture-times-v3.sqlite3'
    if path.is_file():
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            times={key:(epoch,pts) for key,epoch,pts in db.execute('SELECT id,captured,pts FROM events WHERE captured IS NOT NULL')}
    reviews={(r.get('event_id'),r.get('sample_id') or r.get('event_id')):r for r in records}
    result=[]
    for row in rows:
        event=row.get('video_id') or row['id']
        epoch,pts=times.get(event,(None,None))
        sample=row.get('sample_id') or event
        r=reviews.get((event,sample),{})
        stamp=row.get('detected_epoch') or epoch
        if stamp is not None and pts is not None and isinstance(r.get('pts_seconds'),(int,float)):
            stamp+=r['pts_seconds']-pts
        elif stamp is None:
            stamp=r.get('captured_epoch') or (r.get('pre_review_models') or {}).get('captured_epoch') or row.get('captured_epoch')
        if includes(stamp,start,end):
            result.append(dict(row,captured_epoch=stamp))
    return result

def matching_clips(data,start,end):
    """Return recorded excerpts with a documented capture interval."""
    import json
    from urllib.parse import quote
    clips=[]
    for index in (Path(data)/'runs').glob('recording-*/capture-clips.json'):
        try:
            records=json.loads(index.read_text())
        except (OSError,ValueError):
            continue
        for clip in records:
            name=clip['file']
            if Path(name).name!=name or not name.endswith('.mp4') or not (index.parent/name).is_file():
                continue
            if (start is None or clip['end']>start) and (end is None or clip['start']<end+1):
                clips.append(dict(title=clip['title'],url='/results/'+quote(index.parent.name)+'/'+quote(name)))
    return clips
