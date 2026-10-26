"""Native desktop import queue. Encoding is added in the next milestone."""

from pathlib import Path
import sys
from threading import Event

from PySide6.QtCore import QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHeaderView, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QTableView, QVBoxLayout, QWidget,
)

from mediashrink.importing import MEDIA_EXTENSIONS, ScanReport, destination_conflict, scan_media
from mediashrink.queue_model import QueueModel, format_size


class ImportThread(QThread):
    batch_ready = Signal(object)
    report_ready = Signal(object)

    def __init__(self, selections, known_paths, destination, parent=None):
        super().__init__(parent)
        self.selections = selections
        self.known_paths = known_paths
        self.destination = destination
        self.cancel = Event()

    def run(self):
        try:
            report = scan_media(
                self.selections, self.known_paths, self.cancel,
                self.batch_ready.emit, self.destination,
            )
        except Exception as exc:
            report = ScanReport()
            report.error(f"Import failed: {exc}")
        self.report_ready.emit(report)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MediaShrink")
        self.resize(1000, 680)
        self.setMinimumSize(640, 500)
        self.worker: ImportThread | None = None
        self.destination: Path | None = None
        self.source_folders: set[Path] = set()
        self.close_pending = False

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
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
            "Development preview: add files or folders to prepare your queue. "
            "Compression is coming in the next milestones."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        actions = QHBoxLayout()
        self.add_files_button = QPushButton("Add files")
        self.add_files_button.clicked.connect(self.choose_files)
        self.add_folder_button = QPushButton("Add folder")
        self.add_folder_button.clicked.connect(self.choose_folder)
        self.clear_button = QPushButton("Clear queue")
        self.clear_button.clicked.connect(self.clear_queue)
        self.cancel_button = QPushButton("Cancel import")
        self.cancel_button.clicked.connect(self.cancel_import)
        self.cancel_button.setEnabled(False)
        for button in (self.add_files_button, self.add_folder_button, self.clear_button, self.cancel_button):
            actions.addWidget(button)
        layout.addLayout(actions)

        output = QHBoxLayout()
        self.destination_button = QPushButton("Choose output folder")
        self.destination_button.clicked.connect(self.choose_destination)
        self.destination_label = QLabel("No output folder selected")
        self.destination_label.setWordWrap(True)
        self.destination_label.setTextFormat(Qt.TextFormat.PlainText)
        output.addWidget(self.destination_button)
        output.addWidget(self.destination_label, 1)
        layout.addLayout(output)

        self.queue = QueueModel(self)
        self.table = QTableView()
        self.table.setAccessibleName("Compression queue")
        self.table.setModel(self.queue)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 100)
        self.table.verticalHeader().hide()
        layout.addWidget(self.table, 1)
        self.summary = QLabel("No files added yet")
        layout.addWidget(self.summary)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAccessibleName("Import in progress")
        self.progress.hide()
        layout.addWidget(self.progress)
        self.details = QLabel("")
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.details)
        self.start_button = QPushButton("Compression coming soon")
        self.start_button.setEnabled(False)
        layout.addWidget(self.start_button)
        safety = QLabel("Import only reads file information. Originals are never changed.")
        safety.setWordWrap(True)
        layout.addWidget(safety)
        self.setCentralWidget(content)
        self.statusBar().showMessage("Ready to import · Compression unavailable")

    @Slot()
    def choose_files(self):
        extensions = MEDIA_EXTENSIONS | {extension.upper() for extension in MEDIA_EXTENSIONS}
        patterns = " ".join(f"*{extension}" for extension in sorted(extensions))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add photos and videos", "", f"Media ({patterns});;All files (*)"
        )
        if paths:
            self.import_paths([Path(path) for path in paths])

    @Slot()
    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Add folder (including subfolders)")
        if path:
            self.import_paths([Path(path)])

    def import_paths(self, paths: list[Path]) -> None:
        if self.worker is not None or not paths:
            return
        self.details.clear()
        self.worker = ImportThread(
            paths, {item.path for item in self.queue.files}, self.destination, self
        )
        self.worker.batch_ready.connect(self.add_batch)
        self.worker.report_ready.connect(self.show_report)
        self.worker.finished.connect(self.import_finished)
        self.set_importing(True)
        self.statusBar().showMessage("Scanning folders…")
        self.worker.start()

    def set_importing(self, busy: bool):
        for button in (self.add_files_button, self.add_folder_button, self.clear_button, self.destination_button):
            button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.progress.setVisible(busy)

    @Slot(object)
    def add_batch(self, files):
        self.queue.append(files)
        self.summary.setText(f"{self.queue.rowCount():,} files · {format_size(self.queue.total_bytes)} original")

    @Slot(object)
    def show_report(self, report: ScanReport):
        self.source_folders.update(report.source_folders)
        state = "Import cancelled; discovered files kept" if report.cancelled else "Import complete"
        message = (
            f"{state}: {report.added:,} added · {report.duplicates:,} duplicate paths · "
            f"{report.unsupported:,} unsupported · {report.symlinks:,} symlinks skipped · "
            f"{report.error_count:,} errors"
        )
        if report.errors:
            message += "\n" + "\n".join(report.errors[:3])
            if report.error_count > 3:
                message += "\nAdditional errors omitted; check folder access and try again."
        self.details.setText(message)
        self.statusBar().showMessage("Import cancelled" if report.cancelled else "Import complete")

    @Slot()
    def import_finished(self):
        worker = self.worker
        self.worker = None
        self.set_importing(False)
        if worker is not None:
            worker.deleteLater()
        if self.close_pending:
            self.close()

    @Slot()
    def cancel_import(self):
        if self.worker is not None:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage("Cancelling import…")

    @Slot()
    def clear_queue(self):
        if self.worker is not None:
            return
        self.queue.clear()
        self.source_folders.clear()
        self.summary.setText("No files added yet")
        self.details.clear()
        self.statusBar().showMessage("Queue cleared")

    def set_destination(self, path: Path) -> bool:
        """Select an existing separate folder without creating or writing anything."""
        if self.worker is not None:
            return False
        try:
            destination = path.resolve(strict=True)
            if not destination.is_dir():
                raise ValueError("Choose an existing folder.")
            if destination_conflict(destination, self.source_folders, (item.path for item in self.queue.files)):
                raise ValueError("Choose an output folder separate from your imported folders and source files.")
        except (OSError, RuntimeError, ValueError) as exc:
            self.details.setText(str(exc))
            return False
        self.destination = destination
        self.destination_label.setText(str(destination))
        self.details.clear()
        return True

    @Slot()
    def choose_destination(self):
        path = QFileDialog.getExistingDirectory(self, "Choose separate output folder")
        if path and not self.set_destination(Path(path)):
            QMessageBox.warning(self, "Output folder unavailable", self.details.text())

    def closeEvent(self, event):
        if self.worker is not None:
            self.close_pending = True
            self.cancel_import()
            event.ignore()
        else:
            event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MediaShrink")
    app.setOrganizationName("MediaShrink")
    window = MainWindow()
    window.show()
    return app.exec()
