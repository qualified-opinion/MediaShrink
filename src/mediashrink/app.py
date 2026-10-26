"""Native desktop window: import queue, batch compression and results."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import sys
from threading import Event, Lock

from PySide6.QtCore import QThread, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QHeaderView, QHBoxLayout, QLabel,
    QFrame, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox, QTableView, QVBoxLayout,
    QWidget,
)

from mediashrink.importing import MEDIA_EXTENSIONS, ScanReport, destination_conflict, scan_media
from mediashrink.queue_model import QueueModel, format_size
from mediashrink.video import compress, Cancelled, choose_encoder
from mediashrink.presets import PRESETS, ENCODERS
from mediashrink.photo import compress as compress_photo
from mediashrink.importing import VIDEO_EXTENSIONS
from mediashrink.report import ResultsLog, previous_results


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


def photo_workers():
    """Photos processed at once: libvips already uses threads within a photo, so about half the cores."""
    return max(1, min(4, (os.cpu_count() or 2) // 2))


class MediaThread(QThread):
    update = Signal(int, str, str)
    encoder_status = Signal(str)
    batch_status = Signal(object)
    overall_progress = Signal(int)
    log_status = Signal(str)

    def __init__(self, files, destination, roots, parent=None, preset="Balanced", encoder="libx264",
                 skip_done=False, min_saving=0.0, workers=None):
        self.preset, self.encoder, self.skip_done, self.min_saving = preset, encoder, skip_done, min_saving
        super().__init__(parent)
        self.files, self.destination, self.roots = files, destination, roots
        self.workers = workers or photo_workers()
        self.cancel = Event()
        self.lock = Lock()  # Photo jobs finish on several threads at once.
        self.earlier = {}
        self.log = None
        self.totals = {}
        self.started = set()
        self.running = {}  # Row -> fraction done, for overall progress.
        self.shown_progress = 0

    def earlier_output(self, item, size):
        """Output path ('' for no reduction) from an earlier batch into this folder, or None."""
        found = self.earlier.get(str(item.path))
        if found is None or found[0] != size or (found[1] and not Path(found[1]).is_file()):
            return None
        return found[1]

    def run(self):
        self.totals = dict(total=len(self.files), completed=0, saved=0, skipped=0, previous=0, unsupported=0,
                           failed=0, cancelled=0, original_bytes=0, output_bytes=0)
        self.batch_status.emit(self.totals.copy())
        if self.skip_done:
            self.earlier = previous_results(self.destination)
        try:
            self.log = ResultsLog(self.destination)
            self.log_status.emit(f"Results log: {self.log.path}")
        except (OSError, RuntimeError) as exc:
            self.log_status.emit(f"Results log could not be created: {exc}")
        videos = [(row, item) for row, item in enumerate(self.files) if item.path.suffix.lower() in VIDEO_EXTENSIONS]
        photos = [(row, item) for row, item in enumerate(self.files) if item.path.suffix.lower() not in VIDEO_EXTENSIONS]
        try:
            # Photos first, several at once; each one runs in its own libvips subprocess.
            # Results are recorded here, on the batch thread, as each photo finishes.
            with ThreadPoolExecutor(self.workers) as pool:
                jobs = [pool.submit(self.process, row, item, compress_photo, {}) for row, item in photos]
                for job in as_completed(jobs):
                    if (outcome := job.result()) is not None:
                        self.finish(*outcome)
            if videos and not self.cancel.is_set():
                try:
                    encoder = choose_encoder(self.encoder, self.preset, self.cancel, self.encoder_status.emit)
                except Cancelled:
                    return
                # Videos one at a time: FFmpeg already uses every core.
                for row, item in videos:
                    if (outcome := self.process(row, item, compress, {"encoder": encoder})) is not None:
                        self.finish(*outcome)
        finally:
            if self.log is not None:
                for row, item in enumerate(self.files):
                    if row not in self.started:
                        self.log.add(item.path, "Not processed", original=item.size)
                self.log.close()
                if self.log.error is not None:
                    self.log_status.emit(f"Results log incomplete ({self.log.error}): {self.log.path}")

    def process(self, row, item, engine, options):
        """Compress one file; return the arguments for finish(), or None if cancelled before starting."""
        if self.cancel.is_set():
            return None
        with self.lock:
            self.started.add(row)
        size = None
        try:
            self.update.emit(row, "Checking media", "—")
            size = item.path.stat().st_size
            earlier = self.earlier_output(item, size)
            if earlier is not None:
                # Re-running a batch must not create numbered duplicates of finished files.
                return (row, "previous", f"Already done: {earlier or 'no size reduction'}",
                        (item.path, "Already done", "Found in an earlier results log", size,
                         earlier or None, Path(earlier).stat().st_size if earlier else None))
            target, output_size = engine(item.path, self.destination, self.roots, self.cancel,
                                         lambda percent: self.report_progress(row, percent), preset=self.preset,
                                         folder=item.folder, min_saving=self.min_saving, **options)
            if target:
                return (row, "saved", f"Saved: {target}", (item.path, "Saved", "", size, target, output_size),
                        format_size(output_size), (size, output_size))
            saving = 100 * (size - output_size) / size if 0 < output_size < size else 0
            reason = f"only {saving:.1f}% smaller" if saving else "no size reduction"
            return (row, "skipped", f"Skipped: {reason}", (item.path, "No reduction", reason, size))
        except Cancelled:
            self.cancel.set()  # Stop the rest of the batch, including queued photo jobs.
            return (row, "cancelled", "Cancelled", (item.path, "Cancelled", "", size))
        except Exception as exc:
            unsupported = str(exc).startswith("Skipped")
            return (row, "unsupported" if unsupported else "failed", str(exc),
                    (item.path, "Skipped" if unsupported else "Failed", str(exc), size))

    def finish(self, row, kind, status, log_row, shown_size="—", saved=None):
        with self.lock:
            self.totals[kind] += 1
            if kind != "cancelled":
                self.totals["completed"] += 1
            if saved:
                self.totals["original_bytes"] += saved[0]
                self.totals["output_bytes"] += saved[1]
            self.running.pop(row, None)
            if self.log is not None:
                self.log.add(*log_row)
            totals = self.totals.copy()
        self.update.emit(row, status, shown_size)
        self.batch_status.emit(totals)
        self.emit_progress()

    def report_progress(self, row, percent):
        with self.lock:
            self.running[row] = min(percent, 99) / 100
        self.update.emit(row, f"Compressing {percent}%", "—")
        self.emit_progress()

    def emit_progress(self):
        with self.lock:
            done = self.totals["completed"] + sum(self.running.values())
            # Parallel jobs report out of order; never let the bar move backwards.
            self.shown_progress = max(self.shown_progress, int(done / max(1, self.totals["total"]) * 100))
            value = self.shown_progress
        self.overall_progress.emit(value)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MediaShrink")
        self.resize(1000, 740)
        self.setMinimumSize(640, 560)
        self.worker: ImportThread | MediaThread | None = None
        self.destination: Path | None = None
        self.source_folders: set[Path] = set()
        self.close_pending = False
        self.setAcceptDrops(True)

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
        notice = QLabel(
            "Photo and video compression, entirely on your computer. Add files or folders, or drag them "
            "onto this window; compressed copies go to a separate output folder."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        settings = QHBoxLayout()
        self.quality = QComboBox()
        self.quality.addItems(list(PRESETS))
        self.quality.setCurrentText('Balanced')
        self.encoder = QComboBox()
        self.encoder.addItems(list(ENCODERS))
        settings.addWidget(QLabel('Quality'))
        settings.addWidget(self.quality)
        settings.addWidget(QLabel('Video encoder'))
        settings.addWidget(self.encoder)
        self.min_saving = QSpinBox()
        self.min_saving.setRange(0, 50)
        self.min_saving.setValue(5)
        self.min_saving.setSuffix('% smaller')
        self.min_saving.setAccessibleName('Minimum saving')
        self.min_saving.setToolTip('Outputs that save less than this are discarded; re-compressing for a tiny '
                                   'saving costs quality for little gain.')
        settings.addStretch(1)
        keep = QHBoxLayout()
        keep.addWidget(QLabel('Keep outputs at least'))
        keep.addWidget(self.min_saving)
        self.skip_done = QCheckBox('Skip files already compressed into this output folder')
        self.skip_done.setChecked(True)
        self.skip_done.setToolTip('Uses the results logs in the output folder. Untick to compress them again.')
        keep.addSpacing(16)
        keep.addWidget(self.skip_done)
        keep.addStretch(1)
        layout.addLayout(settings)
        layout.addLayout(keep)
        self.encoder_note = QLabel('Photos use CPU. PNG/WebP remain lossless for every preset.')
        self.encoder_note.setWordWrap(True)
        self.encoder_note.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.encoder_note)
        actions = QHBoxLayout()
        self.add_files_button = QPushButton("Add files")
        self.add_files_button.clicked.connect(self.choose_files)
        self.add_folder_button = QPushButton("Add folder")
        self.add_folder_button.clicked.connect(self.choose_folder)
        self.clear_button = QPushButton("Clear queue")
        self.clear_button.clicked.connect(self.clear_queue)
        self.remove_button = QPushButton("Remove selected")
        self.remove_button.clicked.connect(self.remove_selected)
        self.remove_button.setEnabled(False)
        self.cancel_button = QPushButton("Cancel import")
        self.cancel_button.clicked.connect(self.cancel_import)
        self.cancel_button.setEnabled(False)
        for button in (self.add_files_button, self.add_folder_button, self.remove_button, self.clear_button,
                       self.cancel_button):
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
        self.open_output_button = QPushButton("Open output folder")
        self.open_output_button.clicked.connect(self.open_output)
        self.open_output_button.setEnabled(False)
        output.addWidget(self.open_output_button)
        layout.addLayout(output)

        self.queue = QueueModel(self)
        self.table = QTableView()
        self.table.setAccessibleName("Compression queue")
        self.table.setModel(self.queue)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)  # Keep file names visible in long paths.
        self.table.setMinimumHeight(150)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self.table.horizontalHeader()
        for column, mode in enumerate((QHeaderView.ResizeMode.Stretch, QHeaderView.ResizeMode.ResizeToContents,
                                       QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch)):
            header.setSectionResizeMode(column, mode)
        self.table.verticalHeader().hide()
        self.table.selectionModel().selectionChanged.connect(lambda *_: self.refresh_start())
        QShortcut(QKeySequence.StandardKey.Delete, self.table, self.remove_selected)
        layout.addWidget(self.table, 1)
        self.summary = QLabel("No files added yet")
        layout.addWidget(self.summary)
        self.batch_summary = QLabel("")
        self.batch_summary.setWordWrap(True)
        layout.addWidget(self.batch_summary)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAccessibleName("Import in progress")
        self.progress.hide()
        layout.addWidget(self.progress)
        self.details = QLabel("")
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.details)
        self.start_button = QPushButton("Compress photos and videos")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_compression)
        layout.addWidget(self.start_button)
        safety = QLabel("Import only reads file information. Originals are never changed.")
        safety.setWordWrap(True)
        layout.addWidget(safety)
        # Long wrapped paths can outgrow small windows; scroll rather than overlap.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        self.setCentralWidget(scroll)
        self.statusBar().showMessage("Ready to import")

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
        self.quality.setEnabled(not busy)
        self.encoder.setEnabled(not busy)
        self.skip_done.setEnabled(not busy)
        self.min_saving.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        if not busy:
            self.cancel_button.setText("Cancel import")
        if busy:
            self.remove_button.setEnabled(False)
            self.progress.setRange(0, 0)
            self.progress.setAccessibleName("Import in progress")
        self.progress.setVisible(busy)

    @Slot(object)
    def add_batch(self, files):
        self.queue.append(files)
        self.summary.setText(f"{self.queue.rowCount():,} files · {format_size(self.queue.total_bytes)} original")
        self.refresh_start()

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
        self.refresh_start()
        if worker is not None:
            worker.deleteLater()
        if self.close_pending:
            self.close()

    @Slot()
    def cancel_import(self):
        if self.worker is not None:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage("Cancelling…")

    @Slot()
    def clear_queue(self):
        if self.worker is not None:
            return
        self.batch_summary.clear()
        self.queue.clear()
        self.refresh_start()
        self.source_folders.clear()
        self.summary.setText("No files added yet")
        self.details.clear()
        self.encoder_note.setText('Photos use CPU. PNG/WebP remain lossless for every preset.')
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
        self.refresh_start()
        self.details.clear()
        return True

    @Slot()
    def choose_destination(self):
        path = QFileDialog.getExistingDirectory(self, "Choose separate output folder")
        if path and not self.set_destination(Path(path)):
            QMessageBox.warning(self, "Output folder unavailable", self.details.text())

    @Slot()
    def remove_selected(self):
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        if self.worker is not None or not rows:
            return
        self.queue.remove(rows)
        self.summary.setText(f"{self.queue.rowCount():,} files · {format_size(self.queue.total_bytes)} original"
                             if self.queue.files else "No files added yet")
        self.statusBar().showMessage(f"Removed {len(rows):,} files from the queue")
        self.refresh_start()

    @Slot()
    def open_output(self):
        if self.destination is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.destination)))

    def dragEnterEvent(self, event):
        if self.worker is None and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if self.worker is None and paths:
            event.acceptProposedAction()
            self.import_paths(paths)

    def refresh_start(self):
        idle = self.worker is None
        self.start_button.setText("Compress photos and videos")
        self.start_button.setEnabled(idle and self.destination is not None and bool(self.queue.files))
        self.remove_button.setEnabled(idle and self.table.selectionModel().hasSelection())
        self.open_output_button.setEnabled(self.destination is not None)

    @Slot()
    def start_compression(self):
        if self.worker is not None or self.destination is None:
            return
        self.worker = MediaThread(list(self.queue.files), self.destination, set(self.source_folders), self,
                                  self.quality.currentText(), ENCODERS[self.encoder.currentText()],
                                  self.skip_done.isChecked(), self.min_saving.value() / 100)
        self.encoder_note.setText("Photos use CPU; video encoder: " + self.encoder.currentText())
        self.worker.encoder_status.connect(self.encoder_note.setText)
        self.details.clear()
        self.worker.log_status.connect(self.details.setText)
        self.queue.results.clear()
        if self.queue.rowCount():
            self.queue.dataChanged.emit(self.queue.index(0, 0), self.queue.index(self.queue.rowCount()-1, 3))
        self.worker.batch_status.connect(self.show_batch)
        self.worker.overall_progress.connect(self.progress.setValue)
        self.worker.update.connect(self.video_update)
        self.worker.finished.connect(self.import_finished)
        self.set_importing(True)
        self.start_button.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setAccessibleName("Compression progress")
        self.cancel_button.setText("Cancel processing")
        self.worker.start()

    @Slot(object)
    def show_batch(self, totals):
        reduction = totals['original_bytes'] - totals['output_bytes']
        percent = 100 * reduction / totals['original_bytes'] if totals['original_bytes'] else 0
        pending = totals['total'] - totals['completed'] - totals['cancelled']
        self.batch_summary.setText(
            f"{totals['completed']}/{totals['total']} processed · {totals['saved']} saved · "
            f"{totals['skipped']} no reduction · {totals['previous']} already done\n"
            f"{totals['unsupported']} unsupported · {totals['failed']} failed · "
            f"{totals['cancelled']} cancelled · {pending} not processed\n"
            f"Saved outputs are {format_size(reduction)} smaller ({percent:.1f}%). Originals remain on disk."
        )

    @Slot(int, str, str)
    def video_update(self, row, status, size):
        self.queue.results[row] = (status, size)
        self.queue.dataChanged.emit(self.queue.index(row, 0), self.queue.index(row, 3))
        self.statusBar().showMessage(f"File {row + 1}/{self.queue.rowCount()}: {status}")

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
