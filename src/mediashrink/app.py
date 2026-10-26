"""Native desktop shell. Media processing is added in later milestones."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MediaShrink")
        self.resize(960, 600)
        self.setMinimumSize(640, 400)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("MediaShrink")
        font = title.font()
        font.setPointSize(24)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        subtitle = QLabel("Photo and video compression, entirely on your computer.")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        notice = QLabel(
            "Development preview: the desktop shell is ready. "
            "File import and compression are coming in the next milestones."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        self.queue = QTableWidget(0, 4)
        self.queue.setAccessibleName("Compression queue")
        self.queue.setHorizontalHeaderLabels(["File", "Original size", "Output size", "Status"])
        self.queue.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.queue.verticalHeader().hide()
        layout.addWidget(self.queue, 1)

        empty = QLabel("No files added yet")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(empty)

        self.start_button = QPushButton("Compression coming soon")
        self.start_button.setEnabled(False)
        self.start_button.setToolTip("File import and processing are not implemented in this preview.")
        layout.addWidget(self.start_button)

        safety = QLabel("Planned safety policy: save to a separate destination and keep your originals.")
        safety.setWordWrap(True)
        layout.addWidget(safety)
        self.setCentralWidget(content)
        self.statusBar().showMessage("Development preview · No media processing available")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MediaShrink")
    app.setOrganizationName("MediaShrink")
    window = MainWindow()
    window.show()
    return app.exec()
