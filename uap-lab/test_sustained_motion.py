import json
import tempfile
import unittest
from pathlib import Path
from sustained_motion import SustainedMotion

class SustainedRecordingTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.recorder=SustainedMotion(self.root)

    def frame(self,t,x=None,positive=False):
        objects=[] if x is None else [dict(box=[x,10,3,3],suggested_label='anomalous' if positive else 'not_anomalous')]
        self.recorder.update('run-1',dict(pts_seconds=t,received_epoch=1000+t,sequence=int(10*t),observations=objects),'v1')

    def test_continuous_pass_survives_restart_and_blink(self):
        for t in range(20,150):
            if t==68:self.recorder=SustainedMotion(self.root)
            self.frame(t,None if 80<=t<83 else 5*t,t==20)
        self.frame(159)
        events=list((self.root/'run-1/events').glob('*.json'))
        self.assertEqual(len(events),1)
        record=json.loads(events[0].read_text())
        self.assertEqual((record['start_pts'],record['end_pts']),(10,159))
        self.assertFalse((self.root/'run-1/open-sustained.json').exists())

    def test_fixed_light_and_negative_motion_do_not_record(self):
        for t in range(60):self.frame(t,10+t%2,True)
        for t in range(60,120):self.frame(t,200+5*t)
        self.assertIsNone(self.recorder.event)

    def test_export_retains_one_complete_session_and_links_review_to_it(self):
        from unittest.mock import patch
        from sustained_motion import playback_url
        from spool_export import export_event
        import lab
        run=self.root/'run-1'
        for t in range(20,116):self.frame(t,3*t,t==20)
        self.frame(126)
        segments=[]
        for t in range(130):
            name=f'segment-{t:09}.mkv'
            (run/name).write_bytes(b'original')
            segments.append(dict(file=name,start=t,end=t+1,bytes=8))
        (run/'segments-index.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in segments))
        path,=(run/'events').glob('*.json')
        e=json.loads(path.read_text())
        station=self.root/'station'
        (station/'sessions').mkdir(parents=True)
        with patch.object(lab,'STATION',station),patch.object(lab,'DATA',self.root):
            export_event(self.root,path)
        folder=station/'sessions'/e['session_id']
        manifest=json.loads((folder/'manifest.json').read_text())
        self.assertEqual(manifest['capture_origin'],'sustained_motion')
        self.assertFalse(manifest['window_limited'])
        self.assertEqual(manifest['elapsed_seconds'],115)
        self.assertEqual(len(list((folder/'buffer-segments').glob('*.mkv'))),115)
        (folder/'video.mp4').touch()
        url=playback_url(self.root,station,dict(generation='run-1',pts_seconds=115))
        self.assertIn(e['session_id'],url)
