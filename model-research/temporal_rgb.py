"""HQ training input: native RGB crops from verified original-video packages."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

import av
import numpy as np
from PIL import Image


def read(path):
    return json.loads(path.read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def admitted(snapshot):
    records = read(snapshot / 'dataset.json')['samples']
    excluded = {r['origin'] for r in read(snapshot / 'research-admission.json')['excluded']}
    conflicts = set(read(snapshot / 'training-admission.json')['excluded_conflicting_pixels'])
    return {r['origin'].split(':')[-1]: r for r in records
            if r.get('human_confirmed') and r['split'] == 'train'
            and r['origin'] not in excluded and r['pixel_sha256'] not in conflicts}


def source_window(folder, row, annotation, review):
    # The reviewed PNG anchors identity even if the MP4 remux changed the PTS origin.
    width, height = row['width'], row['height']
    x, y, w, h = annotation['bounds']
    if not (0 <= x < x+w <= width and 0 <= y < y+h <= height):
        raise ValueError('invalid reviewed bounds')
    motion = row.get('motion', {})
    if motion.get('annotation_id') != annotation['annotation_id']:
        motion = {}
    side = max(160, 3 * max(w, h))
    cw, ch = min(side, width), min(side, height)
    roi = motion.get('crop_xywh', [min(max(0,x+w//2-cw//2),width-cw),
                                  min(max(0,y+h//2-ch//2),height-ch),cw,ch])
    left, top, cw, ch = roi
    if not (0 <= left <= x < x+w <= left+cw <= width and 0 <= top <= y < y+h <= top+ch <= height):
        raise ValueError('invalid context crop')
    still = folder / 'frames' / row['original']['file']
    if not still.resolve().is_relative_to((folder/'frames').resolve()) or digest(still.read_bytes()) != row['original']['sha256']:
        raise ValueError('invalid reviewed anchor')
    with Image.open(still) as image:
        ref = image.convert('RGB')
    pixels = ref.crop((x,y,x+w,y+h)).tobytes()
    if digest(f'{w}x{h}:RGB:'.encode()+pixels) != review['pixel_sha256']:
        raise ValueError('current review pixels differ')
    source = folder / 'video.mkv'
    trim = read(folder/'video-trim.json') if (folder/'video-trim.json').exists() else {}
    anchor = float(row['source_pts_seconds'])
    frame_number = row['frame']
    if not source.is_file():
        source = folder / 'video.mp4'
        frame_number -= int(trim.get('source_start_frame',0))
        if frame_number < 0 or row['frame'] >= trim.get('source_end_frame', float('inf')):
            raise ValueError('outside available original trim')
    if source.is_symlink() or not source.is_file():
        raise ValueError('missing original video')
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        if source.suffix == '.mp4':
            # Exact ordinal in the packet-preserving remux, including VFR and trims.
            matched = next((f for i,f in enumerate(container.decode(stream)) if i == frame_number),None)
            if matched is None:
                raise ValueError('original frame unavailable')
            anchor = float(matched.time)
        offsets = motion.get('sample_offsets_seconds')
        if offsets is not None and (not offsets or 0 not in offsets or offsets != sorted(set(offsets))):
            raise ValueError('invalid packaged timestamps')
        start = max(float((stream.start_time or 0)*stream.time_base), anchor-1)
        if stream.duration is not None:
            first = float((stream.start_time or 0)*stream.time_base)
            start = max(first,min(start,first+float(stream.duration*stream.time_base)-2))
        lower,upper = (anchor+offsets[0],anchor+offsets[-1]) if offsets else (start,start+2)
        container.seek(int((lower-.003)/stream.time_base),stream=stream,backward=True)
        rgb, times = [], []
        verified = False
        for frame in container.decode(stream):
            stamp = float(frame.time)
            if stamp < lower-.001: continue
            if stamp > upper+.001: break
            delta = stamp-anchor
            if offsets is not None:
                if len(times)==len(offsets): break
                if abs(delta-offsets[len(times)]) > .001: continue
            elif times and abs(delta) > .0005 and delta-times[-1] < .1-1e-6:
                continue
            image = frame.to_image().convert('RGB')
            if abs(delta) <= .001:
                if image.size != ref.size or image.tobytes() != ref.tobytes():
                    raise ValueError('decoded anchor differs from reviewed original')
                verified = True
            rgb.append(np.asarray(image.crop((left,top,left+cw,top+ch))))
            times.append(delta)
    if not verified or len(rgb)<2 or (offsets is not None and len(times)!=len(offsets)):
        raise ValueError('incomplete source sequence')
    return np.stack(rgb), np.asarray(times,dtype=np.float64), roi, source.name


def prepare(archive, snapshot, output):
    if not archive.is_dir() or not archive.parent.is_mount() or not output.parent.is_dir():
        raise RuntimeError('training or archive storage unavailable')
    reviews = admitted(snapshot)
    output.mkdir(exist_ok=True)
    objects = output/'sequences'
    objects.mkdir(exist_ok=True)
    manifest = output/'manifest.json'
    previous = {s['key']: s for s in read(manifest)['samples']} if manifest.exists() else {}
    samples, skips, seen = [], Counter(), set()
    for item in sorted(archive.iterdir()):
        receipts = sorted(item.glob('*/.archive-copy.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True)
        if not receipts: continue
        folder = receipts[0].parent
        receipt = read(receipts[0])
        if not receipt.get('verified'): continue
        index = folder/'frames/reviewed-index.json'
        if not index.is_file(): continue
        index_hash = digest(index.read_bytes())
        if not any(e['name']=='frames/reviewed-index.json' and e['sha256']==index_hash for e in receipt['files']):
            skips['unverified reviewed index']+=1
            continue
        for row in read(index)['frames']:
            for ann in row['annotations']:
                aid = ann.get('annotation_id')
                r = reviews.get(aid)
                if r is None or aid in seen: continue
                key = digest(json.dumps([2,item.name,folder.name,index_hash,row['frame'],aid,r['pixel_sha256']]).encode())
                s = previous.get(key)
                try:
                    if s is None or not (objects/(key+'.npz')).is_file():
                        frames,times,roi,video = source_window(folder,row,ann,r)
                        with tempfile.NamedTemporaryFile(dir=objects,suffix='.npz',delete=False) as tmp:
                            try: np.savez_compressed(tmp,rgb=frames,offset_seconds=times)
                            except BaseException:
                                os.unlink(tmp.name)
                                raise
                        os.replace(tmp.name,objects/(key+'.npz'))
                        s=dict(key=key,file='sequences/'+key+'.npz',recording=item.name,
                               revision=folder.name,source_video=video,original_frame=row['frame'],
                               original_pts_seconds=row['source_pts_seconds'],crop_xywh=roi,
                               annotation_id=aid,review_bounds_xywh=ann['bounds'],frames=len(times))
                except (ValueError,FileNotFoundError,av.FFmpegError) as exc:
                    skips[str(exc)[:160]]+=1
                    continue
                samples.append(dict(s,label=r['label'],group=r['group'],origin=r['origin']))
                seen.add(aid)
    data=dict(schema=1,snapshot=snapshot.name,input='native_rgb24_original_video',samples=samples,
              counts=dict(Counter(s['label'] for s in samples)),skipped=dict(skips))
    temp=manifest.with_suffix('.tmp')
    temp.write_text(json.dumps(data));temp.replace(manifest)
    return data


def training_sequences(dataset):
    """Yield time x height x width x RGB uint8, real time offsets, and the human label/group."""
    for sample in read(dataset/'manifest.json')['samples']:
        with np.load(dataset/sample['file'],allow_pickle=False) as data:
            yield data['rgb'], data['offset_seconds'], sample


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--training-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fit-research-head',action='store_true')
    args=parser.parse_args()
    if not any(p.is_mount() and p!=Path('/') for p in args.output.resolve().parents):
        raise RuntimeError('external training storage unavailable')
    args.output.mkdir(exist_ok=True)
    with (args.output/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        snapshot=Path(read(args.training_root/'status.json')['run_directory'])
        result=prepare(args.archive,snapshot,args.output)
        if args.fit_research_head:
            from temporal_rgb_fit import fit
            fit(args.output)
        print(result['counts'],result['skipped'],flush=True)
