import unittest
from formation_prediction import predict


class PredictionTests(unittest.TestCase):
    def test_tracks_relative_velocity_through_shared_camera_motion(self):
        rows=[]
        for tick in range(81):
            t=tick/10
            ref=[50+t*t,30+t]
            top=[ref[0]+2*t,ref[1]-7] if t<4 else None
            rows.append([t,[ref,top]])
        predicted=predict(rows)
        self.assertIsNone(predicted[39][1])
        self.assertEqual(predicted[-1],[None,[130,31]])
        self.assertIsNone(predict(rows+[[9,[None,None]]])[-1][1])

    def test_stops_at_horizon_and_yields_to_observations(self):
        rows=[[i/10, [[i,0],[i,5] if i<=50 or i==135 else None]] for i in range(136)]
        estimates=predict(rows)
        self.assertEqual(estimates[130][1],[130,5])
        self.assertIsNone(estimates[131][1])
        self.assertIsNone(estimates[135][1])
