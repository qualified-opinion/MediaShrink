import subprocess
import tempfile
from pathlib import Path
from threading import Event
import unittest
from mediashrink.video import compress, run, Cancelled, inspect

class VideoTest(unittest.TestCase):
    def test_real_encode_and_collision(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source.mkv'
            output = root / 'output'
            output.mkdir()
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=128x96:rate=24','-t','1','-c:v','ffv1',str(source)],check=True)
            before = source.read_bytes()
            existing = output / 'source-compressed.mp4'
            existing.write_bytes(b'keep')
            target, size = compress(source, output, (), Event(), lambda p: None)
            self.assertIsNotNone(target)
            self.assertLess(size, len(before))
            self.assertEqual(existing.read_bytes(), b'keep')
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse(list(output.glob('.mediashrink-*')))

    def test_cancellation_reaps_process(self):
        event = Event()
        event.set()
        with self.assertRaises(Cancelled):
            run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2','-f','null','-'], event)

    def test_hdr_rejected(self):
        with self.assertRaises(ValueError):
            inspect({'streams':[{'codec_type':'video','pix_fmt':'yuv420p10le'}]})
