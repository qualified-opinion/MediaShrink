import csv
import errno
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mediashrink.storage import check_destination, output_folder, publish
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
                check_destination(folder, 100)  # exFAT/FAT32 drives have no hard links.
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_publish_without_hard_links_never_replaces_existing_files(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            existing = root / 'clip-compressed.mp4'
            existing.write_bytes(b'keep')
            output = root / 'encoded.mp4'
            output.write_bytes(b'new')
            with patch('mediashrink.storage.os.link', side_effect=PermissionError(errno.EPERM, 'no links')):
                target = publish(output, root, 'clip', '.mp4', Event())
            self.assertEqual(target, root / 'clip-compressed-1.mp4')
            self.assertEqual((existing.read_bytes(), target.read_bytes()), (b'keep', b'new'))
            self.assertFalse(output.exists())
            other = root / 'other.mp4'
            other.write_bytes(b'x')
            with patch('mediashrink.storage.os.link', side_effect=OSError(errno.EIO, 'disk error')):
                with self.assertRaises(OSError):
                    publish(other, root, 'other', '.mp4', Event())
            self.assertFalse((root / 'other-compressed.mp4').exists())

    def test_output_subfolder_cannot_escape_through_symlink(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            destination, elsewhere = root / 'out', root / 'elsewhere'
            destination.mkdir()
            elsewhere.mkdir()
            self.assertEqual(output_folder(destination, Path('Phone/DCIM')), destination / 'Phone' / 'DCIM')
            (destination / 'Trip').symlink_to(elsewhere, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'plain folder'):
                output_folder(destination, Path('Trip/Day 1'))
            with self.assertRaises(ValueError):
                output_folder(destination, Path('../escape'))
            self.assertEqual(list(elsewhere.iterdir()), [])

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

    def test_results_log_maps_every_original(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / 'out'
            output.mkdir()
            paths = [root / f'{n}.jpg' for n in range(4)]
            for path in paths:
                path.write_bytes(b'x' * 100)
            worker = MediaThread([MediaFile(p, 100) for p in paths], output, ())
            messages = []
            worker.log_status.connect(messages.append)
            results = [(output / '0-compressed.jpg', 40), ValueError('Skipped: animated or multi-image photo'), Cancelled()]
            with patch('mediashrink.app.compress_photo', side_effect=results):
                worker.run()
            [log] = output.glob('mediashrink-results-*.csv')
            self.assertEqual(messages, [f'Results log: {log}'])
            with open(log, newline='', encoding='utf-8-sig') as file:
                rows = list(csv.DictReader(file))
            self.assertEqual([(r['Original file'], r['Result']) for r in rows],
                             [(str(paths[0]), 'Saved'), (str(paths[1]), 'Skipped'),
                              (str(paths[2]), 'Cancelled'), (str(paths[3]), 'Not processed')])
            self.assertEqual((rows[0]['Output file'], rows[0]['Saved bytes'], rows[0]['Saved %']),
                             (str(output / '0-compressed.jpg'), '60', '60.0'))

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
