"""Read-only, cancellable discovery. Extensions are candidates, not codec validation."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import stat
from threading import Event
from typing import Callable, Iterable


VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv"})
PHOTO_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic"})
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | PHOTO_EXTENSIONS


@dataclass(frozen=True)
class MediaFile:
    path: Path
    size: int
    # Output subfolder mirroring the source layout, e.g. "DCIM/100APPLE"; empty for single files.
    folder: Path = Path()


@dataclass
class ScanReport:
    added: int = 0
    unsupported: int = 0
    duplicates: int = 0
    symlinks: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)
    source_folders: set[Path] = field(default_factory=set)
    cancelled: bool = False

    def error(self, message: str) -> None:
        self.error_count += 1
        if len(self.errors) < 20:
            self.errors.append(message)


def destination_conflict(
    destination: Path, source_folders: Iterable[Path], source_files: Iterable[Path]
) -> bool:
    """Paths must be resolved. A destination must be separate from imported trees."""
    return any(
        destination == root or destination in root.parents or root in destination.parents
        for root in source_folders
    ) or any(destination == path.parent or destination in path.parents for path in source_files)


def scan_media(
    selections: Iterable[Path],
    known_paths: Iterable[Path],
    cancel: Event,
    emit_batch: Callable[[list[MediaFile]], None],
    destination: Path | None = None,
) -> ScanReport:
    """Stream batches; never open media, follow symlinks, or write to disk.

    Cancellation keeps discovered entries. Filesystem operations already in progress
    cannot be interrupted (for example, a stalled network mount).
    """
    report = ScanReport()
    seen = set(known_paths)
    visited: set[Path] = set()
    batch: list[MediaFile] = []

    def add_file(path: Path, info: os.stat_result, subfolder: Path = Path()) -> None:
        if path.suffix.lower() not in MEDIA_EXTENSIONS:
            report.unsupported += 1
        elif destination is not None and destination_conflict(destination, (), (path,)):
            report.error(f"Output folder overlaps source: {path}")
        elif path in seen:
            report.duplicates += 1
        else:
            seen.add(path)
            batch.append(MediaFile(path, info.st_size, subfolder))
            report.added += 1
            if len(batch) >= 128:
                emit_batch(batch.copy())
                batch.clear()

    for selection in selections:
        if cancel.is_set():
            break
        try:
            # lstat before resolve prevents selected symlinks from becoming roots.
            info = selection.lstat()
            if stat.S_ISLNK(info.st_mode):
                report.symlinks += 1
                continue
            root = selection.resolve(strict=True)
            if stat.S_ISREG(info.st_mode):
                add_file(root, info)
                continue
            if not stat.S_ISDIR(info.st_mode):
                report.unsupported += 1
                continue
            if destination is not None and destination_conflict(destination, (root,), ()):
                report.error(f"Output folder overlaps source folder: {root}")
                continue
            report.source_folders.add(root)
            stack = [root]
            while stack and not cancel.is_set():
                folder = stack.pop()
                if folder in visited:
                    continue
                visited.add(folder)
                try:
                    with os.scandir(folder) as entries:
                        for entry in entries:
                            if cancel.is_set():
                                break
                            try:
                                if entry.is_symlink():
                                    report.symlinks += 1
                                elif entry.is_dir(follow_symlinks=False):
                                    stack.append(Path(entry.path))
                                elif entry.is_file(follow_symlinks=False):
                                    add_file(Path(entry.path), entry.stat(follow_symlinks=False),
                                             Path(root.name) / folder.relative_to(root))
                                else:
                                    report.unsupported += 1
                            except OSError as exc:
                                report.error(f"{entry.path}: {exc}")
                except OSError as exc:
                    report.error(f"{folder}: {exc}")
        except (OSError, RuntimeError) as exc:
            report.error(f"{selection}: {exc}")

    if batch:
        emit_batch(batch.copy())
    report.cancelled = cancel.is_set()
    return report
