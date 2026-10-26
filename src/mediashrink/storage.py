"""Conservative preflight; available space can still change during processing."""
import os
from pathlib import Path
import shutil
import tempfile


def check_destination(destination, source_size):
    required = source_size * 2 + 64 * 1024 * 1024
    if shutil.disk_usage(destination).free < required:
        raise OSError('Not enough output space: allow twice the source size plus 64 MiB')
    with tempfile.TemporaryDirectory(prefix='.mediashrink-check-', dir=destination) as folder:
        probe = Path(folder) / 'write'
        probe.write_bytes(b'probe')
        try:
            os.link(probe, Path(folder) / 'link')
        except OSError as exc:
            raise OSError('Output filesystem must support hard links; choose a different destination') from exc
