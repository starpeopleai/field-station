"""Fit and export a versioned Experimental model with a frozen RGB backbone.

Inputs are native_feature_worker embeddings and their ordered row manifest. The
source dataset defines admission and calibration independently of matrix order.
"""
import argparse
import hashlib
import io
import json
import math
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch

from curated_refinement import Recipe, fit, logits
from human_head import ReviewedHead


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def confusion(target, scores, threshold):
    predicted = scores >= threshold
    return dict(tp=int((target & predicted).sum()), fp=int((~target & predicted).sum()),
                tn=int((~target & ~predicted).sum()), fn=int((target & ~predicted).sum()))


def composite(counts):
    tp, fp, tn, fn = (counts[k] for k in ('tp', 'fp', 'tn', 'fn'))
    if not tp or not tn:
        return 0.
    return 100 / (.35 * (tp + fn) / tp + .25 * (tp + fp) / tp +
                  .25 * (tn + fp) / tn + .15 * sum(counts.values()) / (tp + tn))


def identities(rows):
    keys = set()
    for row in rows:
        keys.update(row.get('group_aliases') or ())
        keys.update((row['group'], row['pixel_sha256'], row['origin']))
        if row.get('generation'):
            keys.add('generation:' + row['generation'])
    return keys


def native_inputs(source, dataset, temporary):
    """Extract verified reviewed and calibration crops with the deployed Vision preprocessing."""
    from PIL import Image
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'recognition'))
    from crop_client import CropClassifier

    rows = [r for r in dataset['samples'] if r['split'] == 'calibration'
            or (r['human_confirmed'] and r['split'] == 'train')]
    matrix = None
    tools = source.parent.parent / 'tools'
    with CropClassifier(tools / 'native_feature_worker', source / 'features.mlmodelc',
                        dataset['fingerprint'], timeout=120) as worker:
        for start in range(0, len(rows), 32):
            paths = [source / row['image'] for row in rows[start:start + 32]]
            images = []
            for row, path in zip(rows[start:start + 32], paths):
                if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
                    raise ValueError('Unsafe reviewed crop')
                raw = path.read_bytes()
                with Image.open(io.BytesIO(raw)) as im:
                    im = im.convert('RGB')
                    pixels = f'{im.width}x{im.height}:RGB:'.encode() + im.tobytes()
                if hashlib.sha256(pixels).hexdigest() != row['pixel_sha256']:
                    raise ValueError('Reviewed pixels changed')
                images.append(raw)
            vectors = np.asarray([r['features'] for r in worker.predict(images)], dtype=np.float32)
            if len(vectors) != len(images) or not np.isfinite(vectors).all():
                raise ValueError('Incomplete native embeddings')
            if matrix is None:
                matrix = np.lib.format.open_memmap(temporary / 'features.npy', mode='w+',
                                                   dtype=np.float32, shape=(len(rows), vectors.shape[1]))
            matrix[start:start + len(vectors)] = vectors
    return rows, matrix


def select_inputs(dataset, manifest, matrix):
    if matrix.ndim != 2 or len(manifest) != len(matrix):
        raise ValueError('Native embedding matrix and row manifest differ')
    index = {r['origin']: i for i, r in enumerate(manifest)}
    if len(index) != len(manifest):
        raise ValueError('Duplicate native embedding origin')
    train = [r for r in dataset['samples'] if r['split'] == 'train' and r['human_confirmed']]
    calibration = [r for r in dataset['samples'] if r['split'] == 'calibration']
    if identities(train) & identities(calibration):
        raise ValueError('Training and calibration share a recording or crop')
    def extract(rows):
        indices = [index[r['origin']] for r in rows]
        for row, i in zip(rows, indices):
            if any(row[k] != manifest[i][k] for k in ('pixel_sha256', 'label', 'group')):
                raise ValueError('Manifest and source disagree on a reviewed crop')
        return torch.from_numpy(matrix[indices]), torch.tensor([r['label'] == 'anomalous' for r in rows])
    return train, calibration, extract(train), extract(calibration)


def calibrate(head, train, calibration, importance, recipe, previous_threshold):
    """Choose a cut on the calibration set under strict full-training gain constraints.

    Allow one binomial standard error of the best calibration recall at no extra
    calibration false positives. Within that band prefer to halve the number of missed training anomalies,
    then maximize the composite score at that recall.
    """
    x, y = train
    cx, cy = calibration
    y = y.numpy()
    cy = cy.numpy()
    boundary = math.log(previous_threshold / (1 - previous_threshold))
    before = confusion(y, logits(head, x).numpy(), boundary)
    reference = confusion(cy, logits(head, cx).numpy(), boundary)
    if before['fn'] == 0 or before['fp'] == 0:
        raise ValueError('Strict improvement of both error counts is impossible')
    candidates = []
    checkpoints = {}
    def observe(epoch, model):
        if epoch != 1 and epoch % 6 and epoch != recipe.epochs:
            return
        scores = logits(model, x).numpy()
        calibration_scores = logits(model, cx).numpy()
        positives = np.sort(scores[y])
        for misses in np.unique(np.linspace(0, before['fn'] - 1, 12, dtype=int)):
            lower = positives[misses - 1] if misses else positives[0] - 0.01
            cut = float((float(lower) + float(positives[misses])) / 2)
            training = confusion(y, scores, cut)
            held = confusion(cy, calibration_scores, cut)
            if training['fp'] >= before['fp'] or training['fn'] >= before['fn']:
                continue
            if held['fp'] > reference['fp'] or held['tp'] < reference['tp']:
                continue
            if epoch not in checkpoints:
                checkpoints[epoch] = {k: v.detach().clone() for k, v in model.state_dict().items()}
            candidates.append(dict(epoch=epoch, cut=cut, training=training, calibration=held))
    fit(head, x, torch.from_numpy(y), importance, recipe, observe)
    if not candidates:
        raise ValueError('No checkpoint met the training and calibration requirements')
    best_hits = max(c['calibration']['tp'] for c in candidates)
    positive_count = int(cy.sum())
    tolerance = math.sqrt(best_hits * (1 - best_hits / positive_count))
    eligible = (c for c in candidates if c['calibration']['tp'] >= best_hits - tolerance)
    choice = max(eligible, key=lambda c: (2 * c['training']['fn'] <= before['fn'],
                                            composite(c['training']), c['calibration']['tp'], -c['epoch']))
    head.load_state_dict(checkpoints[choice['epoch']])
    # Fold the operating point into the learned intercept. The deployed threshold
    # and input contract stay identical to the reference comparison.
    with torch.no_grad():
        head.layers[-1].bias.add_(math.log(recipe.threshold / (1 - recipe.threshold)) - choice['cut'])
    return dict(chosen=choice, baseline_training=before, baseline_calibration=reference)


