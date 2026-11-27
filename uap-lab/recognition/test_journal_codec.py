import json,sqlite3,tempfile,unittest
from pathlib import Path
from journal_codec import encode_observations,decode_observations
from recognition_store import RecognitionStore

class CodecTests(unittest.TestCase):
 def test_lossless_and_legacy(self):
  rows=[dict(box=[1.2,3.4,5,6],shape_descriptor=[.12345]*64,suggested_label='anomalous',proposed_track_id=str(i)) for i in range(2500)]
  raw=json.dumps(rows);encoded=encode_observations(raw)
  self.assertIsInstance(encoded,bytes);self.assertLess(len(encoded),len(raw)/4)
  self.assertEqual(decode_observations(encoded),rows);self.assertEqual(decode_observations(raw),rows)
  self.assertEqual(encode_observations('[]'),'[]')
 def test_rollover_keeps_compressed_payload(self):
  with tempfile.TemporaryDirectory() as d:
   store=RecognitionStore(Path(d)/'results.sqlite');store.partition_bytes=1
   rows=[dict(box=[1,2,3,4],suggested_label='anomalous')]*100
   store.add('run',dict(sequence=1,pts_seconds=1,received_epoch=1,observations=rows),'model');store.commit(dict(last_sequence=1),None);store.close()
   db=sqlite3.connect(next((Path(d)/'partitions').glob('*.sqlite')))
   try:self.assertEqual(decode_observations(db.execute('SELECT observations FROM frames').fetchone()[0]),rows)
   finally:db.close()
