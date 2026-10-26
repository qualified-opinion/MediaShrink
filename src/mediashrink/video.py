"""CPU/NVIDIA encoding with cancellable subprocesses and no-clobber publication."""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import tempfile
import time

from mediashrink.importing import destination_conflict
from mediashrink.presets import video_options
from mediashrink.storage import Cancelled, check_destination, output_folder, publish


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


@dataclass(frozen=True)
class VideoInfo:
    duration: float
    width: int  # Display size, after rotation.
    height: int
    audio: int
    rotation: int
    hdr: bool


def is_pure_rotation(text):
    """Return True when an ffprobe display matrix is a pure rotation (no mirroring)."""
    rows = [line.split(':', 1)[1].split() for line in text.strip().splitlines() if ':' in line]
    try:
        (a, b, _), (c, d, _) = [[int(value) for value in row] for row in rows[:2]]
    except ValueError:
        return False
    return a * d - b * c > 0


def inspect(data):
    streams = data.get('streams', [])
    videos = [s for s in streams if s.get('codec_type') == 'video']
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    # Data tracks (timecode, camera/GPS metadata) are dropped; anything viewable or audible is not.
    others = [s for s in streams if s.get('codec_type') not in ('video', 'audio', 'data')]
    if len(videos) != 1 or len(audio) > 1 or others:
        raise ValueError('Skipped: additional video, audio or subtitle streams are not supported yet')
    v = videos[0]
    if v.get('disposition', {}).get('attached_pic'):
        raise ValueError('Skipped: cover-art video streams are not supported yet')
    hdr = v.get('color_transfer') == 'arib-std-b67'
    if hdr:
        if (v.get('pix_fmt'), v.get('color_primaries'), v.get('color_space')) != ('yuv420p10le', 'bt2020', 'bt2020nc'):
            raise ValueError('Skipped: unsupported HLG HDR format')
    elif v.get('pix_fmt') not in ('yuv420p', 'yuvj420p') or v.get('color_transfer') == 'smpte2084' or v.get('color_primaries') == 'bt2020':
        raise ValueError('Skipped: HDR10/PQ, wide-gamut or unsupported pixel format')
    try:
        rotation = int(v.get('tags', {}).get('rotate', 0))
    except ValueError:
        raise ValueError('Skipped: unreadable rotation metadata') from None
    for side in v.get('side_data_list', []):
        kind = side.get('side_data_type')
        if kind == 'Display Matrix':
            if not is_pure_rotation(side.get('displaymatrix', '')):
                raise ValueError('Skipped: mirrored video is not supported yet')
            rotation = round(float(side.get('rotation', 0)))
        elif kind == 'DOVI configuration record' and hdr and side.get('dv_bl_signal_compatibility_id') == 4:
            pass  # iPhone Dolby Vision: the HLG base layer is kept; the Dolby Vision layer is dropped.
        else:
            raise ValueError(f'Skipped: unsupported video metadata ({kind or "unknown"})')
    if rotation % 90:
        raise ValueError('Skipped: rotation is not a multiple of 90 degrees')
    duration = float(data.get('format', {}).get('duration', 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Skipped: unknown duration')
    width, height = int(v['width']), int(v['height'])
    if width % 2 or height % 2:
        raise ValueError('Skipped: odd video dimensions')
    if rotation % 180:
        width, height = height, width
    return VideoInfo(duration, width, height, len(audio), rotation % 360, hdr)


def choose_encoder(requested, preset, cancel, notify):
    if requested == 'libx264':
        return requested
    options = video_options(requested, preset)
    notify('Testing NVIDIA encoder…')
    try:
        run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
             'color=size=128x128:rate=24', '-frames:v', '3', *options,
             '-f', 'null', '-'], cancel, timeout=15)
        notify(f'Using {requested}')
        return requested
    except Cancelled:
        raise
    except (RuntimeError, OSError) as exc:
        notify(f'NVIDIA unavailable; using CPU H.264. {str(exc)[-300:]}')
        return 'libx264'


def compress(source, destination, roots, cancel, progress, preset='Balanced', encoder='libx264', folder=Path()):
    source = Path(source)
    if source.is_symlink():
        raise ValueError('Source changed to a symlink')
    source = source.resolve(strict=True)
    destination = Path(destination).resolve(strict=True)
    if not destination.is_dir() or destination_conflict(destination, roots, (source,)):
        raise ValueError('Output folder overlaps source')
    before = source.stat()
    check_destination(destination, before.st_size)
    info = inspect(probe(source, cancel))
    # Private directory on the destination filesystem permits atomic publication.
    with tempfile.TemporaryDirectory(prefix='.mediashrink-', dir=destination) as temporary:
        output = Path(temporary) / 'encoded.mp4'
        # Rotation is applied to the pixels (ffmpeg autorotate), so outputs need no rotation flag.
        run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-i', str(source),
             '-map', '0:v:0', '-map', '0:a:0?', '-map_metadata', '0', *video_options(encoder, preset, info.hdr),
             '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-progress', 'pipe:1', str(output)],
            cancel, lambda seconds: progress(min(95, int(seconds / info.duration * 95))))
        result = inspect(probe(output, cancel))
        expected = (info.width, info.height, info.audio, 0, info.hdr)
        if ((result.width, result.height, result.audio, result.rotation, result.hdr) != expected
                or abs(result.duration - info.duration) > max(0.25, info.duration * 0.01)):
            raise RuntimeError('Output validation failed: dimensions, rotation, HDR, streams or duration changed')
        run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(output), '-map', '0', '-f', 'null', '-'], cancel)
        after = source.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise RuntimeError('Source changed during compression')
        size = output.stat().st_size
        if size >= before.st_size:
            return None, 0
        os.utime(output, ns=(before.st_atime_ns, before.st_mtime_ns))
        target = publish(output, output_folder(destination, folder), source.stem, '.mp4', cancel)
        progress(100)
        return target, size
