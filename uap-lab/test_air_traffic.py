import json, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
import air_traffic as a

class TrafficTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);a.base(self.root).mkdir();self.now=time.time()
 def tearDown(self):self.temp.cleanup()
 def payload(self,**kw):
  row=dict(hex='abc123',flight='UAL123 ',lat=37.4,lon=-122.18,alt_baro=10000,gs=200,track=0,seen_pos=1);row.update(kw)
  return dict(now=self.now*1000,ac=[row])
 def snapshot(self):return a.normalize(self.payload(),a.DEFAULT,self.now)
 def test_outside_default_radius_excluded(self):self.assertEqual(a.normalize(self.payload(lat=37.7),a.DEFAULT,self.now)['aircraft'],[])
 def test_radius_only_update_needs_no_geocoding(self):
  with patch.object(a,'fetch_json',side_effect=AssertionError('network')):
   result=a.save_settings(self.root,{'address':a.DEFAULT['address'],'radius_miles':25})
  self.assertAlmostEqual(result['radius_nm']*1.150779448,25)
 def test_invalid_radius_preserves_settings(self):
  for radius in [0,101,'10',True,float('nan')]:
   with self.assertRaises(ValueError):a.save_settings(self.root,{'address':a.DEFAULT['address'],'radius_miles':radius})
  self.assertEqual(a.settings(self.root),a.DEFAULT)
 def test_ground_excluded(self):self.assertEqual(a.normalize(self.payload(alt_baro='ground'),a.DEFAULT,self.now)['aircraft'],[])
 def test_stale_position_excluded(self):self.assertEqual(a.normalize(self.payload(seen_pos=31),a.DEFAULT,self.now)['aircraft'],[])
 def test_missing_direction_is_not_north(self):
  s=a.normalize(self.payload(track=None),a.DEFAULT,self.now);self.assertNotIn('track_deg',s['aircraft'][0])
 def test_north_heading_retained(self):self.assertEqual(self.snapshot()['aircraft'][0]['track_deg'],0)
 def test_bad_coordinates_excluded(self):self.assertEqual(a.normalize(self.payload(lat=float('nan')),a.DEFAULT,self.now)['aircraft'],[])
 def test_old_feed_rejected(self):
  with self.assertRaises(ValueError):a.normalize(dict(now=(self.now-31)*1000,ac=[]),a.DEFAULT,self.now)
 def test_future_feed_rejected(self):
  with self.assertRaises(ValueError):a.normalize(dict(now=(self.now+60)*1000,ac=[]),a.DEFAULT,self.now)
 def test_historical_never_uses_current_feed(self):
  a.store(self.root,self.snapshot());self.assertEqual(a.at_time(self.root,self.now-60)['status'],'unavailable')
 def test_future_sample_not_used(self):
  a.store(self.root,self.snapshot());self.assertEqual(a.at_time(self.root,self.now-1)['status'],'unavailable')
 def test_context_saved_and_survives_history_removal(self):
  a.store(self.root,self.snapshot());folder=self.root/'event';folder.mkdir();event={'detected_epoch':self.now+1}
  a.attach(self.root,folder,event);(a.base(self.root)/'history.sqlite').unlink()
  self.assertEqual(a.detection(self.root,folder,event)['aircraft'][0]['flight'],'UAL123')
 def test_expired_live_has_no_stale_arrows(self):
  a.store(self.root,self.snapshot());self.assertEqual(a.live(self.root,self.now+31)['aircraft'],[])
 def test_live_center_change_does_not_show_old_aircraft(self):
  a.store(self.root,self.snapshot());a.atomic(a.base(self.root)/'settings.json',dict(a.DEFAULT,latitude=40))
  self.assertEqual(a.live(self.root,self.now)['status'],'waiting')
 def test_default_center_needs_no_geocoding(self):
  with patch.object(a,'fetch_json',side_effect=AssertionError('network')):
   self.assertEqual(a.save_settings(self.root,{'address':'Stanford Dish'})['latitude'],a.DEFAULT['latitude'])
 def test_failed_address_does_not_replace_center(self):
  with patch.object(a,'fetch_json',return_value=[]):
   with self.assertRaises(ValueError):a.save_settings(self.root,{'address':'invalid address somewhere'})
  self.assertEqual(a.settings(self.root),a.DEFAULT)
 def test_resolved_address_saved(self):
  with patch.object(a,'fetch_json',return_value=[{'lat':'40','lon':'-73','display_name':'Test location'}]):
   self.assertEqual(a.save_settings(self.root,{'address':'New test location'})['latitude'],40)
 def test_empty_coverage_is_valid_but_missing_is_unknown(self):
  self.assertEqual(a.at_time(self.root,self.now)['status'],'unavailable')
  a.store(self.root,a.normalize(dict(now=self.now*1000,ac=[]),a.DEFAULT,self.now))
  self.assertEqual(a.at_time(self.root,self.now)['status'],'available')
 def test_old_history_pruned(self):
  s=self.snapshot();s['sampled_epoch']=self.now-73*3600;a.store(self.root,s)
  with a.database(self.root) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0],0)
 def test_event_creation_survives_write_failure(self):
  with patch.object(a,'atomic',side_effect=OSError('full')):a.attach(self.root,self.root/'folder',{'detected_epoch':self.now})

if __name__=='__main__':unittest.main()
