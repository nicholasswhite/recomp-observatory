"""Exercise folder-picker HTTP boundaries against an isolated loopback server."""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import server


class FolderRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.port_patch = patch.object(server, 'PORT', cls.port)
        cls.log_patch = patch.object(server.Handler, 'log_message')
        cls.port_patch.start()
        cls.log_patch.start()
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.thread.join(timeout=3)
        cls.httpd.server_close()
        cls.log_patch.stop()
        cls.port_patch.stop()

    def setUp(self):
        self.fixture = {'path': 'C:\\Fixture', 'parent': 'C:\\',
                        'folders': [{'name': 'Example', 'path': 'C:\\Fixture\\Example'}],
                        'shortcuts': [{'name': 'Fixture', 'path': 'C:\\Fixture'}], 'truncated': False}
        self.browser_patch = patch.object(server, 'browse_folders', return_value=self.fixture)
        self.browser = self.browser_patch.start()
        self.addCleanup(self.browser_patch.stop)

    def request(self, method='POST', path='/api/folders', data=None, headers=None):
        request_headers = {}
        body = None
        if method == 'POST':
            request_headers = {'Origin': f'http://127.0.0.1:{self.port}', 'Content-Type': 'application/json'}
            body = json.dumps(data if data is not None else {'path': 'C:\\Fixture'})
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_same_origin_json_returns_helper_result(self):
        status, headers, body = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), self.fixture)
        self.assertEqual(headers['Content-Type'], 'application/json')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.browser.assert_called_once_with('C:\\Fixture')

    def test_missing_path_uses_helper_default(self):
        status, _, body = self.request(data={})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), self.fixture)
        self.browser.assert_called_once_with(None)

    def test_foreign_origin_or_cross_site_request_cannot_enumerate(self):
        for headers in ({'Origin': 'https://foreign.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(headers=headers):
                status, _, _ = self.request(headers=headers)
                self.assertEqual(status, 403)
                self.browser.assert_not_called()

    def test_non_loopback_host_cannot_enumerate(self):
        status, _, _ = self.request(headers={'Host': f'foreign.example:{self.port}'})
        self.assertEqual(status, 403)
        self.browser.assert_not_called()

    def test_non_json_request_cannot_enumerate(self):
        status, _, _ = self.request(headers={'Content-Type': 'text/plain'})
        self.assertEqual(status, 415)
        self.browser.assert_not_called()

    def test_invalid_path_returns_actionable_bad_request(self):
        self.browser.side_effect = ValueError('This folder does not exist')
        status, headers, body = self.request(data={'path': 'C:\\MissingFixture'})
        self.assertEqual(status, 400)
        self.assertEqual(headers['Content-Type'], 'application/json')
        self.assertEqual(json.loads(body), {'error': 'This folder does not exist'})
        self.browser.assert_called_once_with('C:\\MissingFixture')

    def test_picker_script_is_served_without_folder_enumeration(self):
        status, headers, body = self.request(method='GET', path='/folders.js')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'text/javascript; charset=utf-8')
        self.assertTrue(body)
        self.browser.assert_not_called()

    def test_workspace_file_is_confined_to_ignored_work_tree(self):
        accepted = server.workspace_file('work/secondary-workspace.json')
        self.assertTrue(accepted.is_relative_to((server.BASE/'work').resolve()))
        for candidate in (server.BASE/'README.md', server.BASE.parent/'outside.json'):
            with self.subTest(candidate=candidate), self.assertRaisesRegex(ValueError, 'work folder'):
                server.workspace_file(candidate)


if __name__ == '__main__':
    unittest.main()
