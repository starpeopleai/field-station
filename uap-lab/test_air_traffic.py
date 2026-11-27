import json, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
import air_traffic as a

class TrafficTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);a.base(self.root).mkdir();self.now=time.time()
 def tearDown(self):self.temp.cleanup()
 def test_focal_setting_and_projection(self):
  first=a.field_of_view({'camera_focal_length_mm':100,'camera_elevation_deg':0})
  self.assertAlmostEqual(first['horizontal_deg'],12.724,places=2)
  self.assertAlmostEqual(first['azimuth_span_deg'],first['horizontal_deg'])
  self.assertLess(a.field_of_view({'camera_focal_length_mm':400})['horizontal_deg'],3.2)
  self.assertGreater(a.field_of_view({'camera_elevation_deg':43})['azimuth_span_deg'],first['horizontal_deg'])
  self.assertEqual(a.field_of_view({'camera_elevation_deg':90})['azimuth_span_deg'],360)
  a.save_settings(self.root,{'address':a.DEFAULT['address'],'camera_focal_length_mm':400})
  self.assertEqual(a.live(self.root)['camera_fov']['focal_length_mm'],400)
  before=a.settings(self.root)
  for value in [0,401,True,float('nan')]:
   with self.assertRaises(ValueError):a.save_settings(self.root,{'address':a.DEFAULT['address'],'camera_focal_length_mm':value})
   self.assertEqual(a.settings(self.root),before)
 def test_locked_history_does_not_block_live_snapshot(self):
  import sqlite3
  with patch.object(a,'fetch_json',return_value=self.payload()),patch.object(a,'database',side_effect=sqlite3.OperationalError('database is locked')):
   result=a.collect_once(self.root)
  self.assertEqual(a.live(self.root)['status'],'available')
  self.assertEqual(a.live(self.root)['sampled_epoch'],result['sampled_epoch'])
  self.assertEqual(a.read(a.base(self.root)/'history-status.json')['status'],'retrying')
 def test_terrain_cache_tracks_center_and_overrides(self):
  with patch.object(a,'fetch_json',return_value={'value':'200.5'}):a.refresh_elevation(self.root)
  self.assertEqual(a.station_elevation(self.root)['camera_altitude_ft'],200.5)
  c=dict(a.DEFAULT,latitude=38)
  self.assertEqual(a.station_elevation(self.root,c)['status'],'unknown')
  c.update(station_altitude_ft=100,camera_height_ft=12)
  self.assertEqual(a.station_elevation(self.root,c)['camera_altitude_ft'],112)
 def test_invalid_ground_settings_preserve_state(self):
  before=a.settings(self.root)
  for value in [float('nan'),True,40000]:
   with self.assertRaises(ValueError):a.save_settings(self.root,dict(address=a.DEFAULT['address'],station_altitude_ft=value))
   self.assertEqual(a.settings(self.root),before)
 def test_bad_terrain_is_not_sea_level(self):
  with patch.object(a,'fetch_json',return_value={'value':'-1000000'}):a.refresh_elevation(self.root)
  self.assertIsNone(a.station_elevation(self.root)['camera_altitude_ft'])
 def test_terrain_fallback_converts_meters_to_feet(self):
  with patch.object(a,'fetch_json',side_effect=[OSError('timeout'),{'elevation':[100]}]):a.refresh_elevation(self.root)
  result=a.station_elevation(self.root)
  self.assertAlmostEqual(result['camera_altitude_ft'],100/.3048)
  self.assertEqual(result['source'],'Copernicus / Open-Meteo')
 def payload(self,**kw):
  row=dict(hex='abc123',flight='UAL123 ',lat=37.4,lon=-122.18,alt_baro=10000,gs=200,track=0,seen_pos=1);row.update(kw)
  return dict(now=self.now*1000,ac=[row])
 def snapshot(self):return a.normalize(self.payload(),a.DEFAULT,self.now)
 def test_poll_cadence_and_single_auxiliary_worker(self):
  clock=[0.0];attempts=[]
  class Stop(Exception):pass
  def collect(root):attempts.append(clock[0]);clock[0]+=4;return {'aircraft':[]}
  def sleep(seconds):
   clock[0]+=seconds
   if len(attempts)>=3:raise Stop()
  with patch.object(a.time,'monotonic',side_effect=lambda:clock[0]),patch.object(a.time,'sleep',side_effect=sleep),patch.object(a,'collect_once',side_effect=collect),patch.object(a,'ThreadPoolExecutor') as executor:
   executor.return_value.__enter__.return_value.submit.return_value.done.return_value=False
   with self.assertRaises(Stop):a.poll(self.root)
   self.assertEqual(attempts,[0,15,30])
   self.assertEqual(executor.return_value.__enter__.return_value.submit.call_count,1)
 def test_poll_preserves_rate_limit_backoff(self):
  clock=[0.0];attempts=[]
  class Stop(Exception):pass
  def collect(root):
   attempts.append(clock[0])
   if len(attempts)==1:raise a.HTTPError('test',429,'rate limited',{'Retry-After':'60'},None)
   return {'aircraft':[]}
  def sleep(seconds):
   clock[0]+=seconds
   if len(attempts)>=2:raise Stop()
  with patch.object(a.time,'monotonic',side_effect=lambda:clock[0]),patch.object(a.time,'sleep',side_effect=sleep),patch.object(a,'collect_once',side_effect=collect),patch.object(a,'ThreadPoolExecutor'):
   with self.assertRaises(Stop):a.poll(self.root)
  self.assertEqual(attempts,[0,60])
 def test_outside_default_radius_excluded(self):self.assertEqual(a.normalize(self.payload(lat=37.7),a.DEFAULT,self.now)['aircraft'],[])
 def test_radius_only_update_needs_no_geocoding(self):
  with patch.object(a,'fetch_json',side_effect=AssertionError('network')):
   result=a.save_settings(self.root,{'address':a.DEFAULT['address'],'radius_miles':25})
  self.assertAlmostEqual(result['radius_nm']*1.150779448,25)
 def test_invalid_radius_preserves_settings(self):
  for radius in [0,101,'10',True,float('nan')]:
   with self.assertRaises(ValueError):a.save_settings(self.root,{'address':a.DEFAULT['address'],'radius_miles':radius})
  self.assertEqual(a.settings(self.root),a.DEFAULT)
 def test_landmark_add_remove_preserves_center(self):
  result=a.save_settings(self.root,dict(action='add_landmark',address='Stanford Dish',label='Dish'))
  self.assertEqual(result['address'],a.DEFAULT['address']);self.assertEqual(result['landmarks'][0]['label'],'Dish')
  result=a.save_settings(self.root,dict(action='remove_landmark',id=result['landmarks'][0]['id']))
  self.assertEqual(result['landmarks'],[])
 def test_landmark_lookup_and_duplicate(self):
  with patch.object(a,'fetch_json',return_value=[dict(lat='37.42',lon='-122.18',display_name='Campus')]):
   result=a.save_settings(self.root,dict(action='add_landmark',address='Campus, Stanford'))
  self.assertEqual(result['landmarks'][0]['label'],'Campus')
  with self.assertRaises(ValueError):a.save_settings(self.root,dict(action='add_landmark',address='Campus, Stanford'))
 def test_failed_landmark_preserves_settings(self):
  with patch.object(a,'fetch_json',return_value=[]):
   with self.assertRaises(ValueError):a.save_settings(self.root,dict(action='add_landmark',address='Missing place'))
  self.assertEqual(a.settings(self.root),a.DEFAULT)
 def test_landmarks_visible_when_feed_unavailable(self):
  a.save_settings(self.root,dict(action='add_landmark',address='Stanford Dish'))
  self.assertEqual(len(a.live(self.root)['landmarks']),1)
 def test_landmarks_visible_when_feed_stale(self):
  a.store(self.root,self.snapshot());a.save_settings(self.root,dict(action='add_landmark',address='Stanford Dish'))
  result=a.live(self.root,self.now+40);self.assertEqual(result['status'],'stale');self.assertEqual(len(result['landmarks']),1)
 def test_center_save_preserves_landmarks(self):
  a.save_settings(self.root,dict(action='add_landmark',address='Stanford Dish'))
  result=a.save_settings(self.root,dict(address=a.DEFAULT['address'],radius_miles=20))
  self.assertEqual(len(result['landmarks']),1)
 def test_azimuth_zero_is_north_and_can_clear(self):
  result=a.save_settings(self.root,dict(address=a.DEFAULT['address'],camera_azimuth_deg=0))
  self.assertEqual(result['camera_azimuth_deg'],0);self.assertEqual(a.live(self.root)['camera_azimuth_deg'],0)
  result=a.save_settings(self.root,dict(address=a.DEFAULT['address'],camera_azimuth_deg=None));self.assertIsNone(result['camera_azimuth_deg'])
 def test_invalid_azimuth_cannot_change_settings(self):
  for azimuth in [-1,360,'90',True,float('nan')]:
   with self.assertRaises(ValueError):a.save_settings(self.root,dict(address=a.DEFAULT['address'],camera_azimuth_deg=azimuth))
  self.assertEqual(a.settings(self.root),a.DEFAULT)
 def test_azimuth_update_preserves_landmarks_and_radius(self):
  a.save_settings(self.root,dict(action='add_landmark',address='Stanford Dish'))
  result=a.save_settings(self.root,dict(address=a.DEFAULT['address'],camera_azimuth_deg=123.4))
  self.assertEqual(len(result['landmarks']),1);self.assertEqual(result['radius_nm'],a.DEFAULT['radius_nm'])
 def test_elevation_roundtrip_and_clear(self):
  for value in [0,45.5,90,-90,None]:
   result=a.save_settings(self.root,dict(address=a.DEFAULT['address'],camera_elevation_deg=value))
   self.assertEqual(result['camera_elevation_deg'],value);self.assertEqual(a.live(self.root)['camera_elevation_deg'],value)
 def test_invalid_elevation_is_atomic(self):
  for value in [-91,91,True,'45',float('nan')]:
   with self.assertRaises(ValueError):a.save_settings(self.root,dict(address=a.DEFAULT['address'],camera_azimuth_deg=90,camera_elevation_deg=value))
  self.assertEqual(a.settings(self.root),a.DEFAULT)
 def test_elevation_preserves_other_settings(self):
  a.save_settings(self.root,dict(address=a.DEFAULT['address'],camera_azimuth_deg=180,radius_miles=20))
  a.save_settings(self.root,dict(action='add_landmark',address='Stanford Dish'))
  result=a.save_settings(self.root,dict(address=a.DEFAULT['address'],camera_elevation_deg=45))
  self.assertEqual(result['camera_azimuth_deg'],180);self.assertEqual(len(result['landmarks']),1);self.assertAlmostEqual(result['radius_nm']*1.150779448,20)
 def test_live_includes_full_resolved_address(self):
  config=dict(a.DEFAULT,resolved_address='Example trail, City, County, State, Country')
  a.atomic(a.base(self.root)/'settings.json',config)
  self.assertEqual(a.live(self.root)['center']['resolved_address'],config['resolved_address'])
  a.store(self.root,self.snapshot())
  self.assertEqual(a.live(self.root)['center']['resolved_address'],config['resolved_address'])
 def test_radar_county_is_structured_and_private(self):
  response={'address':{'county':'San Mateo County','country_code':'us','ISO3166-2-lvl4':'US-CA','road':'SECRET'}}
  with patch.object(a,'fetch_json',return_value=response):a.refresh_region(self.root)
  self.assertEqual(a.public_region(self.root),dict(status='known',county='San Mateo County',state='CA',country='US'))
  self.assertNotIn('SECRET',(a.base(self.root)/'radar-region.json').read_text())
  with patch.object(a,'fetch_json',side_effect=AssertionError('cached')):a.refresh_region(self.root)
 def test_moved_radar_does_not_use_old_county(self):
  a.atomic(a.base(self.root)/'radar-region.json',dict(status='known',center_key=a.region_key(a.DEFAULT),county='Old',state='CA',country='US'))
  a.atomic(a.base(self.root)/'settings.json',dict(a.DEFAULT,latitude=40))
  self.assertEqual(a.public_region(self.root)['status'],'unknown')
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