class Classifier(torch.nn.Module):
    def __init__(self, backbone, head):
        super().__init__()
        self.features = backbone
        self.head = head

    def forward(self, image):
        return self.head(self.features(image)).softmax(dim=1)


def train(args):
    import coremltools as ct
    from torchvision.models import mobilenet_v3_small
    from vision_features import build_features
    from native_compile import compile_model

    recipe = Recipe(epochs=72, threshold=args.threshold)
    torch.manual_seed(recipe.seed)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    dataset = read(args.source / 'dataset.json')
    policy = read(args.source / 'candidate-policy.json')
    if dataset['blockers'] or policy['classes'] != ['anomalous', 'not_anomalous']:
        raise ValueError('Expected a qualified binary human-reviewed source')
    flags = read(args.flags)
    if set(flags.values()) - {'star', 'pin'}:
        raise ValueError('Unknown reviewer importance')
    if bool(args.features) != bool(args.rows):
        raise ValueError('A cached native matrix requires its ordered row manifest')
    with tempfile.TemporaryDirectory() as tmp:
        manifest, matrix = ((read(args.rows), np.load(args.features, mmap_mode='r')) if args.features
                            else native_inputs(args.source, dataset, Path(tmp)))
        rows, calibration, train_data, cal_data = select_inputs(dataset, manifest, matrix)
    importance = torch.tensor([{'star': recipe.star_weight, 'pin': recipe.pin_weight}
                              .get(flags.get(r['origin']), 1.) for r in rows])
    weights = torch.load(args.source / 'candidate-weights.pt', map_location='cpu', weights_only=True)
    head = ReviewedHead(weights['head.mean'], weights['head.std'], len(weights['head.layers.0.bias']))
    model = Classifier(build_features(mobilenet_v3_small(weights=None)), head).eval()
    model.load_state_dict(weights)
    result = calibrate(head, train_data, cal_data, importance, recipe, args.threshold)
    evidence = dict(result, recipe=asdict(recipe), parent_version=policy['version'],
                    sample_id=hashlib.sha256(json.dumps([(r['origin'], r['pixel_sha256'], r['label'])
                                                        for r in rows]).encode()).hexdigest(),
                    training_count=len(rows), calibration_count=len(calibration), flags_sha256=digest(args.flags),
                    fit_stars=int((importance == recipe.star_weight).sum()),
                    fit_pins=int((importance == recipe.pin_weight).sum()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as tmp:
        staged = Path(tmp) / 'run'
        staged.mkdir()
        torch.save(model.state_dict(), staged / 'candidate-weights.pt')
        evidence['weights_sha256'] = digest(staged / 'candidate-weights.pt')
        version = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
        traced = torch.jit.trace(model.eval(), torch.zeros(1, 3, 224, 224), check_trace=False)
        native = ct.convert(traced, inputs=[ct.ImageType(name='image', shape=(1, 3, 224, 224), scale=1/255)],
                            classifier_config=ct.ClassifierConfig(policy['classes']),
                            minimum_deployment_target=ct.target.macOS13, compute_precision=ct.precision.FLOAT32)
        native.save(str(staged / 'candidate.mlpackage'))
        compile_model(args.compiler, staged / 'candidate.mlpackage', staged / 'candidate.mlmodelc')
        policy.update(version=version, thresholds={**policy['thresholds'], 'anomalous': recipe.threshold},
                      training_recipe='curated_hard_negative_refinement', classification_input_scope='review_box')
        policy.pop('night_context_confirmation', None)
        write(staged / 'candidate-policy.json', policy)
        write(staged / 'fit.json', evidence)
        # Model selection needs one original runtime probe, and the catalog needs
        # the full fitted manifest. Do not duplicate the private training corpus.
        write(staged / 'dataset.json', dict(fingerprint=version, classes=policy['classes'], samples=rows,
              training_lane='human_experimental', training_strategy=policy['training_recipe'],
              counts=dataset['human_training_counts'], human_training_counts=dataset['human_training_counts']))
        probe = Path(rows[0]['image'])
        if probe.is_absolute() or '..' in probe.parts:
            raise ValueError('Unsafe probe path')
        (staged / probe).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.source / probe, staged / probe)
        staged.rename(args.output)
    print(json.dumps(dict(version=version, **result)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'flags', 'compiler', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--features', type=Path, help='Optional native embedding matrix')
    parser.add_argument('--rows', type=Path, help='Ordered manifest for the optional matrix')
    parser.add_argument('--threshold', type=float, required=True, help='Existing Experimental operating threshold')
    train(parser.parse_args())
