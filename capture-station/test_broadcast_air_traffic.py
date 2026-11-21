import unittest
from broadcast_air_traffic import AircraftOverlay

class AircraftOverlayTests(unittest.TestCase):
 def setUp(self):
  self.overlay=AircraftOverlay('/not-mounted');self.overlay.config=dict(latitude=37.4083,longitude=-122.179,radius_nm=15/1.150779448)
  self.overlay.data=dict(provider='adsb.lol',license='ODbL-1.0',sampled_epoch=1000,center=self.overlay.config,radius_nm=self.overlay.config['radius_nm'],aircraft=[dict(latitude=37.42,longitude=-122.17,track_deg=45)])
 def test_private_provider_is_never_broadcast(self):
  self.overlay.data['provider']='adsb.fi';self.assertEqual(self.overlay.reports(1010)[0],[])
 def test_stale_reports_disappear(self):self.assertFalse(self.overlay.reports(1211)[2])
 def test_center_change_hides_old_reports(self):
  self.overlay.config=dict(self.overlay.config,latitude=38);self.assertFalse(self.overlay.reports(1010)[2])
 def test_landmarks_and_addresses_do_not_change_render(self):
  before=self.overlay.render((255,255,255,255),1010).tobytes()
  self.overlay.config['landmarks']=[dict(label='SECRET HOME',address='PRIVATE ADDRESS',latitude=37.41,longitude=-122.17)]
  self.overlay.config['address']='PRIVATE ADDRESS';self.overlay.data['landmarks']=self.overlay.config['landmarks']
  self.assertEqual(before,self.overlay.render((255,255,255,255),1010).tobytes())
 def test_camera_azimuth_changes_render(self):
  before=self.overlay.render((255,255,255,255),1010).tobytes();self.overlay.config['camera_azimuth_deg']=90
  self.assertNotEqual(before,self.overlay.render((255,255,255,255),1010).tobytes())
 def test_east_up_rotates_north_left_and_east_top(self):
  from unittest.mock import patch
  from PIL import ImageDraw
  original=ImageDraw.ImageDraw.text;labels={}
  def capture(draw,xy,text,*args,**kwargs):
   if text in ('N','E','S','W'):labels[text]=xy
   return original(draw,xy,text,*args,**kwargs)
  self.overlay.config['camera_azimuth_deg']=90
  with patch.object(ImageDraw.ImageDraw,'text',capture):self.overlay.render((255,255,255,255),1010)
  self.assertAlmostEqual(labels['N'][0],20);self.assertAlmostEqual(labels['N'][1],252)
  self.assertAlmostEqual(labels['E'][0],230);self.assertAlmostEqual(labels['E'][1],42)
 def test_aircraft_render_changes_pixels(self):
  before=self.overlay.render((255,255,255,255),1010).tobytes();self.overlay.data['aircraft']=[]
  self.assertNotEqual(before,self.overlay.render((255,255,255,255),1010).tobytes())
if __name__=='__main__':unittest.main()
