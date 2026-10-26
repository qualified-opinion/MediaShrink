"""Synthetic file discovery fixtures; no real photos or videos are used."""

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from mediashrink.importing import destination_conflict, scan_media


class DiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.media = self.root / 'phone backup'
        self.media.mkdir()

    def make_file(self, name, data=b'synthetic'):
        path = self.media / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def scan(self, paths, known=(), destination=None, cancel=None, callback=None):
        files = []
        def emit(batch):
            files.extend(batch)
            if callback:
                callback(batch)
        report = scan_media(paths, known, cancel or Event(), emit, destination)
        return files, report

    def test_recursive_filter_sizes_and_originals_unchanged(self):
        image = self.make_file('nested/photo.JPG', b'123')
        video = self.make_file('clip.MOV', b'12345')
        self.make_file('notes.txt')
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (image, video)}
        files, report = self.scan([self.media])
        self.assertEqual({f.path: f.size for f in files}, {image: 3, video: 5})
        self.assertEqual(report.added, 2)
        self.assertEqual(report.unsupported, 1)
        self.assertEqual(report.source_folders, {self.media})
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})

    def test_output_subfolder_mirrors_source_layout(self):
        nested = self.make_file('DCIM/100APPLE/IMG_0001.JPG')
        top = self.make_file('IMG_0002.JPG')
        single = self.root / 'single.jpg'
        single.write_bytes(b'x')
        files, _ = self.scan([self.media, single])
        self.assertEqual({f.path: f.folder for f in files}, {
            nested: Path('phone backup/DCIM/100APPLE'), top: Path('phone backup'), single: Path(),
        })

    def test_repeated_file_overlapping_roots_and_existing_queue(self):
        first = self.make_file('sub/a.mp4')
        second = self.make_file('sub/b.heic')
        files, report = self.scan([first, self.media, self.media / 'sub', first], known=(second,))
        self.assertEqual([f.path for f in files], [first])
        self.assertEqual(report.duplicates, 3)

    def test_symlinks_including_selected_roots_are_skipped(self):
        image = self.make_file('photo.png')
        (self.media / 'loop').symlink_to(self.media, target_is_directory=True)
        alias = self.media / 'alias.png'
        alias.symlink_to(image)
        files, report = self.scan([self.media, alias, self.media / 'loop'])
        self.assertEqual([f.path for f in files], [image])
        self.assertEqual(report.symlinks, 4)

    def test_missing_path_reports_error_and_continues(self):
        image = self.make_file('photo.webp')
        files, report = self.scan([self.media / 'missing.mp4', image])
        self.assertEqual([f.path for f in files], [image])
        self.assertEqual(report.error_count, 1)

    def test_permission_error_does_not_abort_other_roots(self):
        image = self.make_file('photo.jpeg')
        with patch('mediashrink.importing.os.scandir', side_effect=PermissionError('denied')):
            files, report = self.scan([self.media, image])
        self.assertEqual([f.path for f in files], [image])
        self.assertEqual(report.error_count, 1)

    def test_errors_are_bounded(self):
        _, report = self.scan([self.media / f'{n}.jpg' for n in range(50)])
        self.assertEqual(report.error_count, 50)
        self.assertEqual(len(report.errors), 20)

    def test_cancel_before_scan(self):
        self.make_file('photo.jpg')
        cancel = Event()
        cancel.set()
        files, report = self.scan([self.media], cancel=cancel)
        self.assertEqual(files, [])
        self.assertTrue(report.cancelled)

    def test_cancel_between_batches_keeps_discovered_files(self):
        for n in range(300):
            self.make_file(f'{n}.jpg')
        cancel = Event()
        files, report = self.scan([self.media], cancel=cancel, callback=lambda _: cancel.set())
        self.assertEqual(len(files), 128)
        self.assertEqual(report.added, 128)
        self.assertTrue(report.cancelled)

    def test_output_overlap_in_both_orders_and_sibling_allowed(self):
        image = self.make_file('photo.jpg')
        nested = self.media / 'output'
        nested.mkdir()
        sibling = self.root / 'compressed'
        sibling.mkdir()
        for destination in (self.root, self.media, nested):
            self.assertTrue(destination_conflict(destination, (self.media,), (image,)))
            files, report = self.scan([self.media], destination=destination)
            self.assertEqual(files, [])
            self.assertEqual(report.error_count, 1)
        self.assertFalse(destination_conflict(sibling, (self.media,), (image,)))
        files, report = self.scan([self.media], destination=sibling)
        self.assertEqual([f.path for f in files], [image])
        self.assertEqual(report.error_count, 0)
        files, report = self.scan([image], destination=self.media)
        self.assertEqual(files, [])
        self.assertEqual(report.error_count, 1)


if __name__ == '__main__':
    unittest.main()
