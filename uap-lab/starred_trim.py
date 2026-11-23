"""Reversible trims of standalone starred evidence. Original media stays immutable."""
import fcntl
import hashlib
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


def binding(data, key, asset=NATIVE):
    if not re.fullmatch('[a-f0-9]{32}', key or ''):
        raise ValueError('Invalid detection')
    receipt = read(root(data) / ('review-' + key + '.json'), {})
    if receipt.get('identifier') != 'starpeople-field-starred-review-' + key:
        return None
    if asset == NATIVE:
        from review_playback import native_path
        path = native_path(data, key)
    else:
        extras = read(root(data) / 'context.json', {}).get(key, {})
        if asset not in extras or not re.fullmatch('[a-z0-9-]+\.mp4', asset):
            raise ValueError('Unknown recording')
        path = Path(extras[asset])
    if path.is_symlink() or not path.is_file():
        raise ValueError('The original recording is unavailable on the field drive')
    return path


def request_path(data, key, asset):
    return root(data) / 'trims' / key / asset / 'request.json'


def status(data, key, asset=NATIVE):
    request = read(request_path(data, key, asset), {})
    receipt = read(root(data) / ('review-' + key + '.json'), {})
    public = bool(receipt.get('verified'))
    return dict(available=True, request=request, applied=bool(request),
                bundle_updating=not public or receipt.get('trim_revisions', {}).get(asset) != request.get('revision'),
                bundle_url='https://archive.org/compress/' + receipt['identifier'] if public else None)


def output(data, key, asset=NATIVE):
    path = request_path(data, key, asset)
    request = read(path, {})
    if request.get('enabled'):
        return path.parent / (request['revision'] + '.mp4')
    return binding(data, key, asset)


def save(data, key, asset, body):
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
            if end-start < .017:
                raise ValueError('Select at least one full frame.')
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
        if re.fullmatch('[a-z0-9-]+\.mp4', name) and binding(data,key,name):
            return '/trim-recording?' + urlencode(dict(id=key,asset=name))
    return None
