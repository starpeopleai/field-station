"""Resolve the Experimental lane and retain explicitly qualified learned weights."""
import fcntl
import hashlib
import time
from pathlib import Path

from worker import model_folder, read, save


def package_digest(package):
    digest = hashlib.sha256()
    for path in sorted(package.rglob('*')):
        if path.is_file():
            digest.update(path.relative_to(package).as_posix().encode() + b'\0')
            with path.open('rb') as stream:
                digest.update(hashlib.file_digest(stream, 'sha256').digest())
    return digest.hexdigest()


def selection(state):
    return dict(version=state['shadow_version'], folder=state['shadow_folder'],
                publication=state.get('publication'), mode=state['experiment_mode'])


def replace_state(root, previous, state):
    if previous:
        save(root / 'profile-history' / (str(time.time_ns()) + '.json'), previous)
    save(root / 'status.json', state)


def select_qualified(root, folder, benchmark):
    """Compare-and-swap a verified artifact against its exact native parent replay."""
    root, folder = Path(root), Path(folder).resolve()
    policy = read(folder / 'candidate-policy.json')
    version = policy['version']
    if folder != (root / 'runs' / version).resolve():
        raise ValueError('Expected an immutable Experimental run directory')
    fit = read(folder / 'fit.json')
    native = read(folder / 'native-evaluation.json')
    point = read(Path(benchmark) / 'result.json')
    if native['version'] != version or native['parent_version'] != fit['parent_version']:
        raise ValueError('Evaluation and artifact versions differ')
    if not (native['sample_id'] == point['sample_id'] == fit['sample_id']):
        raise ValueError('Different reviewed cohorts')
    if point['experimental_version'] != native['parent_version']:
        raise ValueError('Benchmark belongs to a different parent')
    if policy['thresholds']['anomalous'] != native['threshold']:
        raise ValueError('Operating point differs from native qualification')
    with (folder / 'candidate-weights.pt').open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    if checksum != native['weights_sha256'] or checksum != fit['weights_sha256']:
        raise ValueError('Trained weights changed')
    if not (folder / 'candidate.mlpackage' / 'Manifest.json').is_file():
        raise ValueError('Missing native package')
    if package_digest(folder / 'candidate.mlpackage') != native['package_sha256']:
        raise ValueError('Native package changed after qualification')
    full = native['sets']['benchmark']
    previous, candidate = full['parent'], full['candidate']
    for key in ('tp', 'tn', 'fp', 'fn'):
        if point['lanes']['experimental'][key] != previous[key]:
            raise ValueError('Parent confusion counts differ from Metrics')
    if not (sum(candidate.values()) == full['count'] == point['count'] == fit['training_count']):
        raise ValueError('Incomplete native evaluation')
    if any(candidate[a] + candidate[b] != previous[a] + previous[b]
           for a, b in [('tp', 'fn'), ('tn', 'fp')]):
        raise ValueError('Class support changed')
    # On an identical binary cohort these two strict gains improve all five metrics.
    if candidate['fn'] >= previous['fn'] or candidate['fp'] >= previous['fp']:
        raise ValueError('Both false positives and missed anomalies must decrease')
    with (root / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = read(root / 'status.json', {})
        if old.get('shadow_version') == version:
            return selection(old)
        if old.get('shadow_version') != native['parent_version']:
            raise ValueError('Experimental has changed since qualification')
        now = time.time()
        state = dict(old, phase='shadow_ready', training_lane='human_experimental',
                     experiment_mode='trained', baseline_copy=False, shadow_seed_only=False,
                     shadow_version=version, shadow_folder=str(folder), run_directory=str(folder),
                     baseline_version=native['parent_version'], trained_epoch=now, updated_epoch=now,
                     reason='Learned weights qualified on the full reviewed cohort.',
                     publication=read(root / 'publications' / (version + '.json')), error=None)
        state.pop('publication_error', None)
        replace_state(root, old, state)
        return selection(state)


def bind(human_root, experimental_root, source=None):
    root, human_root = Path(experimental_root), Path(human_root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = read(root / 'status.json', {})
        if old.get('experiment_mode') == 'trained':
            return selection(old)
        human = read(human_root / 'status.json', {})
        folder = Path(source) if source else model_folder(human_root, human['active_version'])
        version = read(folder / 'candidate-policy.json')['version']
        if not (folder / 'candidate-weights.pt').is_file() or not (folder / 'candidate.mlpackage').is_dir():
            raise ValueError('Stable artifacts unavailable')
        publication = read(human_root / 'model-publication/status.json', {})
        publication = publication if publication.get('version') == version else None
        if (old.get('shadow_version') != version or old.get('experiment_mode') != 'decision_profile'
                or old.get('shadow_folder') != str(folder) or old.get('run_directory') != str(folder)):
            state = dict(old, phase='shadow_ready', experiment_mode='decision_profile',
                         training_lane='human_experimental', shadow_folder=str(folder), run_directory=str(folder),
                         shadow_version=version, shadow_seed_only=False, baseline_copy=True, baseline_version=version,
                         trained_epoch=human.get('trained_epoch'), error=None, publication=publication,
                         reason='Same learned weights as Stable; independent decision settings.', updated_epoch=time.time())
            state.pop('publication_error', None)
            replace_state(root, old, state)
        return dict(version=version, folder=str(folder), previous_version=old.get('shadow_version'),
                    publication=publication, mode='decision_profile')


def sync(cfg):
    result = bind(cfg['human_root'], cfg['experimental_root'])
    if result['mode'] == 'decision_profile':
        from model_inspector_sync import rpc
        policy = read(Path(result['folder']) / 'candidate-policy.json')
        code = ("import sys,json;from pathlib import Path;sys.path.insert(0,'/Users/ufo-field/ufo-field/uap-lab');"
                "from model_settings import rebase_experimental;print(json.dumps(rebase_experimental("
                "(Path('/Volumes/UFO-Field-Working-Files/uap-lab') if Path('/Volumes/UFO-Field-Working-Files/uap-lab').is_dir() else Path('/Volumes/UFO-Field/uap-lab'))," + repr(result['version']) + "," + repr(policy) + ")))")
        rpc(cfg, code)
    return result



if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description='Select a qualified model for the Experimental lane')
    for name in ('root', 'folder', 'benchmark'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(select_qualified(args.root, args.folder, args.benchmark)))
