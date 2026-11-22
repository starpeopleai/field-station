"""Build one source-linked, two-second GIF from a reviewed recording."""
import hashlib
from pathlib import Path

import av
from PIL import Image


def write_preview(folder, raw, entries, work, revision_dir, trim):
    start = int(trim.get('source_start_frame', 0))
    end = trim.get('source_end_frame')
    choices = [(row, annotation) for row in entries
               if row['frame'] >= start and (end is None or row['frame'] < end)
               for annotation in row['annotations']]
    if not choices:
        return
    row, annotation = min(choices, key=lambda item: (
        item[1]['label'] != 'anomalous', item[0]['frame'], str(item[1].get('annotation_id'))))
    target = row['frame'] - start
    x, y, w, h = annotation['bounds']
    width, height = row['width'], row['height']
    side = max(160, 3 * max(w, h))
    cw, ch = min(width, side), min(height, side)
    left = min(max(0, x + w // 2 - cw // 2), width - cw)
    top = min(max(0, y + h // 2 - ch // 2), height - ch)
    clip = folder / 'video.mp4' if trim.get('enabled') else raw
    anchor = row['source_pts_seconds']
    with av.open(str(clip)) as reader:
        stream = reader.streams.video[0]
        if trim.get('enabled'):
            # The exported trim can have a new PTS origin. Match its exact frame.
            anchor = next(float(f.time) for i, f in enumerate(reader.decode(stream)) if i == target)
        first = float((stream.start_time or 0) * stream.time_base)
        begin = max(first, anchor - 1)
        if stream.duration is not None:
            begin = max(first, min(begin, first + float(stream.duration * stream.time_base) - 2))
        reader.seek(int(begin / stream.time_base), stream=stream, backward=True)
        samples = []
        for frame in reader.decode(stream):
            stamp = float(frame.time)
            if stamp < begin - 1e-6:
                continue
            if stamp >= begin + 2 - 1e-6:
                break
            if samples and abs(stamp - anchor) > 1e-6 and stamp - samples[-1][0] < .1 - 1e-6:
                continue
            image = frame.to_image().convert('RGB').crop((left, top, left + cw, top + ch))
            image.thumbnail((320, 320), Image.Resampling.LANCZOS)
            samples.append((stamp, image))
    if not samples:
        raise ValueError('No video frames in the reviewed motion window')
    times, images = zip(*samples)
    durations = [max(10, round((b - a) * 100) * 10) for a, b in zip(times, times[1:])]
    durations.append(min(100, max(10, round((begin + 2 - times[-1]) * 100) * 10)))
    name = f"frame-{row['frame']:09d}-motion.gif"
    path = Path(work) / name
    images[0].save(path, save_all=True, append_images=images[1:], duration=durations, loop=0)
    row['motion'] = dict(file=revision_dir + '/' + name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         source_video='video.mp4', source_frame=target, annotation_id=annotation.get('annotation_id'),
                         crop_xywh=[left, top, cw, ch], anchor_source_pts_seconds=row['source_pts_seconds'],
                         sample_offsets_seconds=[round(t - anchor, 6) for t in times],
                         duration_ms=sum(durations))
