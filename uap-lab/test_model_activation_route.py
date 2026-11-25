import fcntl
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from model_settings import read, save


class MakeLiveRouteTest(unittest.TestCase):
    def test_metrics_request_is_authenticated_and_queued_once(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, UAP_LAB_DATA=tmp):
            import server
            data_patch = patch.object(server.lab, 'DATA', Path(tmp))
            data_patch.start()
            self.addCleanup(data_patch.stop)
            root = Path(tmp) / 'model-inspector'
            policy = dict(version='a' * 64, thresholds={'anomalous': .6})
            model = dict(lane='experimental', version=policy['version'], available=True, policy=policy)
            save(root / 'models.json', {'models': [model]})
            payload = json.dumps(dict(lane=model['lane'], version=model['version'], revision=0))
            with server.StationHTTPServer(('127.0.0.1', 0), server.Handler) as httpd:
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                try:
                    def post(token):
                        connection = http.client.HTTPConnection('127.0.0.1', httpd.server_port, timeout=5)
                        try:
                            connection.request('POST', '/api/model-activate', payload,
                                                    {'Content-Type': 'application/json', 'X-Lab-Token': token})
                            response = connection.getresponse()
                            return response.status, json.loads(response.read())
                        finally:
                            connection.close()
                    self.assertEqual(post('invalid')[0], 403)
                    self.assertFalse((root / 'activation.json').exists())
                    status, job = post(server.TOKEN)
                    self.assertEqual(status, 202)
                    self.assertEqual(job['phase'], 'queued')
                    self.assertEqual(read(root / 'activation.json')['version'], model['version'])
                    self.assertEqual(post(server.TOKEN)[1]['id'], job['id'])
                finally:
                    httpd.shutdown()
                    thread.join()


    def test_deployment_lock_defers_delivery_without_losing_request(self):
        import model_activation
        with tempfile.TemporaryDirectory() as tmp, patch.object(model_activation, 'APP', Path(tmp)):
            app = Path(tmp)
            data = app / 'lab'
            job = dict(id='operator-request', phase='queued', lane='experimental')
            save(data / 'model-inspector/activation.json', job)
            (app / 'auto-training').mkdir()
            with (app / 'auto-training/deployment.lock').open('a') as maintenance:
                fcntl.flock(maintenance, fcntl.LOCK_EX)
                self.assertEqual(model_activation.next_request(data), {})
                waiting = read(data / 'model-inspector/activation.json')
                self.assertEqual(waiting['phase'], 'queued')
                self.assertIn('maintenance', waiting['error'])
            self.assertEqual(model_activation.next_request(data)['id'], job['id'])
