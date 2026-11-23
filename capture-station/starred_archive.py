"""Reconcile operator stars to public evidence, independently of training labels."""
import argparse
import base64
import hashlib
import json
import mimetypes
import re
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'uap-lab'))
from review_playback import native_path

ID = re.compile(r'[a-f0-9]{32}')
PUBLIC_EVENT = ('id', 'generation', 'sequence', 'pts_seconds', 'detected_epoch',
                'created_epoch', 'bounds', 'detection_bounds', 'model', 'classification')


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, sort_keys=True))
    tmp.replace(path)


def checksums(files):
    result = {}
    for name, path in files.items():
        h = hashlib.md5()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1 << 20), b''):
                h.update(block)
        result[name] = h.hexdigest()
    return result


def existing_item(data, event, samples, groups):
    for sid, rows in groups.items():
        if not re.fullmatch(r'[0-9TZ]+-[a-f0-9]{6}', sid):
            continue
        annotations = [a for row in rows if row.get('id') == event for a in row.get('annotations', [])]
        if not set(samples) <= {a.get('sample_id') or a.get('id') or event for a in annotations}:
            continue
        receipt = read(data.parent / 'sessions' / sid / 'manifest.json', {}).get('internet_archive', {})
        if receipt.get('verified_at') and receipt.get('state') in ('cleaned', 'retaining'):
            identifier = receipt.get('identifier', '')
            if re.fullmatch(r'[A-Za-z0-9_-]+', identifier):
                return identifier
    return None


def evidence(data, kind, event, samples, extra):
    files = {}
    notes = []
    if kind == 'review':
        folder = data.parent / 'notifications/outbox' / event
        record = read(folder / 'event.json', {})
        for sample in sorted(samples):
            example = data / 'email-reviews/examples' / sample
            annotation = read(example / 'review.json', {})
            if annotation and annotation.get('event_id') != event:
                raise ValueError('Review belongs to another event')
            crop = example / 'native-object.png'
            if not crop.is_file() and sample == event:
                crop = folder / 'native-object.png'
            if crop.is_file():
                files['frames/' + sample + '.png'] = crop
            notes.append(dict(id=sample, **{k: annotation[k] for k in ('label', 'bounds', 'pts_seconds', 'review_clip_time') if k in annotation}))
        for name in ('source-frame.png', 'color-frame.jpg', 'air-traffic-public.json'):
            if (folder / name).is_file():
                files[name] = folder / name
        clip = native_path(data, event)
        if not clip.is_file() and record and not (folder / 'local-media-retired.json').exists():
            from email_review import prepare
            try:
                prepare(data, event)
            except (OSError, ValueError, RuntimeError):
                pass  # Available frames can be published while the video is recovered.
        if clip.is_file():
            files['review.mp4'] = clip
    else:
        from detection_actions import object_folder
        _, _, folder = object_folder(data, ':'.join((kind, event, next(iter(samples)))))
        record = {'id': event}
        notes = [{k: a[k] for k in ('id', 'label', 'bounds', 'time', 'frame_index') if k in a}
                 for a in read(folder / 'annotations.json', []) if a.get('id') in samples]
        if (folder / 'source').is_file():
            files['original-video'] = folder / 'source'
    for name, path in extra.items():
        if not re.fullmatch(r'[a-z0-9-]+\.mp4', name) or not Path(path).is_file():
            raise ValueError('Missing configured context clip')
        files[name] = Path(path)
    if not files or all(p.suffix == '.json' for p in files.values()):
        raise ValueError('Awaiting recoverable image or video')
    return files, {'event': {k: record[k] for k in PUBLIC_EVENT if k in record}, 'starred_objects': notes}


