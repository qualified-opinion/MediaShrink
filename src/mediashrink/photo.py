"""Photo encoding orchestration; originals are never modified."""
import os
from pathlib import Path
import sys
import tempfile

from mediashrink.importing import PHOTO_EXTENSIONS, destination_conflict
from mediashrink.storage import Cancelled, check_destination, output_folder, publish
from mediashrink.video import run

# HEIC stays HEIC: it is already more compact than JPEG, so a JPEG copy is almost never smaller.
OUTPUT_EXTENSIONS = {'.jpg': '.jpg', '.jpeg': '.jpg', '.heic': '.heic', '.png': '.webp', '.webp': '.webp'}


def compress(source, destination, roots, cancel, progress, preset='Balanced', folder=Path()):
    source = Path(source)
    if cancel.is_set():
        raise Cancelled('Cancelled')
    if source.is_symlink():
        raise ValueError('Source changed to a symlink')
    source = source.resolve(strict=True)
    destination = Path(destination).resolve(strict=True)
    if source.suffix.lower() not in PHOTO_EXTENSIONS:
        raise ValueError('Unsupported photo extension')
    if not source.is_file() or not destination.is_dir() or destination_conflict(destination, roots, (source,)):
        raise ValueError('Output folder overlaps source or source is unavailable')
    before = source.stat()
    check_destination(destination, before.st_size)
    extension = OUTPUT_EXTENSIONS[source.suffix.lower()]
    progress(0)
    with tempfile.TemporaryDirectory(prefix='.mediashrink-', dir=destination) as temporary:
        output = Path(temporary) / f'encoded{extension}'
        run([sys.executable, '-m', 'mediashrink.photo_worker', str(source), str(output), preset], cancel)
        progress(95)
        after = source.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise RuntimeError('Source changed during photo compression')
        size = output.stat().st_size
        if size <= 0:
            raise RuntimeError('Empty photo output')
        if size >= before.st_size:
            return None, 0
        os.utime(output, ns=(before.st_atime_ns, before.st_mtime_ns))
        target = publish(output, output_folder(destination, folder), source.stem, extension, cancel)
        progress(100)
        return target, size
