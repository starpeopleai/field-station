import unittest

from station_weather import conditions


class WeatherConditionsTests(unittest.TestCase):
    def test_missing_description_in_actual_ksfo_observation(self):
        raw = 'KSFO 220356Z 24007KT 2SM -RA BR SCT006 BKN018 OVC035 12/11 A3005 RMK AO2 RAB23'
        self.assertEqual(conditions(dict(rawMessage=raw)), 'Light rain, Mist')

    def test_reported_description_has_priority(self):
        self.assertEqual(conditions(dict(textDescription='Mostly cloudy', rawMessage='-RA')), 'Mostly cloudy')

    def test_remarks_and_trends_are_not_current_conditions(self):
        for raw in ['KSFO CLR RMK -RA', 'KSFO CLR TEMPO TSRA']:
            self.assertEqual(conditions(dict(rawMessage=raw)), 'Clear')

    def test_layer_fallback_and_missing_observation(self):
        self.assertEqual(conditions(dict(cloudLayers=[dict(amount='BKN')])), 'Mostly cloudy')
        self.assertEqual(conditions({}), '')
