import unittest
import cv2
import numpy as np
from formation_overlay import locate, segments


class FormationTests(unittest.TestCase):
    def test_seed_center_and_missing_light(self):
        image = np.full((80, 120), 14, dtype=np.uint8)
        cv2.circle(image, (70, 20), 2, 100, -1)
        self.assertEqual(locate(image, (67, 24), 12), [70, 20])
        self.assertIsNone(locate(image, (85, 20), 8))
        image[19, 68] = 255
        self.assertIsNone(locate(image, (2, 2), 10))

    def test_missing_vertex_breaks_its_edges(self):
        a,b,c=(10,10),(30,25),(40,50)
        self.assertEqual(segments([a,None,b,c]), [(b,c),(c,a)])
