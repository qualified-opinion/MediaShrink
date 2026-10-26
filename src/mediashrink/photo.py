"""Photo encoding orchestration; originals are never modified."""
import os
from pathlib import Path
import sys
import tempfile

from mediashrink.importing import PHOTO_EXTENSIONS, destination_conflict
from mediashrink.video import Cancelled, run


def compress(source, destination, roots, cancel, progress):
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
    extension = '.jpg' if source.suffix.lower() in ('.jpg', '.jpeg', '.heic') else '.webp'
    progress(0)
    with tempfile.TemporaryDirectory(prefix='.mediashrink-', dir=destination) as temporary:
        output = Path(temporary) / f'encoded{extension}'
        run([sys.executable, '-m', 'mediashrink.photo_worker', str(source), str(output)], cancel)
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
        for number in range(10000):
            if cancel.is_set():
                raise Cancelled('Cancelled')
            suffix = '' if number == 0 else f'-{number}'
            target = destination / f'{source.stem[:120]}-compressed{suffix}{extension}'
            try:
                os.link(output, target)
            except FileExistsError:
                continue
            progress(100)
            return target, size
        raise RuntimeError('Too many output filename collisions')
