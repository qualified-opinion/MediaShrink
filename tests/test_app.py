"""Headless startup regression checks; no media or GPU is needed."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from mediashrink.app import MainWindow


class StartupTest(unittest.TestCase):
    def test_window_starts_and_closes(self):
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        window.show()
        self.assertTrue(window.isVisible())
        QTimer.singleShot(0, app.quit)
        self.assertEqual(app.exec(), 0)
        self.assertEqual(window.queue.rowCount(), 0)
        self.assertFalse(window.start_button.isEnabled())
        window.close()
        self.assertFalse(window.isVisible())


if __name__ == "__main__":
    unittest.main()
