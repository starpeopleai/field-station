import hashlib
import tempfile
import unittest
from pathlib import Path
import av
import numpy as np

from temporal_rgb import source_window


class SourceTest(unittest.TestCase):
    def test_exact_rgb_and_variable_timestamps_with_no_gif(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            pixels=np.zeros((32,32,3),dtype='uint8')
            with av.open(str(root/'video.mkv'),'w') as out:
                stream=out.add_stream('ffv1',rate=10)
                stream.width=32;stream.height=32;stream.pix_fmt='bgr0'
                for i in range(12):
                    pixels[:]=[103+i,114,109]
                    f=av.VideoFrame.from_ndarray(pixels,format='rgb24')
                    f.pts=i if i<7 else i+1
                    for packet in stream.encode(f):out.mux(packet)
                for packet in stream.encode():out.mux(packet)
            with av.open(str(root/'video.mkv')) as inp:
                originals=[(f.time,f.to_image().convert('RGB')) for f in inp.decode(video=0)]
            t,image=originals[5]
            (root/'frames').mkdir()
            still=root/'frames/original.png'
            image.save(still)
            annotation=dict(annotation_id='target',bounds=[10,10,8,8])
            r=dict(pixel_sha256=hashlib.sha256(b'8x8:RGB:'+image.crop((10,10,18,18)).tobytes()).hexdigest())
            row=dict(width=32,height=32,original=dict(file='original.png',sha256=hashlib.sha256(still.read_bytes()).hexdigest()),
                     source_pts_seconds=t,frame=5,motion=dict(annotation_id='target',crop_xywh=[6,6,16,16],sample_offsets_seconds=[-.1,0,.3]))
            frames,times,roi,source=source_window(root,row,annotation,r)
            self.assertEqual(source,'video.mkv')
            np.testing.assert_allclose(times,[-.1,0,.3])
            np.testing.assert_array_equal(frames[1],np.array(image.crop((6,6,22,22))))
            self.assertEqual(frames[:,0,0,0].tolist(),[107,108,110])
            row['motion']['sample_offsets_seconds']=[-.1,0,.2]
            with self.assertRaisesRegex(ValueError,'incomplete'):
                source_window(root,row,annotation,r)
