import http.server
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from app import App
from usability import friendly_error, newer_release, VERSION


class ReleaseTests(unittest.TestCase):
    def test_stable_versions_only(self):
        for tag in [VERSION, 'v1.0.0', 'bad', 'v1.2.0-beta', None]:
            self.assertIsNone(newer_release({'tag_name': tag}))
        self.assertEqual(newer_release({'tag_name': 'v1.10.0'}), 'v1.10.0')
        self.assertIsNone(newer_release({'tag_name': 'v2.0.0', 'prerelease': True}))
        self.assertIsNone(newer_release({'tag_name': 'v2.0.0', 'draft': True}))

    def test_friendly_errors(self):
        for error, expected in [('Connection timed out', 'internet connection'),
                                ('Permission denied', 'save folder'), ('No space left', 'drive is full'),
                                ('ERROR 429', 'limiting requests'), ('HTTP 404', 'could not be found'),
                                ('FFmpeg postprocessing error', 'conversion failed'),
                                ('unexpected failure', 'technical details')]:
            self.assertIn(expected, friendly_error(error))


class UpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        class Handler(http.server.BaseHTTPRequestHandler):
            payload = {'tag_name': 'v2.0.0'}
            status = 200
            def do_GET(self):
                self.send_response(type(self).status)
                self.end_headers()
                self.wfile.write(json.dumps(type(self).payload).encode())
            def log_message(self, *_):
                pass
        cls.handler = Handler
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.window = App(settings=QSettings(str(Path(self.temp.name) / 'settings.ini'), QSettings.Format.IniFormat),
                          state_path=Path(self.temp.name) / 'queue.json', enable_updates=False)
        self.api = patch('app.UPDATE_API', f'http://127.0.0.1:{self.server.server_port}/latest')
        self.api.start()
        self.handler.status = 200

    def tearDown(self):
        self.window.close()
        self.api.stop()
        self.temp.cleanup()

    def wait_reply(self):
        deadline = time.monotonic() + 5
        while self.window.update_reply:
            self.qt.processEvents()
            time.sleep(.01)
            self.assertLess(time.monotonic(), deadline)

    def test_new_release_shows_banner_without_popup(self):
        self.handler.payload = {'tag_name': 'v2.0.0'}
        with patch('app.QMessageBox.information') as popup:
            self.window.check_for_updates(False)
            self.wait_reply()
        self.assertFalse(self.window.update_notice.isHidden())
        self.assertIn('v2.0.0', self.window.update_notice.text())
        popup.assert_not_called()

    def test_same_version_is_silent(self):
        self.handler.payload = {'tag_name': VERSION}
        with patch('app.QMessageBox.information') as popup:
            self.window.check_for_updates(False)
            self.wait_reply()
        popup.assert_not_called()
        self.assertTrue(self.window.update_notice.isHidden())

    def test_failed_background_check_is_silent(self):
        self.handler.status = 503
        with patch('app.QMessageBox.information') as popup:
            self.window.check_for_updates(False)
            self.wait_reply()
        popup.assert_not_called()
        self.assertTrue(self.window.check_update_action.isEnabled())

    def test_manual_failed_check_explains_next_step(self):
        self.handler.status = 503
        with patch('app.QMessageBox.information') as popup:
            self.window.check_for_updates(True)
            self.wait_reply()
        self.assertEqual(popup.call_args.args[1], 'Could not check for updates')

    def test_bad_response_does_not_crash(self):
        self.handler.payload = ['unexpected']
        with patch('app.QMessageBox.information') as popup:
            self.window.check_for_updates(True)
            self.wait_reply()
        self.assertEqual(popup.call_count, 1)

    def test_disabling_automatic_updates_skips_request(self):
        self.window.settings.setValue('automatic_updates', False)
        with patch.object(self.window.network, 'get') as request:
            self.window.check_for_updates(False)
        request.assert_not_called()
