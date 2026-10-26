"""Read-only table model; one row per candidate, without per-cell widgets."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from mediashrink.importing import MediaFile


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:,.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


class QueueModel(QAbstractTableModel):
    HEADERS = ("File", "Original size", "Output size", "Status")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.files: list[MediaFile] = []
        self.total_bytes = 0
        self.results = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.files)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.files):
            return None
        item = self.files[index.row()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return self.results.get(index.row(), (str(item.path), ""))[0]
        if role == Qt.ItemDataRole.DisplayRole:
            status, size = self.results.get(index.row(), ("Imported", "—"))
            return (str(item.path), format_size(item.size), size, status)[index.column()]
        return None

    def append(self, files: list[MediaFile]) -> None:
        if not files:
            return
        start = len(self.files)
        self.beginInsertRows(QModelIndex(), start, start + len(files) - 1)
        self.files.extend(files)
        self.total_bytes += sum(item.size for item in files)
        self.endInsertRows()

    def clear(self) -> None:
        self.beginResetModel()
        self.files.clear()
        self.total_bytes = 0
        self.results = {}
        self.endResetModel()