def publish(api, identifier, files, checks, existing, acknowledged, checkpoint):
    def remote():
        return {f['name']: f.get('md5') for f in api.metadata(identifier).get('files', [])}
    indexed = remote()
    for name, path in files.items():
        if indexed.get(name) == checks[name] or (acknowledged.get(name, {}).get("md5") == checks[name] and time.time() - acknowledged[name]["at"] < 3600):
            continue
        headers = {'Content-MD5': base64.b64encode(bytes.fromhex(checks[name])).decode(),
                   'Content-Type': mimetypes.guess_type(name)[0] or 'application/octet-stream',
                   'x-archive-queue-derive': '0', 'x-archive-keep-old-version': '1'}
        if not existing:
            headers.update({'x-archive-auto-make-bucket': '1', 'x-archive-meta-collection': 'opensource_movies',
                            'x-archive-meta-mediatype': 'movies', 'x-archive-meta-subject': 'StarPeople.ai;Field Station;starred',
                            'x-archive-meta-title': 'Field Station starred detection ' + identifier.rsplit('-', 1)[-1]})
        with path.open('rb') as stream, api.raw('PUT', api.url(identifier, name), stream, headers, auth=True):
            pass
        acknowledged[name] = dict(md5=checks[name], at=time.time())
        checkpoint()
    if any(indexed.get(k) != v for k, v in checks.items()):
        indexed = remote()
    return all(indexed.get(k) == v for k, v in checks.items())


def main():
    parser = argparse.ArgumentParser()
    for arg in ('data', 'private', 'state'):
        parser.add_argument('--' + arg, type=Path, required=True)
    args = parser.parse_args()
    data, state = args.data, args.state
    state.mkdir(exist_ok=True, parents=True)
    stars = read(data / 'starred-objects.json')['objects']
    events = defaultdict(dict)
    for key, value in stars.items():
        kind, event, sample = key.split(':')
        if kind in ('video', 'review', 'preserved') and ID.fullmatch(event) and ID.fullmatch(sample):
            events[kind, event][sample] = value
    groups = read(data / 'archive-review-groups.json', {}).get('groups', {})
    extras = read(state / 'context.json', {})
    from internet_archive import ArchiveAPI
    api = ArchiveAPI(args.private)
    for kind, event in sorted(events, key=lambda pair: pair[1] not in extras):
        samples = events[kind, event]
        receipt = state / (kind + '-' + event + '.json')
        previous = read(receipt, {})
        try:
            extra = extras.get(event, {})
            from starred_trim import request_path
            trims = {asset: read(request_path(data,event,asset), {}) for asset in ('review.mp4',*extra)}
            trims = {asset: r for asset,r in trims.items() if r.get('revision')}
            revisions = {asset:r['revision'] for asset,r in trims.items()}
            signature = hashlib.sha256(json.dumps([samples, extra, revisions] if revisions else [samples, extra], sort_keys=True).encode()).hexdigest()
            if previous.get('signature') == signature and previous.get('verified') and time.time()-previous['checked'] < 86400:
                continue
            existing = existing_item(data, event, samples, groups)
            identifier = previous.get('identifier') or existing or ('starpeople-field-starred-' + kind + '-' + event)
            with tempfile.TemporaryDirectory(dir=state) as tmp:
                files, manifest = evidence(data, kind, event, samples, extra)
                if trims:
                    manifest['video_trims'] = trims
                    for asset,request in trims.items():
                        if request.get('enabled'):
                            files[asset] = request_path(data,event,asset).parent / (request['revision']+'.mp4')
                manifest['available_files'] = sorted(files)
                sidecar = Path(tmp) / 'starred.json'
                sidecar.write_text(json.dumps(manifest, sort_keys=True))
                files['starred.json'] = sidecar
                if identifier == existing or not identifier.startswith('starpeople-field-starred-'):
                    files = {'starred/' + event + '/' + k: v for k, v in files.items()}
                checks = checksums(files)
                acknowledged = previous.get('acknowledged', {}) if previous.get('identifier') == identifier else {}
                def checkpoint():
                    save(receipt, dict(signature=signature, identifier=identifier, verified=False, state='uploading', acknowledged=acknowledged))
                checkpoint()
                verified = publish(api, identifier, files, checks, not identifier.startswith('starpeople-field-starred-'), acknowledged, checkpoint)
                save(receipt, dict(signature=signature, identifier=identifier, verified=verified, checked=time.time(),
                                   state='verified' if verified else 'awaiting_index', files=checks, samples=sorted(samples), acknowledged=acknowledged, trim_revisions=revisions))
        except Exception as exc:
            value = read(receipt, {})
            value.update(verified=False, state='retry', error=str(exc)[:400])
            save(receipt, value)


if __name__ == '__main__':
    main()
