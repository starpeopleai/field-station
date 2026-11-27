"""Persistent detection bookmarks and downloads of unchanged source media."""
import fcntl, mimetypes, threading, time
from pathlib import Path
from urllib.parse import quote
from object_omission import parse, omitted
from retired_data import read, save


def canonical(key):
    return ':'.join(parse(key))


def stars(data):
    return read(Path(data)/'starred-objects.json', {}).get('objects', {})


def object_folder(data, key):
    kind, video, sample = parse(key)
    data = Path(data)
    if omitted(data, key):
        raise ValueError('Object was deleted or is queued for deletion')
    if kind == 'review':
        from email_review import folder_for
        folder = folder_for(data, video)
        if sample != video:
            record = read(data/'email-reviews/examples'/sample/'review.json', {})
            if record.get('event_id') != video or record.get('deleted'):
                raise ValueError('Detection not found')
    else:
        from labeled_frames import preserved_root
        folder = (preserved_root() if kind == 'preserved' else data)/'videos'/video
        if not any(a.get('id') == sample for a in read(folder/'annotations.json', [])):
            raise ValueError('Detection not found')
    if folder.is_symlink():
        raise ValueError('Unsafe source folder')
    return kind, video, folder


def set_star(data, body):
    key = body.get('id'); value = body.get('starred')
    if type(value) is not bool:
        raise ValueError('Choose a star state')
    import detection_library as library
    with library._SAVE_LOCK:
        object_folder(data, key)
        with (Path(data)/'starred-objects.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            entries = stars(data)
            if value: entries[canonical(key)] = dict(starred_epoch=time.time())
            else: entries.pop(canonical(key), None)
            save(Path(data)/'starred-objects.json', dict(objects=entries))
    return dict(id=key, starred=value)


def original(data, key):
    kind, video, folder = object_folder(data, key)
    if kind == 'review':
        from review_playback import native_path
        path = native_path(data, video)
        name = 'clip-'+video+'-original.mp4'; mime = 'video/mp4'
    else:
        meta = read(folder/'video.json', {})
        path = folder/'source'
        name = Path(meta.get('name') or ('video-'+video+'.mkv')).name
        mime = meta.get('mime') or mimetypes.guess_type(name)[0] or 'application/octet-stream'
    if path.is_symlink() or not path.is_file():
        raise ValueError('Original clip is unavailable or has been removed by retention')
    return path, mime, name


_BUILDING = set()
_LOCK = threading.Lock()

def original_status(data, key):
    kind, video, folder = object_folder(data, key)
    try:
        path, mime, name = original(data, key)
        return dict(state='ready', filename=name, bytes=path.stat().st_size,
                    download_url='/api/objects/original?id='+quote(key, safe=''))
    except ValueError:
        if kind != 'review' or (folder/'local-media-retired.json').exists():
            return dict(state='unavailable', error='The original clip is no longer available locally.')
    error = read(folder/'review-error.json', {})
    if error.get('error'):
        return dict(state='unavailable', error='Original clip preparation failed: '+error['error'])
    build_key = (str(data), video)
    with _LOCK:
        if build_key not in _BUILDING:
            _BUILDING.add(build_key)
            def build():
                try:
                    from email_review import prepare
                    prepare(data, video)
                except Exception:
                    pass # prepare records the error for the next status request.
                finally:
                    with _LOCK: _BUILDING.discard(build_key)
            threading.Thread(target=build, daemon=True).start()
    return dict(state='preparing')
