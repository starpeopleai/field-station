import unittest
from datetime import datetime, timedelta

from launch_indicator import label


class LaunchClockTests(unittest.TestCase):
    def setUp(self):
        self.launch = datetime.now().replace(hour=23, minute=30, second=0, microsecond=0)
        self.row = {"net": self.launch.astimezone().isoformat(), "net_precision": {"abbrev": "MIN"},
                    "status": {"id": 6}}

    def test_elapsed_across_midnight_and_expiry(self):
        for seconds, expected in [(0, "Launch -00:00"), (60, "Launch -00:01"),
                                  (7199, "Launch -01:59"), (7200, "No launch scheduled")]:
            with self.subTest(seconds=seconds):
                self.assertEqual(label([self.row], self.launch.timestamp()+seconds)["text"], expected)

    def test_pending_and_next_launch(self):
        later = dict(self.row, net=(self.launch + timedelta(hours=3)).astimezone().isoformat(),
                     status={"id": 1})
        pending = dict(self.row, status={"id": 1})
        self.assertEqual(label([pending], self.launch.timestamp()+60)["state"], "pending")
        self.assertEqual(label([self.row, later], self.launch.timestamp()+7200)["text"], "Launch in 01:00")

    def test_most_recent_confirmed_launch_wins(self):
        second = dict(self.row, net=(self.launch + timedelta(minutes=15)).astimezone().isoformat())
        self.assertEqual(label([self.row, second], self.launch.timestamp()+1800)["text"], "Launch -00:15")
