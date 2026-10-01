import http.client
import json
from pathlib import Path
import threading
import unittest

import browser_app as app

ROOT = Path(__file__).resolve().parents[1]


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.LocalServer(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(5)

    def request(self, path, data=None, headers=None, raw=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=30)
        defaults = {'Origin': self.server.origin, 'X-Session-Token': self.server.token,
                    'Content-Type': 'application/json'}
        defaults.update(headers or {})
        try:
            connection.request('POST' if data is not None or raw is not None else 'GET', path,
                               body=raw if raw is not None else json.dumps(data) if data is not None else None,
                               headers=defaults)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def example(self):
        return {name: (ROOT / 'examples' / f'{name}.csv').read_text(encoding='utf-8-sig')
                for name in ('config', 'problem')}

    def test_page_templates_and_manual(self):
        status, headers, body = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode(), body)
        self.assertNotIn(b'__SESSION_TOKEN__', body)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        self.assertEqual(self.request('/templates/config.csv')[2], (ROOT / 'examples/config.csv').read_bytes())
        self.assertEqual(self.request('/manual.pdf')[2][:5], b'%PDF-')
        self.assertEqual(json.loads(self.request('/api/example')[2]), self.example())

    def test_example_run_uses_solver_and_returns_two_outputs(self):
        status, _, body = self.request('/api/run', self.example())
        self.assertEqual(status, 200, body)
        data = json.loads(body)
        self.assertEqual(data['summary']['matches'], 3)
        self.assertEqual(data['summary']['unmatched_locals'], 1)
        self.assertEqual([(r['student_id'], r['local_id']) for r in data['pairs']],
                         [('S01', 'L01'), ('S02', 'L02'), ('S03', 'L03')])
        self.assertTrue(data['csv'].startswith('student_id,local_id,score'))
        self.assertIn('Status: SUCCESS', data['report'])
        self.assertIn('L04:', data['report'])

    def test_zero_matches_and_custom_settings(self):
        data = self.example()
        data['config'] = data['config'].replace('minimum_score,0,', 'minimum_score,1,')
        status, _, body = self.request('/api/run', data)
        self.assertEqual(status, 200, body)
        payload = json.loads(body)
        self.assertEqual(payload['pairs'], [])
        self.assertEqual(payload['summary']['unmatched_students'], 3)
        self.assertIn('No matches were selected', payload['report'])

    def test_invalid_csv_is_readable_error_without_old_results(self):
        data = self.example()
        data['problem'] = 'id,side\nS01,student\n'
        status, _, body = self.request('/api/run', data)
        self.assertEqual(status, 422)
        payload = json.loads(body)
        self.assertIn('column headings', payload['error'])
        self.assertNotIn('csv', payload)

    def test_only_local_page_can_submit(self):
        for headers in [{'Origin':'https://example.com'}, {'Origin':''},
                        {'X-Session-Token':'wrong'}, {'Host':'example.com'}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request('/api/run', self.example(), headers)[0], 403)
        self.assertEqual(self.request('/', headers={'Host':'example.com'})[0], 403)

    def test_request_validation_and_busy(self):
        self.assertEqual(self.request('/api/run', {})[0], 422)
        self.assertEqual(self.request('/api/run', raw='[')[0], 400)
        self.assertEqual(self.request('/api/run', raw='[]')[0], 400)
        self.assertEqual(self.request('/api/run', {}, {'Content-Type':'text/plain'})[0], 415)
        self.assertEqual(self.request('/api/run', {}, {'Content-Length':str(app.MAX_REQUEST_BYTES+1)})[0], 413)
        self.assertEqual(self.request('/missing')[0], 404)
        self.server.run_lock.acquire()
        try:
            self.assertEqual(self.request('/api/run', self.example())[0], 409)
            self.assertEqual(self.request('/api/stop', {})[0], 409)
        finally:
            self.server.run_lock.release()


if __name__ == '__main__':
    unittest.main()
