"""Output-folder safety shared by both engines; originals are never written."""
import errno
import os
from pathlib import Path
import shutil
import tempfile


class Cancelled(Exception):
    pass


# os.link errors meaning "this filesystem has no hard links" (exFAT, FAT32, some shares).
NO_HARD_LINKS = {errno.EPERM, errno.EOPNOTSUPP, errno.ENOTSUP, errno.ENOSYS}


def check_destination(destination, source_size):
    """Conservative preflight; available space can still change during processing."""
    required = source_size * 2 + 64 * 1024 * 1024
    if shutil.disk_usage(destination).free < required:
        raise OSError('Not enough output space: allow twice the source size plus 64 MiB')
    with tempfile.TemporaryDirectory(prefix='.mediashrink-check-', dir=destination) as folder:
        probe = Path(folder) / 'write'
        probe.write_bytes(b'probe')
        probe.rename(Path(folder) / 'renamed')


def output_folder(destination, subfolder):
    """Create the mirrored source subfolder inside the destination, one plain folder at a time."""
    subfolder = Path(subfolder)
    if subfolder.is_absolute() or '..' in subfolder.parts:
        raise ValueError('Invalid output subfolder')
    folder = Path(destination)
    for part in subfolder.parts:
        folder = folder / part
        try:
            folder.mkdir()
        except FileExistsError:
            pass
        # A symlink here could redirect output outside the chosen folder.
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError(f'Output subfolder is not a plain folder: {folder}')
    return folder


def publish(output, folder, stem, extension, cancel):
    """Move a validated temporary output into place without replacing any existing file."""
    for number in range(10000):
        if cancel.is_set():
            raise Cancelled('Cancelled')
        suffix = '' if number == 0 else f'-{number}'
        target = Path(folder) / f'{stem[:120]}-compressed{suffix}{extension}'
        try:
            os.link(output, target)
            return target
        except FileExistsError:
            continue
        except OSError as exc:
            if exc.errno not in NO_HARD_LINKS:
                raise
        # Without hard links, claim the name exclusively, then atomically rename over our own claim.
        try:
            os.close(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644))
        except FileExistsError:
            continue
        try:
            os.replace(output, target)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target
    raise RuntimeError('Too many output filename collisions')
