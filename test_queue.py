"""Queue interaction regression tests; uses short local workers, no downloads."""
import sys
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from app import App, STYLE
from downloader import parse_links


class QueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setStyleSheet(STYLE)

    def setUp(self):
        self.callback_errors = []
        self.exception_hook = patch('sys.excepthook', side_effect=lambda *error: self.callback_errors.append(error))
        self.exception_hook.start()
        self.temp = tempfile.TemporaryDirectory()
        self.window = App(settings=QSettings(str(Path(self.temp.name) / 'settings.ini'), QSettings.Format.IniFormat),
                          state_path=Path(self.temp.name) / 'queue.json', enable_updates=False)
        self.window.folder.setText(self.temp.name)
        self.started = []
        def command(url, *args):
            self.started.append(url)
            return [sys.executable, '-c', 'import time; time.sleep(.15)']
        self.mock = patch('app.download_command', side_effect=command)
        self.mock.start()
        self.preview_patch = patch('app.preview_command', return_value=[
            sys.executable, '-c',
            'import json; print(json.dumps({"title":"Preview title","uploader":"Artist","duration":114}))'])
        self.preview_mock = self.preview_patch.start()

    def tearDown(self):
        self.window.cancel_all()
        self.wait_idle()
        self.window.close()
        self.mock.stop()
        self.preview_patch.stop()
        self.temp.cleanup()
        self.exception_hook.stop()
        self.assertEqual(self.callback_errors, [], 'Unhandled exception in a Qt callback')

    def wait_idle(self):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            self.qt.processEvents()
            if not self.window.active and not any(i.state == 'Waiting to download' for i in self.window.items):
                self.qt.processEvents()
                return
            time.sleep(.01)
        self.fail('Queue did not become idle')

    def add(self, name, now=False):
        self.window.links.setPlainText('https://youtu.be/' + name)
        (self.window.download_now_button if now else self.window.add_button).click()
        return self.window.items[-1]

    def test_individual_download_leaves_other_cards_queued(self):
        first = self.add('first')
        second = self.add('second')
        self.assertEqual(self.started, [])
        second.download_button.click()
        self.wait_idle()
        self.assertEqual(first.state, 'Queued')
        self.assertEqual(second.state, 'Complete')
        self.assertEqual(self.started, [second.url])

    def test_download_now_and_existing_duplicate(self):
        first = self.add('first')
        second = self.add('second', now=True)
        self.wait_idle()
        self.assertEqual(first.state, 'Queued')
        self.assertEqual(second.state, 'Complete')
        self.add('first', now=True)
        self.wait_idle()
        self.assertEqual(len(self.window.items), 2)
        self.assertEqual(first.state, 'Complete')

    def test_batch_excludes_later_additions_and_cancelled_items(self):
        first = self.add('first')
        second = self.add('second')
        cancelled = self.add('cancelled')
        cancelled.cancel_button.click()
        self.window.download_all_button.click()
        later = self.add('later')
        self.wait_idle()
        self.assertEqual(self.started, [first.url, second.url])
        self.assertEqual(later.state, 'Queued')
        self.assertEqual(cancelled.state, 'Cancelled')
        cancelled.download_button.click()
        self.wait_idle()
        self.assertEqual(cancelled.state, 'Complete')
        self.assertEqual(later.state, 'Queued')

    def test_cancel_scheduled_card(self):
        first = self.add('first')
        second = self.add('second')
        self.window.download_all_button.click()
        self.assertEqual(second.state, 'Waiting to download')
        second.cancel_button.click()
        self.wait_idle()
        self.assertEqual(self.started, [first.url])
        self.assertEqual(second.state, 'Cancelled')

    def wait_previews(self):
        deadline = time.monotonic() + 8
        while self.window.preview_process or self.window.preview_pending:
            self.qt.processEvents()
            if time.monotonic() >= deadline:
                self.fail('Preview lookup did not finish')
            time.sleep(.01)

    def test_preview_populates_without_downloading(self):
        card = self.add('preview')
        self.wait_previews()
        self.assertEqual(card.title.text(), 'Preview title')
        self.assertIn('Artist · 1:54', card.subtitle.text())
        self.assertEqual(card.state, 'Queued')
        self.assertTrue(card.download_button.isEnabled())
        self.assertEqual(self.started, [])
        self.assertIsNone(card.file)

    def test_preview_failure_does_not_block_download(self):
        self.preview_mock.return_value = [sys.executable, '-c', 'raise SystemExit(1)']
        card = self.add('unavailable')
        self.wait_previews()
        self.assertIn('preview unavailable', card.status.text())
        card.download_button.click()
        self.wait_idle()
        self.assertEqual(card.state, 'Complete')

    def test_removed_card_ignores_late_preview(self):
        self.preview_mock.return_value = [sys.executable, '-c', 'import time; time.sleep(5)']
        card = self.add('removed')
        self.window.remove(card)
        self.wait_previews()
        self.assertEqual(self.window.items, [])
        self.assertEqual(self.started, [])

    def test_cancel_immediately_while_worker_starts(self):
        with patch('app.download_command', return_value=[sys.executable, '-c', 'import time; time.sleep(30)']):
            card = self.add('starting', now=True)
            card.cancel_button.click()
            self.wait_idle()
        self.assertEqual(card.state, 'Cancelled')
        self.assertFalse(card.remove_button.isHidden())

    def test_cancel_with_taskkill_unavailable(self):
        with patch('app.download_command', return_value=[sys.executable, '-c', 'import time; time.sleep(30)']):
            card = self.add('cancel-fallback', now=True)
            self.assertTrue(self.window.process.waitForStarted(3000))
            with patch('app.subprocess.Popen', side_effect=OSError('taskkill missing')):
                card.cancel_button.click()
                self.wait_idle()
        self.assertEqual(card.state, 'Cancelled')

    def test_failed_worker_start_continues_batch(self):
        first = self.add('bad-worker')
        second = self.add('good-worker')
        with patch('app.download_command', side_effect=[
            [str(Path(self.temp.name) / 'missing.exe')],
            [sys.executable, '-c', 'print("ok")'],
        ]):
            self.window.download_all_button.click()
            self.wait_idle()
        self.assertEqual(first.state, 'Failed')
        self.assertEqual(second.state, 'Complete')

    def test_bad_metadata_does_not_break_queue(self):
        card = self.add('metadata')
        for duration in [None, 'unknown', float('nan'), float('inf'), -3, {}]:
            card.metadata({'title': 'Title', 'duration': duration, 'thumbnail': {}})
            self.assertIn('Unknown duration', card.subtitle.text())
        card.metadata({'title': 'Long track', 'duration': 3661})
        self.assertIn('1:01:01', card.subtitle.text())
        self.window.active = card
        self.window.handle_line('APP_META:[]')
        self.window.active = None
        self.assertIn('Metadata could not be displayed', self.window.log.toPlainText())

    def test_close_stops_preview_and_active_download(self):
        self.preview_mock.return_value = [sys.executable, '-c', 'import time; time.sleep(30)']
        self.add('preview-only')
        with patch('app.download_command', return_value=[sys.executable, '-c', 'import time; time.sleep(30)']):
            card = self.add('active', now=True)
            self.window.show()
            self.qt.processEvents()
            self.window.close()
            self.wait_idle()
            self.wait_previews()
        self.assertEqual(card.state, 'Cancelled')
        self.assertIsNone(self.window.process)
        self.assertIsNone(self.window.preview_process)
        self.assertFalse(self.window.isVisible())

    def test_remove_twice_is_safe_and_keeps_files(self):
        card = self.add('remove')
        output = Path(self.temp.name) / 'keep.mp3'
        output.write_bytes(b'keep')
        card.file = str(output)
        card.cancel_button.click()
        card.remove_button.click()
        self.window.remove(card)
        self.assertEqual(output.read_bytes(), b'keep')
        self.assertEqual(self.window.items, [])

    def test_invalid_urls_are_rejected(self):
        for link in ['https://youtube.com/shorts/', 'https://youtube.com/live/',
                     'https://youtu.be/a/b', 'https://soundcloud.com/a/b/s-',
                     'https://youtube.com/playlist?list=123', 'https://youtube.com.evil.test/watch?v=123']:
            with self.subTest(link=link), self.assertRaises(ValueError):
                parse_links(link)

    def test_preview_failed_to_start_releases_next_lookup(self):
        self.preview_mock.side_effect = [[str(Path(self.temp.name) / 'missing.exe')],
            [sys.executable, '-c', 'print(\'{"title":"Second preview"}\')']]
        first = self.add('first-preview')
        second = self.add('second-preview')
        self.wait_previews()
        self.assertIn('unavailable', first.status.text())
        self.assertEqual(second.title.text(), 'Second preview')

    def test_preview_timeout_leaves_card_downloadable(self):
        self.window.preview_timeout_ms = 50
        self.preview_mock.return_value = [sys.executable, '-c', 'import time; time.sleep(30)']
        card = self.add('timeout')
        self.wait_previews()
        self.assertEqual(card.state, 'Queued')
        self.assertTrue(card.download_button.isEnabled())
        self.assertIn('unavailable', card.status.text())

    def reopen(self):
        settings, path = self.window.settings, self.window.state_path
        self.window.close()
        self.wait_idle()
        self.window = App(settings=settings, state_path=path, enable_updates=False)

    def test_saved_queue_restores_details_without_downloading(self):
        card = self.add('saved')
        self.wait_previews()
        self.reopen()
        self.assertEqual(len(self.window.items), 1)
        restored = self.window.items[0]
        self.assertEqual(restored.title.text(), 'Preview title')
        self.assertEqual(restored.quality, card.quality)
        self.assertEqual(restored.folder, Path(self.temp.name))
        self.assertEqual(restored.state, 'Queued')
        self.assertEqual(self.started, [])

    def test_close_active_download_restores_it_as_queued(self):
        with patch('app.download_command', return_value=[sys.executable, '-c', 'import time; time.sleep(30)']):
            self.add('interrupted', now=True)
            self.reopen()
        self.assertEqual(self.window.items[0].state, 'Queued')
        self.assertIsNone(self.window.process)

    def test_user_cancelled_and_failed_items_keep_retry_state(self):
        first = self.add('cancelled')
        second = self.add('failed')
        first.cancel_button.click()
        second.set_state('Failed')
        self.reopen()
        self.assertEqual([item.state for item in self.window.items], ['Cancelled', 'Failed'])
        self.assertTrue(all(item.download_button.text() == 'Retry' for item in self.window.items))

    def test_completed_and_removed_cards_are_not_restored(self):
        first = self.add('done', now=True)
        self.wait_idle()
        second = self.add('removed')
        self.window.remove(second)
        self.assertEqual(first.state, 'Complete')
        self.reopen()
        self.assertEqual(self.window.items, [])

    def test_corrupt_saved_queue_is_backed_up(self):
        self.window.close()
        self.window.state_path.write_text('{broken', encoding='utf-8')
        self.window = App(settings=self.window.settings, state_path=self.window.state_path, enable_updates=False)
        self.assertEqual(self.window.items, [])
        self.assertEqual(len(list(Path(self.temp.name).glob('queue.invalid-*.json'))), 1)

    def test_invalid_saved_entries_are_skipped(self):
        self.window.close()
        entries = [None, {'url': 'https://example.com', 'folder': self.temp.name, 'quality': '320 kbps MP3'},
                   {'url': 'https://youtu.be/valid', 'folder': self.temp.name, 'quality': '320 kbps MP3', 'metadata': {'title': 'Saved'}}]
        self.window.state_path.write_text(json.dumps({'version': 1, 'items': entries}), encoding='utf-8')
        self.window = App(settings=self.window.settings, state_path=self.window.state_path, enable_updates=False)
        self.assertEqual(len(self.window.items), 1)
        self.assertEqual(self.window.items[0].title.text(), 'Saved')

    def test_friendly_error_is_displayed_after_failure(self):
        with patch('app.download_command', return_value=[sys.executable, '-c', 'print("ERROR: Private video. Sign in required"); raise SystemExit(1)']):
            card = self.add('private', now=True)
            self.wait_idle()
        self.assertIn('requires sign-in', card.status.text())
        self.assertEqual(card.download_button.text(), 'Retry')

    def test_card_save_folder_can_be_changed_before_retry(self):
        card = self.add('new-folder')
        card.cancel_button.click()
        folder = Path(self.temp.name) / 'new'
        folder.mkdir()
        with patch('app.QFileDialog.getExistingDirectory', return_value=str(folder)):
            self.window.change_item_folder(card)
        self.reopen()
        self.assertEqual(self.window.items[0].folder, folder)


if __name__ == '__main__':
    unittest.main()
