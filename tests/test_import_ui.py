"""Offscreen worker lifecycle and queue integration checks."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mediashrink.app import MainWindow
from mediashrink.importing import ScanReport


class ImportUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.media = self.root / 'phone'
        self.media.mkdir()
        self.image = self.media / 'photo.JPG'
        self.image.write_bytes(b'synthetic')
        self.output = self.root / 'compressed'
        self.output.mkdir()
        self.window = MainWindow()
        self.window.show()

    def tearDown(self):
        self.window.cancel_import()
        self.until(lambda: self.window.worker is None)
        self.window.close()
        self.temp.cleanup()

    def until(self, condition):
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(condition(), 'Timed out waiting for background import')

    def test_import_repeat_clear_and_destination(self):
        self.window.import_paths([self.media])
        self.assertFalse(self.window.add_files_button.isEnabled())
        self.until(lambda: self.window.worker is None)
        self.assertTrue(self.window.add_files_button.isEnabled())
        self.assertEqual(self.window.queue.rowCount(), 1)
        self.assertEqual(self.window.queue.total_bytes, 9)
        self.assertIn('9.0 B', self.window.summary.text())
        self.window.import_paths([self.image])
        self.until(lambda: self.window.worker is None)
        self.assertEqual(self.window.queue.rowCount(), 1)
        self.assertIn('1 duplicate paths', self.window.details.text())
        self.assertFalse(self.window.set_destination(self.media))
        self.assertTrue(self.window.set_destination(self.output))
        alias = self.root / 'alias'
        alias.symlink_to(self.media, target_is_directory=True)
        self.assertFalse(self.window.set_destination(alias))
        self.assertEqual(self.window.destination, self.output)
        self.window.clear_queue()
        self.assertEqual(self.window.queue.rowCount(), 0)
        self.assertEqual(self.window.source_folders, set())
        self.assertFalse(self.window.start_button.isEnabled())

    def test_destination_first_rejects_import_overlap(self):
        self.assertTrue(self.window.set_destination(self.media))
        self.window.import_paths([self.media])
        self.until(lambda: self.window.worker is None)
        self.assertEqual(self.window.queue.rowCount(), 0)
        self.assertIn('overlaps', self.window.details.text())
        self.assertFalse(self.window.set_destination(self.root / 'missing'))
        self.assertFalse(self.window.set_destination(self.image))

    def test_ui_ticks_and_cancels_without_blocking(self):
        started = Event()
        def slow_scan(selections, known, cancel, emit, destination):
            started.set()
            cancel.wait(3)
            return ScanReport(cancelled=cancel.is_set())
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(5)
        with patch('mediashrink.app.scan_media', side_effect=slow_scan):
            self.window.import_paths([self.media])
            self.until(started.is_set)
            self.until(lambda: len(ticks) >= 3)
            self.window.cancel_import()
            self.until(lambda: self.window.worker is None)
        timer.stop()
        self.assertIn('cancelled', self.window.details.text())

    def test_worker_failure_restores_controls_and_allows_retry(self):
        with patch('mediashrink.app.scan_media', side_effect=RuntimeError('synthetic failure')):
            self.window.import_paths([self.media])
            self.until(lambda: self.window.worker is None)
        self.assertIn('synthetic failure', self.window.details.text())
        self.assertTrue(self.window.add_files_button.isEnabled())
        self.window.import_paths([self.media])
        self.until(lambda: self.window.worker is None)
        self.assertEqual(self.window.queue.rowCount(), 1)

    def test_close_waits_for_worker_cancellation(self):
        started = Event()
        def slow_scan(selections, known, cancel, emit, destination):
            started.set()
            cancel.wait(3)
            return ScanReport(cancelled=cancel.is_set())
        with patch('mediashrink.app.scan_media', side_effect=slow_scan):
            self.window.import_paths([self.media])
            self.until(started.is_set)
            self.window.close()
            self.assertTrue(self.window.close_pending)
            self.until(lambda: self.window.worker is None)
            self.assertFalse(self.window.isVisible())


if __name__ == '__main__':
    unittest.main()
