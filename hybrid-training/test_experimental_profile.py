import hashlib
import tempfile
import unittest
from pathlib import Path

from experimental_profile import bind, package_digest, select_qualified
from worker import read, save


class ExperimentalReleaseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run = self.root / 'runs' / 'new'
        package = self.run / 'candidate.mlpackage'
        package.mkdir(parents=True)
        (package / 'Manifest.json').write_text('{}')
        (self.run / 'candidate-weights.pt').write_bytes(b'weights')
        digest = hashlib.sha256(b'weights').hexdigest()
        self.benchmark = self.root / 'comparison'
        old = dict(tp=10, tn=80, fp=8, fn=2)
        new = dict(tp=11, tn=85, fp=3, fn=1)
        save(self.root / 'status.json', {'shadow_version': 'old'})
        save(self.benchmark / 'result.json', dict(experimental_version='old', sample_id='sample',
             count=100, lanes=dict(experimental=old)))
        save(self.run / 'candidate-policy.json', dict(version='new', thresholds=dict(anomalous=.6)))
        save(self.run / 'fit.json', dict(parent_version='old', sample_id='sample', training_count=100,
                                        weights_sha256=digest))
        self.proof = self.run / 'native-evaluation.json'
        save(self.proof, dict(version='new', parent_version='old', sample_id='sample',
             threshold=.6, weights_sha256=digest, package_sha256=package_digest(package),
             sets=dict(benchmark=dict(count=100, parent=old, candidate=new))))

    def test_survives_catalog_refresh_and_repeated_delivery(self):
        expected = select_qualified(self.root, self.run, self.benchmark)
        self.assertEqual(bind(self.root / 'stable', self.root), expected)
        self.assertEqual(select_qualified(self.root, self.run, self.benchmark), expected)
        self.assertEqual(len(list((self.root / 'profile-history').glob('*.json'))), 1)

    def test_refuses_recall_regression_even_when_precision_improves(self):
        proof = read(self.proof)
        proof['sets']['benchmark']['candidate'].update(tp=9, fn=3)
        save(self.proof, proof)
        with self.assertRaisesRegex(ValueError, 'missed anomalies'):
            select_qualified(self.root, self.run, self.benchmark)
        self.assertEqual(read(self.root / 'status.json')['shadow_version'], 'old')

    def test_changed_native_artifact_is_rejected(self):
        (self.run / 'candidate.mlpackage' / 'Manifest.json').write_text('modified')
        with self.assertRaisesRegex(ValueError, 'package changed'):
            select_qualified(self.root, self.run, self.benchmark)
