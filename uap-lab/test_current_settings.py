import tempfile
import unittest
from pathlib import Path

import detection_settings
import model_settings


class CurrentSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name)

    def test_shared_values_replace_legacy_settings_without_numbered_saves(self):
        path = self.data / 'detection-settings.json'
        model_settings.save(path, {'values': {'motion_difference': 9}, 'revision': 4, 'history': []})
        before = detection_settings.state(self.data)
        self.assertNotIn('revision', before)
        self.assertEqual(detection_settings.snapshot(self.data)['revision'], 4)
        payload = {'expected': before['values'], 'values': {'motion_difference': 11}}
        after = detection_settings.update(self.data, payload)
        self.assertEqual(after['values']['motion_difference'], 11)
        self.assertNotIn('revision', after)
        self.assertEqual(set(model_settings.read(path)), {'values', 'epoch'})
        with self.assertRaisesRegex(ValueError, 'changed'):
            detection_settings.update(self.data, dict(payload, values={'motion_difference': 12}))
        key = detection_settings.snapshot(self.data)['revision']
        detection_settings.update(self.data, {'reset': True})
        self.assertEqual(detection_settings.snapshot(self.data)['revision'], 0)
        detection_settings.update(self.data, {'values': {'motion_difference': 11}})
        self.assertEqual(detection_settings.snapshot(self.data)['revision'], key)

    def test_decision_settings_keep_historical_scores_and_use_current_values(self):
        version = 'a' * 64
        key = 'experimental:' + version
        root = self.data / 'model-inspector'
        args = {'lane': 'experimental', 'version': version}
        policy = {'version': version, 'thresholds': {'anomalous': .6}}
        model_settings.save(root / 'models.json', {'models': [dict(args, policy=policy, available=True)]})
        path = root / 'settings.json'
        model_settings.save(path, {'models': {key: {'revision': 3, 'values': {'anomaly_threshold': .7}}}})

        def policy_now():
            return model_settings.effective(policy, 'experimental', model_settings.snapshot(self.data))

        self.assertEqual(policy_now()['settings_revision'], 3)
        prior = model_settings.defaults(policy_now())
        model_settings.update(self.data, dict(args, values=prior, expected=prior))
        self.assertEqual(policy_now()['settings_revision'], 3)
        model_settings.update(self.data, dict(args, expected=prior, values={'anomaly_threshold': .8}))
        self.assertEqual(policy_now()['thresholds']['anomalous'], .8)
        marker = policy_now()['settings_revision']
        self.assertEqual(set(model_settings.read(path)['models'][key]), {'values', 'epoch'})
        with self.assertRaisesRegex(ValueError, 'changed'):
            model_settings.update(self.data, dict(args, expected=prior, reset=True))
        model_settings.update(self.data, dict(args, reset=True))
        self.assertEqual(policy_now()['settings_revision'], 0)
        self.assertEqual(policy_now()['thresholds']['anomalous'], .6)
        model_settings.update(self.data, dict(args, values={'anomaly_threshold': .8}))
        self.assertEqual(policy_now()['settings_revision'], marker)
