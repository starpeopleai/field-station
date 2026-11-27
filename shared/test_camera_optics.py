import math,unittest
from camera_optics import aircraft_view,field_of_view
class OpticsTests(unittest.TestCase):
 def setUp(self):self.config=dict(latitude=0,longitude=0,camera_azimuth_deg=0,camera_elevation_deg=0,camera_focal_length_mm=100)
 def test_horizontal_and_vertical_rejection(self):
  center=dict(latitude=.01,longitude=0,altitude_ft=0)
  self.assertTrue(aircraft_view(self.config,center,0)['in_fov'])
  self.assertFalse(aircraft_view(self.config,dict(center,longitude=.01),0)['in_fov'])
  self.assertFalse(aircraft_view(self.config,dict(center,altitude_ft=1000),0)['in_fov'])
 def test_station_height_and_unknown(self):
  a=dict(latitude=.01,longitude=0,altitude_ft=1000)
  self.assertTrue(aircraft_view(self.config,a,1000)['in_fov'])
  self.assertIsNone(aircraft_view(self.config,a,None)['in_fov'])
  self.assertIsNone(aircraft_view(self.config,dict(a,altitude_ft=None),1000)['in_fov'])
 def test_wraparound_and_narrowing(self):
  self.config['camera_azimuth_deg']=359
  a=dict(latitude=.1,longitude=.004,altitude_ft=0)
  self.assertTrue(aircraft_view(self.config,a,0)['in_fov'])
  self.config['camera_focal_length_mm']=400
  self.assertFalse(aircraft_view(self.config,a,0)['in_fov'])
 def test_elevation_and_behind_camera(self):
  self.config['camera_elevation_deg']=30
  distance=3440.065*math.radians(.01)*6076.11549
  a=dict(latitude=.01,longitude=0,altitude_ft=distance*math.tan(math.radians(30)))
  self.assertTrue(aircraft_view(self.config,a,0)['in_fov'])
  self.assertFalse(aircraft_view(self.config,dict(a,latitude=-.01),0)['in_fov'])
 def test_missing_orientation(self):
  self.config['camera_elevation_deg']=None
  self.assertIsNone(aircraft_view(self.config,dict(latitude=.01,longitude=0,altitude_ft=100),0)['in_fov'])
if __name__=='__main__':unittest.main()
