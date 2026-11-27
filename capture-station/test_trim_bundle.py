import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import starred_archive
from starred_trim import save


class TrimBundleTests(TestCase):
    def test_trim_keeps_full_recording_in_publication_plan(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'uap-lab'
            data.mkdir()
            event = 'a' * 32
            state = root / 'archive-tags/starred-bundles'
            state.mkdir(parents=True)
            source = root / 'full.mp4'
            subprocess.run([shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=size=160x90:rate=30:duration=2', '-c:v', 'libx264', str(source)], check=True)
            full_hash = hashlib.md5(source.read_bytes()).hexdigest()
            (data / 'starred-objects.json').write_text('{"objects":{}}')
            (state / 'context.json').write_text(json.dumps({event: {'continuous.mp4': str(source)}}))
            save(data,event,'continuous.mp4',{'start':.5,'end':1.5})
            source.unlink()  # The rolling source may expire before the publisher runs.
            with patch.object(sys, 'argv', ['archive','--data',str(data),'--state',str(state),'--private',str(root)]), patch.object(starred_archive, 'publish', return_value=True) as send:
                starred_archive.main()
            checks=send.call_args.args[3]
            self.assertEqual(checks['continuous.mp4'],full_hash)
            self.assertNotEqual(checks['continuous-trimmed.mp4'],full_hash)
            receipt=json.loads((state/('review-'+event+'.json')).read_text())
            self.assertTrue(receipt['verified'])
