"""Reversible trims of standalone starred evidence. Original media stays immutable."""
import fcntl
import json
import math
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from label_queue import read

NATIVE = 'review.mp4'


def root(data):
    return Path(data).parent / 'archive-tags/starred-bundles'


def continuous_session(data, key):
    import lab
    from email_review import folder_for
    from sustained_motion import playback_url
    from urllib.parse import parse_qs, urlsplit
    event=read(folder_for(data,key)/'event.json',{})
    url=playback_url(data,lab.STATION,event)
    if not url:
        return None
    sid=parse_qs(urlsplit(url).query).get('session',[''])[0]
    if not re.fullmatch(r'[0-9TZ]+-[a-f0-9]{6}',sid):
        return None
    folder=Path(data).parent/'sessions'/sid
    return folder if not folder.is_symlink() and (folder/'manifest.json').is_file() else None


def binding(data, key, asset=NATIVE):
    if not re.fullmatch('[a-f0-9]{32}', key or ''):
        raise ValueError('Invalid detection')
    if not re.fullmatch(r'[a-z0-9-]+\.mp4', asset or ''):
        raise ValueError('Unknown recording')
    pinned=request_path(data,key,asset).parent/'original.mp4'
    if pinned.is_file() and not pinned.is_symlink():
        return pinned
    receipt = read(root(data) / ('review-' + key + '.json'), {})
    if asset == NATIVE and receipt.get('identifier') != 'starpeople-field-starred-review-' + key:
        from video_trim import session_for
        try:
            session=session_for(data,key)
        except ValueError:
            pass
        else:
            decision=read(session/'archive-decision.json',{})
            if decision.get('confirmed_anomalous') or (session/'review-trim.json').is_file():
                return None
    if asset == 'session-full.mp4':
        folder=continuous_session(data,key)
        if folder is None:raise ValueError('Continuous recording unavailable')
        return folder/'video.mp4'
    if asset != NATIVE and not receipt and asset not in read(root(data) / 'context.json', {}).get(key, {}):
        return None
    if asset == NATIVE:
        from review_playback import native_path
        path = native_path(data, key)
    else:
        extras = read(root(data) / 'context.json', {}).get(key, {})
        if asset not in extras or not re.fullmatch(r'[a-z0-9-]+\.mp4', asset):
            raise ValueError('Unknown recording')
        path = Path(extras[asset])
    if path.is_symlink() or not path.is_file():
        return None
    return path


def approved_session(data,key,asset):
    if asset!='session-full.mp4':
        return None
    folder=continuous_session(data,key)
    if folder and read(folder/'archive-decision.json',{}).get('confirmed_anomalous'):
        return folder
    return None


def request_path(data, key, asset):
    return root(data) / 'trims' / key / asset / 'request.json'


def status(data, key, asset=NATIVE):
    session=approved_session(data,key,asset)
    if session:
        from video_trim import status as session_status
        return session_status(data,key,folder=session,scope='continuous')
    request = read(request_path(data, key, asset), {})
    receipt = read(root(data) / ('review-' + key + '.json'), {})
    public = bool(receipt.get('verified'))
    return dict(available=True, request=request, applied=bool(request),
                bundle_updating=bool(receipt) and (not public or receipt.get('trim_revisions', {}).get(asset) != request.get('revision')),
                publication_expected=bool(receipt),
                bundle_url='https://archive.org/compress/' + receipt['identifier'] if public else None)


def output(data, key, asset=NATIVE):
    session=approved_session(data,key,asset)
    if session:
        from video_trim import download
        return download(data,key,folder=session,scope='continuous')
    path = request_path(data, key, asset)
    request = read(path, {})
    if request.get('enabled'):
        return path.parent / (request['revision'] + '.mp4')
    return binding(data, key, asset)


def save(data, key, asset, body):
    session=approved_session(data,key,asset)
    if session:
        from video_trim import save as session_save
        return session_save(data,body,folder=session,scope='continuous')
    source = binding(data, key, asset)
    if not source:
        raise ValueError('No starred recording for this detection')
    path = request_path(data, key, asset)
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        revision = uuid.uuid4().hex
        request = dict(enabled=body.get('reset') is not True, event_id=key, revision=revision)
        if request['enabled']:
            probe = shutil.which('ffprobe') or '/opt/homebrew/bin/ffprobe'
            duration = float(subprocess.check_output([probe, '-v','error','-show_entries','format=duration',
                '-of','default=nw=1:nk=1', str(source)], timeout=30))
            start,end = float(body['start']),float(body['end'])
            if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration+.001):
                raise ValueError('Choose a start and end within this recording.')
            if end-start < .001:
                raise ValueError('Select at least one frame.')
            from evidence_copy import copy_evidence
            pinned=path.parent/'original.mp4'
            if not pinned.exists():
                staging=path.parent/(revision+'.original.tmp')
                try:
                    copy_evidence(source,staging)
                    os.replace(staging,pinned)
                finally:
                    staging.unlink(missing_ok=True)
            source=pinned
            target=path.parent/(revision+'.mp4')
            try:
                subprocess.run([shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg','-nostdin','-v','error',
                    '-ss',str(start),'-i',str(source),'-t',str(min(duration,end)-start),'-map','0:v:0',
                    '-an','-c:v','libx264','-threads','2','-preset','veryfast','-crf','16',
                    '-movflags','+faststart',str(target)],check=True,timeout=600)
            except Exception:
                target.unlink(missing_ok=True)
                raise
            request.update(start=start,end=end)
        tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(request))
        os.replace(tmp,path)
    return dict(saved=True,**status(data,key,asset))


def context_editor(data, key):
    from urllib.parse import urlencode
    extras = read(root(data) / 'context.json', {}).get(key, {})
    for name in extras:
        if re.fullmatch(r'[a-z0-9-]+\.mp4', name) and binding(data,key,name):
            return '/review-detection?' + urlencode(dict(id=key,asset=name))
    if continuous_session(data,key):
        return '/review-detection?' + urlencode(dict(id=key,asset='session-full.mp4'))
    return None
