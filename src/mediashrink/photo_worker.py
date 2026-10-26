"""Isolated libvips work so cancellation can terminate image decoding/encoding."""
import json
import sys


def encode(source, output):
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
    image = image.autorot()
    if image.interpretation == 'b-w' and not output.endswith('.jpg'):
        image = image.colourspace('srgb')
    # Default libvips metadata retention preserves supported EXIF, XMP and ICC.
    if output.endswith('.jpg'):
        if image.hasalpha():
            raise ValueError('Skipped: JPEG output cannot preserve transparency')
        image.jpegsave(output, Q=85, optimize_coding=True)
    else:
        image.webpsave(output, Q=85, lossless=True, exact=True)
    result = pyvips.Image.new_from_file(output, fail_on='warning')
    result.avg()  # Force full decoding before the parent can publish anything.
    if (image.width, image.height, image.bands) != (result.width, result.height, result.bands):
        raise RuntimeError('Photo validation failed: dimensions or channels changed')
    if result.get_typeof('orientation') and result.get('orientation') != 1:
        raise RuntimeError('Photo validation failed: orientation was not normalised')
    for field in ('icc-profile-data', 'xmp-data', 'exif-ifd2-DateTimeOriginal'):
        if image.get_typeof(field) and (not result.get_typeof(field) or image.get(field) != result.get(field)):
            raise RuntimeError(f'Photo validation failed: {field} was not preserved')
    if output.endswith('.webp') and (image - result).abs().max() != 0:
        raise RuntimeError('Lossless photo validation failed')
    return {'width': result.width, 'height': result.height}


if __name__ == '__main__':
    try:
        print(json.dumps(encode(sys.argv[1], sys.argv[2])))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
