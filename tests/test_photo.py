import os
from pathlib import Path
import tempfile
from threading import Event
import unittest
import pyvips
from mediashrink.photo import compress
from mediashrink.photo_worker import encode
from mediashrink.video import Cancelled


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

    def test_high_bit_depth_rejected(self):
        source = self.root / 'deep.png'
        pyvips.Image.black(20, 20).cast('ushort').pngsave(str(source), bitdepth=16)
        with self.assertRaisesRegex(ValueError, 'high bit depth'):
            encode(str(source), str(self.output / 'out.webp'))
