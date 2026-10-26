from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mediashrink.storage import check_destination
from mediashrink.app import MediaThread
from mediashrink.importing import MediaFile
from mediashrink.video import Cancelled

class ReadinessTest(unittest.TestCase):
    def test_low_space_and_link_failure_leave_no_files(self):
        with TemporaryDirectory() as folder:
            with patch('mediashrink.storage.shutil.disk_usage', return_value=SimpleNamespace(free=1)):
                with self.assertRaisesRegex(OSError, 'space'):
                    check_destination(folder, 100)
            with patch('mediashrink.storage.os.link', side_effect=OSError('unsupported')):
                with self.assertRaisesRegex(OSError, 'hard links'):
                    check_destination(folder, 100)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_mixed_batch_counts_and_savings(self):
        with TemporaryDirectory() as folder:
            paths = [Path(folder)/f'{n}.jpg' for n in range(3)]
            for path in paths:
                path.write_bytes(b'x'*100)
            worker = MediaThread([MediaFile(p,100) for p in paths], Path(folder), ())
            summaries = []
            progress = []
            worker.batch_status.connect(summaries.append)
            worker.overall_progress.connect(progress.append)
            with patch('mediashrink.app.compress_photo', side_effect=[(Path(folder)/'out.jpg',40),(None,0),RuntimeError('bad media')]):
                worker.run()
            last = summaries[-1]
            self.assertEqual((last['saved'],last['skipped'],last['failed']), (1,1,1))
            self.assertEqual(last['original_bytes']-last['output_bytes'],60)
            self.assertEqual(progress[-1],100)

    def test_cancel_does_not_claim_completion(self):
        with TemporaryDirectory() as folder:
            source = Path(folder)/'photo.jpg'
            source.write_bytes(b'x')
            worker = MediaThread([MediaFile(source,1)]*2, Path(folder), ())
            summaries=[]
            worker.batch_status.connect(summaries.append)
            with patch('mediashrink.app.compress_photo', side_effect=Cancelled()):
                worker.run()
            self.assertEqual(summaries[-1]['completed'],0)
            self.assertEqual(summaries[-1]['cancelled'],1)
