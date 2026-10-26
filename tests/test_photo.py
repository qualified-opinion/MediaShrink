import os
from pathlib import Path
import tempfile
from threading import Event
import unittest
import pyvips
from mediashrink.photo import compress
from mediashrink.photo_worker import encode, webp_is_lossy
from mediashrink.video import Cancelled


def photo_like(width=400, height=300):
    """Smooth noise compresses like a photo, unlike flat synthetic colours."""
    base = pyvips.Image.gaussnoise(width // 4, height // 4, mean=128, sigma=40).gaussblur(2).resize(4)
    return base.bandjoin([base.flip('horizontal'), base.flip('vertical')]).cast('uchar').copy(interpretation='srgb')


def heic_encoder_available():
    try:
        pyvips.Image.black(16, 16, bands=3).heifsave_buffer(compression='hevc')
        return True
    except pyvips.Error:
        return False


class PhotoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.output = self.root / 'out'
        self.output.mkdir()

    def test_lossless_alpha_collision_and_original(self):
        source = self.root / 'photo [1].png'
        image = pyvips.Image.black(80, 60, bands=4).new_from_image([30, 90, 150, 70])
        image.pngsave(str(source), compression=0)
        original = source.read_bytes()
        stamp = source.stat().st_mtime_ns
        existing = self.output / 'photo [1]-compressed.webp'
        existing.write_bytes(b'keep')
        target, size = compress(source, self.output, (), Event(), lambda _: None)
        self.assertIsNotNone(target)
        self.assertLess(size, len(original))
        result = pyvips.Image.new_from_file(str(target))
        self.assertEqual((image - result).abs().max(), 0)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(target.stat().st_mtime_ns, stamp)
        self.assertEqual(existing.read_bytes(), b'keep')
        self.assertFalse(list(self.output.glob('.mediashrink-*')))

    def test_orientation_and_date_retained(self):
        source = self.root / 'rotated.jpg'
        image = pyvips.Image.black(80, 60).new_from_image(100)
        image.set_type(pyvips.GValue.gint_type, 'orientation', 6)
        image.set_type(pyvips.GValue.gstr_type, 'exif-ifd2-DateTimeOriginal', '2020:01:02 03:04:05')
        image.jpegsave(str(source))
        out = self.output / 'test.jpg'
        encode(str(source), str(out))
        result = pyvips.Image.new_from_file(str(out))
        self.assertEqual((result.width, result.height), (60, 80))
        self.assertIn('2020:01:02', result.get('exif-ifd2-DateTimeOriginal'))

    def test_animation_rejected(self):
        source = self.root / 'animated.webp'
        first = pyvips.Image.black(20, 20, bands=3)
        image = first.join(first + 200, 'vertical').cast('uchar')
        image.webpsave(str(source), page_height=20)
        with self.assertRaisesRegex(ValueError, 'animated'):
            encode(str(source), str(self.output / 'out.webp'))

    def test_corrupt_and_cancellation_cleanup(self):
        source = self.root / 'bad.jpg'
        source.write_bytes(b'not a jpeg')
        with self.assertRaises(RuntimeError):
            compress(source, self.output, (), Event(), lambda _: None)
        self.assertEqual(list(self.output.iterdir()), [])
        event = Event()
        event.set()
        with self.assertRaises(Cancelled):
            compress(source, self.output, (), event, lambda _: None)
        self.assertEqual(source.read_bytes(), b'not a jpeg')

    def test_larger_result_discarded_and_overlap_rejected(self):
        source = self.root / 'small.webp'
        pyvips.Image.black(1, 1).webpsave(str(source), lossless=True, strip=True)
        target, size = compress(source, self.output, (), Event(), lambda _: None)
        self.assertIsNone(target)
        self.assertEqual(list(self.output.iterdir()), [])
        with self.assertRaises(ValueError):
            compress(source, self.root, (), Event(), lambda _: None)

    def test_lossy_webp_stays_lossy_in_mirrored_folder(self):
        source = self.root / 'web.webp'
        photo_like().webpsave(str(source), Q=95)
        self.assertTrue(webp_is_lossy(source))
        target, size = compress(source, self.output, (), Event(), lambda _: None, folder=Path('Trip/Day 1'))
        self.assertEqual(target, self.output / 'Trip' / 'Day 1' / 'web-compressed.webp')
        self.assertTrue(webp_is_lossy(target))
        self.assertLess(size, source.stat().st_size)
        lossless = self.root / 'lossless.webp'
        photo_like().webpsave(str(lossless), lossless=True)
        self.assertFalse(webp_is_lossy(lossless))

    @unittest.skipUnless(heic_encoder_available(), 'libheif has no HEVC encoder')
    def test_heic_stays_heic_with_capture_date(self):
        source = self.root / 'IMG_0001.HEIC'
        image = photo_like().copy()
        image.set_type(pyvips.GValue.gstr_type, 'exif-ifd2-DateTimeOriginal', '2020:01:02 03:04:05')
        image.heifsave(str(source), Q=80, compression='hevc')
        target, size = compress(source, self.output, (), Event(), lambda _: None)
        self.assertEqual(target.name, 'IMG_0001-compressed.heic')
        self.assertLess(size, source.stat().st_size)
        result = pyvips.Image.new_from_file(str(target))
        self.assertEqual((result.width, result.height), (400, 300))
        self.assertIn('2020:01:02', result.get('exif-ifd2-DateTimeOriginal'))

    def test_high_bit_depth_rejected(self):
        source = self.root / 'deep.png'
        pyvips.Image.black(20, 20).cast('ushort').pngsave(str(source), bitdepth=16)
        with self.assertRaisesRegex(ValueError, 'high bit depth'):
            encode(str(source), str(self.output / 'out.webp'))
