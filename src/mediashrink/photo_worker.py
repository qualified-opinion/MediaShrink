"""Isolated libvips work so cancellation can terminate image decoding/encoding."""
import json
import sys
from mediashrink.presets import PRESETS


def webp_is_lossy(path):
    """Read the RIFF chunk list: 'VP8 ' holds lossy image data, 'VP8L' lossless."""
    with open(path, 'rb') as file:
        header = file.read(12)
        if header[:4] != b'RIFF' or header[8:] != b'WEBP':
            return False
        while len(chunk := file.read(8)) == 8:
            if chunk[:4] in (b'VP8 ', b'VP8L'):
                return chunk[:4] == b'VP8 '
            size = int.from_bytes(chunk[4:], 'little')
            file.seek(size + (size & 1), 1)
    return False


def encode(source, output, preset='Balanced'):
    try:
        import pyvips
    except (ImportError, OSError) as exc:
        raise RuntimeError('Photo compression requires pyvips and a working libvips installation') from exc
    pyvips.cache_set_max(0)
    image = pyvips.Image.new_from_source(pyvips.Source.new_from_file(source), '', fail_on='warning')
    if image.get_typeof('n-pages') and image.get('n-pages') != 1:
        raise ValueError('Skipped: animated or multi-image photo')
    if image.format != 'uchar' or image.interpretation not in ('srgb', 'b-w'):
        raise ValueError('Skipped: HDR, high bit depth or unsupported colour space')
    if image.width * image.height > 100_000_000:
        raise ValueError('Skipped: photo exceeds 100 megapixels')
    if output.endswith('.heic'):
        try:
            pyvips.Image.black(16, 16, bands=3).heifsave_buffer(compression='hevc')
        except pyvips.Error:
            raise ValueError('Skipped: HEIC output needs the libheif HEVC (x265) encoder plugin') from None
    lossless = output.endswith('.webp') and not webp_is_lossy(source)
    image = image.autorot()
    if image.interpretation == 'b-w' and not output.endswith('.jpg'):
        image = image.colourspace('srgb')
    # Default libvips metadata retention preserves supported EXIF, XMP and ICC.
    if output.endswith('.jpg'):
        if image.hasalpha():
            raise ValueError('Skipped: JPEG output cannot preserve transparency')
        image.jpegsave(output, Q=PRESETS[preset].jpeg, optimize_coding=True)
    elif output.endswith('.heic'):
        image.heifsave(output, Q=PRESETS[preset].heic, compression='hevc')
    elif lossless:
        options = {'Q': 85, 'lossless': True}
        if 'exact' in pyvips.Introspect.get('webpsave').optional_input:
            options['exact'] = True
        image.webpsave(output, **options)
    else:
        # Lossy WebP re-saved losslessly would always grow, so it stays lossy.
        image.webpsave(output, Q=PRESETS[preset].webp)
    result = pyvips.Image.new_from_file(output, fail_on='warning')
    result.avg()  # Force full decoding before the parent can publish anything.
    if (image.width, image.height, image.bands) != (result.width, result.height, result.bands):
        raise RuntimeError('Photo validation failed: dimensions or channels changed')
    if result.get_typeof('orientation') and result.get('orientation') != 1:
        raise RuntimeError('Photo validation failed: orientation was not normalised')
    for field in ('icc-profile-data', 'xmp-data', 'exif-ifd2-DateTimeOriginal'):
        if image.get_typeof(field) and (not result.get_typeof(field) or image.get(field) != result.get(field)):
            raise RuntimeError(f'Photo validation failed: {field} was not preserved')
    if lossless and (image - result).abs().max() != 0:
        raise RuntimeError('Lossless photo validation failed')
    return {'width': result.width, 'height': result.height}


if __name__ == '__main__':
    try:
        print(json.dumps(encode(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'Balanced')))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
