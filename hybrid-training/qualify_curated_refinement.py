"""Replay every reviewed RGB crop with an exported Experimental Core ML package."""
import argparse
import hashlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from experimental_profile import package_digest
from worker import read, save


def qualify(folder, benchmark, tools):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'uap-lab/recognition'))
    from crop_client import CropClassifier

    sample = read(benchmark / 'sample.json')
    point = read(benchmark / 'result.json')
    fit = read(folder / 'fit.json')
    policy = read(folder / 'candidate-policy.json')
    rows = sample['samples']
    identity = hashlib.sha256(json.dumps([(r['origin'], r['pixel_sha256'], r['label'])
                                          for r in rows]).encode()).hexdigest()
    if not identity == fit['sample_id'] == point['sample_id'] == sample['id']:
        raise ValueError('Different training cohorts')
    if point['experimental_version'] != fit['parent_version'] or len(rows) != point['count']:
        raise ValueError('Missing comparable full parent replay')
    source = Path(sample['source_folder']).resolve()
    threshold = policy['thresholds']['anomalous']
    counts = dict(tp=0, tn=0, fp=0, fn=0)
    version = policy['version']
    package = folder / 'candidate.mlpackage'
    checksum = package_digest(package)
    with tempfile.TemporaryDirectory() as tmp:
        compiled = Path(tmp) / 'candidate.mlmodelc'
        subprocess.run([str(tools / 'compile_model'), str(package), str(compiled)], check=True)
        with CropClassifier(tools / 'crop_worker', compiled, version, timeout=120) as worker:
            for offset in range(0, len(rows), 32):
                batch = rows[offset:offset + 32]
                images = []
                for row in batch:
                    path = source / row['image']
                    if path.is_symlink() or not path.resolve().is_relative_to(source):
                        raise ValueError('Unsafe benchmark image path')
                    raw = path.read_bytes()
                    with Image.open(io.BytesIO(raw)) as image:
                        image = image.convert('RGB')
                        pixels = f'{image.width}x{image.height}:RGB:'.encode() + image.tobytes()
                    if hashlib.sha256(pixels).hexdigest() != row['pixel_sha256']:
                        raise ValueError('Reviewed crop changed')
                    images.append(raw)
                predictions = worker.predict(images)
                if len(predictions) != len(batch):
                    raise ValueError('Incomplete native predictions')
                for row, prediction in zip(batch, predictions):
                    score = prediction['scores']['anomalous']
                    if not 0 <= score <= 1:
                        raise ValueError('Invalid native probability')
                    hit = score >= threshold
                    if row['label'] == 'anomalous':
                        counts['tp' if hit else 'fn'] += 1
                    elif row['label'] == 'not_anomalous':
                        counts['fp' if hit else 'tn'] += 1
                    else:
                        raise ValueError('Unknown review label')
    if checksum != package_digest(package):
        raise ValueError('Native package changed during replay')
    parent = {key: point['lanes']['experimental'][key] for key in counts}
    full = dict(count=len(rows), parent=parent, candidate=counts)
    evidence = dict(version=version, parent_version=fit['parent_version'], sample_id=identity,
                    weights_sha256=fit['weights_sha256'], package_sha256=checksum, threshold=threshold,
                    protocol='native-full-review-box-v1', sets=dict(benchmark=full))
    save(folder / 'native-evaluation.json', evidence)
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('folder', 'benchmark', 'tools'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(qualify(args.folder, args.benchmark, args.tools)))
