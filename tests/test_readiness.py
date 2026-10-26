import csv
import errno
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import threading
import time
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
            worker = MediaThread([MediaFile(p,100) for p in paths], Path(folder), (), workers=1)
            summaries = []
            progress = []
            worker.batch_status.connect(summaries.append)
            worker.overall_progress.connect(progress.append)
            with patch('mediashrink.app.compress_photo', side_effect=[(Path(folder)/'out.jpg',40),(None,0),RuntimeError('bad media')]):
                worker.run()
            last = summaries[-1]
            self.assertEqual((last['saved'],last['skipped'],last['failed'],last['unsupported']), (1,1,1,0))
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
            worker = MediaThread([MediaFile(p, 100) for p in paths], output, (), workers=1)
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

    def test_rerun_skips_files_already_done_in_this_output_folder(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / 'out'
            output.mkdir()
            paths = [root / f'{n}.jpg' for n in range(3)]
            for path in paths:
                path.write_bytes(b'x' * 100)
            saved = output / '0-compressed.jpg'
            saved.write_bytes(b'y' * 40)
            first = [(saved, 40), (None, 0), ValueError('Skipped: animated or multi-image photo')]
            with patch('mediashrink.app.compress_photo', side_effect=first):
                MediaThread([MediaFile(p, 100) for p in paths], output, (), workers=1).run()
            paths[1].write_bytes(b'x' * 99)  # Changed since the first batch, so it is compressed again.
            worker = MediaThread([MediaFile(p, 100) for p in paths], output, (), skip_done=True, workers=1)
            summaries = []
            worker.batch_status.connect(summaries.append)
            with patch('mediashrink.app.compress_photo', side_effect=[(None, 0), (None, 0)]) as engine:
                worker.run()
            self.assertEqual([c.args[0] for c in engine.call_args_list], paths[1:])
            last = summaries[-1]
            self.assertEqual((last['previous'], last['skipped'], last['unsupported'], last['failed']), (1, 2, 0, 0))
            with patch('mediashrink.app.compress_photo', side_effect=[(None, 0)] * 3) as engine:
                MediaThread([MediaFile(p, 100) for p in paths], output, (), skip_done=False).run()
            self.assertEqual(engine.call_count, 3)

    def test_unsupported_counted_separately_from_failures(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / 'photo.jpg'
            source.write_bytes(b'x')
            output = Path(folder) / 'out'
            output.mkdir()
            worker = MediaThread([MediaFile(source, 1)] * 2, output, (), workers=1)
            summaries = []
            worker.batch_status.connect(summaries.append)
            with patch('mediashrink.app.compress_photo', side_effect=[ValueError('Skipped: HDR'), RuntimeError('broken')]):
                worker.run()
            self.assertEqual((summaries[-1]['unsupported'], summaries[-1]['failed']), (1, 1))

    def test_photos_run_in_parallel_and_videos_after(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / 'out'
            output.mkdir()
            photos = [root / f'{n}.jpg' for n in range(6)]
            video = root / 'clip.mp4'
            for path in (*photos, video):
                path.write_bytes(b'x' * 100)
            active, peak, order = [0], [0], []
            lock = threading.Lock()
            def slow_photo(source, *args, **kwargs):
                with lock:
                    active[0] += 1
                    peak[0] = max(peak[0], active[0])
                time.sleep(0.1)
                with lock:
                    active[0] -= 1
                    order.append(source)
                return None, 100
            def video_engine(source, *args, **kwargs):
                order.append(source)
                return None, 100
            worker = MediaThread([MediaFile(p, 100) for p in (video, *photos)], output, (), workers=2)
            summaries, progress = [], []
            worker.batch_status.connect(summaries.append)
            worker.overall_progress.connect(progress.append)
            with patch('mediashrink.app.compress_photo', side_effect=slow_photo), \
                    patch('mediashrink.app.compress', side_effect=video_engine), \
                    patch('mediashrink.app.choose_encoder', return_value='libx264'):
                worker.run()
            self.assertEqual(peak[0], 2)
            self.assertEqual(order[-1], video)
            self.assertEqual(summaries[-1]['completed'], 7)
            self.assertEqual(progress, sorted(progress))
            self.assertEqual(progress[-1], 100)

    def test_minimum_saving_reported(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'photo.jpg'
            source.write_bytes(b'x' * 100)
            output = root / 'out'
            output.mkdir()
            worker = MediaThread([MediaFile(source, 100)], output, (), min_saving=0.05, workers=1)
            updates = []
            worker.update.connect(lambda row, status, size: updates.append(status))
            with patch('mediashrink.app.compress_photo', return_value=(None, 97)) as engine:
                worker.run()
            self.assertEqual(engine.call_args.kwargs['min_saving'], 0.05)
            self.assertEqual(updates[-1], 'Skipped: only 3.0% smaller')
            [log] = output.glob('mediashrink-results-*.csv')
            with open(log, newline='', encoding='utf-8-sig') as file:
                row = next(csv.DictReader(file))
            self.assertEqual((row['Result'], row['Details']), ('No reduction', 'only 3.0% smaller'))

    def test_cancel_does_not_claim_completion(self):
        with TemporaryDirectory() as folder:
            source = Path(folder)/'photo.jpg'
            source.write_bytes(b'x')
            worker = MediaThread([MediaFile(source,1)]*2, Path(folder), (), workers=1)
            summaries=[]
            worker.batch_status.connect(summaries.append)
            with patch('mediashrink.app.compress_photo', side_effect=Cancelled()):
                worker.run()
            self.assertEqual(summaries[-1]['completed'],0)
            self.assertEqual(summaries[-1]['cancelled'],1)
