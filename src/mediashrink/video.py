"""CPU encoding with cancellable subprocesses and no-clobber publication."""
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import tempfile
import time

from mediashrink.importing import destination_conflict


class Cancelled(Exception):
    pass


def run(command, cancel, progress=lambda value: None, timeout=None):
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errors)
        output = bytearray()
        started = time.monotonic()
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        pending = b''
        try:
            while selector.get_map():
                if cancel.is_set():
                    raise Cancelled('Cancelled')
                if timeout and time.monotonic() - started > timeout:
                    raise RuntimeError('Media probe timed out')
                for key, _ in selector.select(0.1):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    output.extend(chunk)
                    if len(output) > 4_000_000:
                        raise RuntimeError('Unexpectedly large tool output')
                    pending += chunk
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        if line.startswith(b'out_time_us='):
                            try:
                                progress(int(line.split(b'=')[1]) / 1_000_000)
                            except ValueError:
                                pass
            if process.wait() != 0:
                errors.seek(0, 2)
                errors.seek(max(0, errors.tell() - 3000))
                raise RuntimeError(errors.read().decode(errors='replace').strip() or 'Media tool failed')
            if cancel.is_set():
                raise Cancelled('Cancelled')
            return bytes(output)
        finally:
            selector.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stdout.close()


def probe(path, cancel):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], cancel, timeout=30))


def inspect(data):
    streams = data.get('streams', [])
    videos = [s for s in streams if s.get('codec_type') == 'video']
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    if len(videos) != 1 or len(audio) > 1 or len(streams) != len(videos) + len(audio):
        raise ValueError('Skipped: additional video, audio, subtitle or data streams are not supported yet')
    v = videos[0]
    if v.get('pix_fmt') not in ('yuv420p', 'yuvj420p') or v.get('color_transfer') in ('smpte2084', 'arib-std-b67') or v.get('color_primaries') == 'bt2020':
        raise ValueError('Skipped: HDR or unsupported pixel format')
    if v.get('side_data_list') or v.get('tags', {}).get('rotate') or v.get('disposition', {}).get('attached_pic'):
        raise ValueError('Skipped: rotation or additional video metadata is not supported yet')
    duration = float(data.get('format', {}).get('duration', 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Skipped: unknown duration')
    width, height = int(v['width']), int(v['height'])
    if width % 2 or height % 2:
        raise ValueError('Skipped: odd video dimensions')
    return duration, width, height, len(audio)


def compress(source, destination, roots, cancel, progress):
    source = Path(source)
    if source.is_symlink():
        raise ValueError('Source changed to a symlink')
    source = source.resolve(strict=True)
    destination = Path(destination).resolve(strict=True)
    if not destination.is_dir() or destination_conflict(destination, roots, (source,)):
        raise ValueError('Output folder overlaps source')
    before = source.stat()
    duration, width, height, audio = inspect(probe(source, cancel))
    # Private directory on the destination filesystem permits atomic hard-link publication.
    with tempfile.TemporaryDirectory(prefix='.mediashrink-', dir=destination) as temporary:
        output = Path(temporary) / 'encoded.mp4'
        run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-noautorotate', '-i', str(source),
             '-map', '0:v:0', '-map', '0:a:0?', '-map_metadata', '0', '-c:v', 'libx264',
             '-preset', 'medium', '-crf', '23', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
             '-b:a', '192k', '-movflags', '+faststart', '-progress', 'pipe:1', str(output)],
            cancel, lambda seconds: progress(min(95, int(seconds / duration * 95))))
        result = inspect(probe(output, cancel))
        if result[1:] != (width, height, audio) or abs(result[0] - duration) > max(0.25, duration * 0.01):
            raise RuntimeError('Output validation failed: dimensions, streams or duration changed')
        run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(output), '-map', '0', '-f', 'null', '-'], cancel)
        after = source.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise RuntimeError('Source changed during compression')
        size = output.stat().st_size
        if size >= before.st_size:
            return None, 0
        if cancel.is_set():
            raise Cancelled('Cancelled')
        os.utime(output, ns=(before.st_atime_ns, before.st_mtime_ns))
        for number in range(10000):
            suffix = '' if number == 0 else f'-{number}'
            target = destination / f'{source.stem[:120]}-compressed{suffix}.mp4'
            try:
                os.link(output, target)
                progress(100)
                return target, size
            except FileExistsError:
                continue
        raise RuntimeError('Too many output filename collisions')
