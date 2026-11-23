import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import detection_zone
import station_settings


class ZoneTests(unittest.TestCase):
    def test_center_filter_scales_to_native_size(self):
        boxes=[[0,0,20,20],[40,20,20,20],[80,20,10,10]]
        self.assertEqual(detection_zone.filter_boxes(boxes,(60,100),[.25,.25,.75,.75]),[boxes[1]])
        self.assertEqual(detection_zone.filter_boxes(boxes,(60,100),[0,0,1,1]),boxes)
    def test_setting_survives_disable_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp, patch('station_location.location_at',return_value={}):
            root=Path(tmp)
            self.assertFalse(station_settings.settings(root)['zone_enabled'])
            bounds=[.2,.3,.8,.9]
            station_settings.update(root,dict(zone_enabled=True,zone_bounds=bounds))
            station_settings.update(root,dict(zone_enabled=False))
            self.assertEqual(station_settings.settings(root)['zone_bounds'],bounds)
            for bad in ([0,0,2,1],[0,0,0,1],[0,0,float('nan'),1]):
                with self.assertRaises(ValueError):station_settings.update(root,dict(zone_bounds=bad))
