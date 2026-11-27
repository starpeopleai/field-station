import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from starred_archive import publish


class StarredArchiveTests(unittest.TestCase):
    def test_waits_for_public_checksum_without_resending_accepted_bytes(self):
        api = MagicMock()
        api.metadata.return_value = {}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'frame.png'
            path.write_bytes(b'frame')
            checks = {'frame.png': hashlib.md5(b'frame').hexdigest()}
            files = {'frame.png': path}
            ack = {}
            for attempt in range(2):
                self.assertFalse(publish(api, 'item', files, checks, False, ack, lambda: None))
            api.raw.assert_called_once()
            api.metadata.return_value = {'files': [{'name': 'frame.png', 'md5': checks['frame.png']}]}
            self.assertTrue(publish(api, 'item', files, checks, False, ack, lambda: None))
            api.raw.assert_called_once()
