import unittest
from broadcast_rf import SpectrumOverlay

class SpectrumScaleTests(unittest.TestCase):
 def setUp(self):
  self.overlay=SpectrumOverlay.__new__(SpectrumOverlay);self.overlay.scales={}
 def test_flat_signal_keeps_twenty_db_range(self):
  self.assertEqual(self.overlay.display_scale('narrow',[-65]*8,0),(-75,-55))
 def test_expands_immediately_to_preserve_peak(self):
  self.overlay.display_scale('narrow',[-65],0)
  low,high=self.overlay.display_scale('narrow',[-65,-20],1)
  self.assertLess(low,-65);self.assertGreater(high,-20)
 def test_contracts_slowly_and_holds_stale_scale(self):
  self.overlay.display_scale('wide',[-90,-30],0)
  low,high=self.overlay.display_scale('wide',[-65],1)
  self.assertLess(low,-75);self.assertGreater(high,-55)
  self.assertEqual(self.overlay.display_scale('wide',[-10],20,False),(low,high))
 def test_bad_samples_and_independent_receivers(self):
  self.assertEqual(self.overlay.display_scale('wide',[None,float('nan'),True],0),(-100,-40))
  self.overlay.display_scale('narrow',[-65],0)
  self.assertEqual(self.overlay.display_scale('wide',[-30],1),(-40,-20))
