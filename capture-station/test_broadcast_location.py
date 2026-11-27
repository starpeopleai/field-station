import unittest
from unittest.mock import patch,Mock
from PIL import Image
from broadcast_location import LocationOverlay

class LocationOverlayTests(unittest.TestCase):
    def test_broadcast_uses_shared_rf_ink(self):
        import os
        from broadcast_rf import OverlayPipe
        overlay=OverlayPipe('/not-mounted')
        try:
            overlay.watermark.location.draw=Mock()
            for bright,standby,ink in [(False,False,(255,255,255,255)),(True,False,(17,17,17,255)),(True,True,(155,201,140,255))]:
                overlay.renderer.bright=bright
                overlay.compose(Image.new('RGBA',(420,204)),standby)
                self.assertEqual(overlay.watermark.location.draw.call_args.kwargs['ink'],ink)
        finally:overlay.close();os.close(overlay.writer)
    def test_county_label_bottom_left_and_unknown_hidden(self):
        overlay=LocationOverlay('/not-mounted')
        known=dict(status='known',county='San Mateo County',state='CA',country='US')
        with patch('broadcast_location.public_region',return_value=known):
            canvas=Image.new('RGBA',(1280,720));overlay.draw(canvas,Image.new('RGB',(1280,720)))
        self.assertEqual(overlay.label,'San Mateo, CA, USA')
        left,top,right,bottom=canvas.getbbox()
        self.assertGreaterEqual(left,30);self.assertGreater(top,660)
        self.assertLess(right,400);self.assertLessEqual(bottom,694)
        overlay.checked=-float('inf')
        with patch('broadcast_location.public_region',return_value=dict(status='unknown')):
            canvas=Image.new('RGBA',(1280,720));overlay.draw(canvas)
        self.assertIsNone(canvas.getbbox())

if __name__=='__main__':unittest.main()
