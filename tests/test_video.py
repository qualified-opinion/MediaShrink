import json
import subprocess
import tempfile
from pathlib import Path
from threading import Event
import unittest
from mediashrink.video import compress, run, Cancelled, inspect, probe

ROTATE_90 = '\n00000000:            0      -65536           0\n00000001:        65536           0           0\n00000002:            0           0  1073741824\n'
MIRRORED = '\n00000000:            0      -65536           0\n00000001:       -65536           0           0\n00000002:            0           0  1073741824\n'
HAS_X265 = 'libx265' in subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout


def ffmpeg(*args):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *map(str, args)], check=True)


def stream_info(path):
    command = ['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries',
               'stream=codec_tag_string,pix_fmt,color_transfer', '-of', 'json', str(path)]
    return json.loads(subprocess.run(command, capture_output=True, check=True).stdout)['streams'][0]


def info(video, audio=1, extra=()):
    stream = {'codec_type': 'video', 'pix_fmt': 'yuv420p', 'width': 64, 'height': 48, **video}
    return {'streams': [stream, *[{'codec_type': 'audio'}] * audio, *extra], 'format': {'duration': '1.0'}}

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

    def test_phone_portrait_and_timecode_track_in_mirrored_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plain = root / 'plain.mp4'
            ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=128x96:rate=24', '-f', 'lavfi', '-i', 'sine',
                   '-t', '1', '-c:v', 'libx264', '-crf', '5', '-c:a', 'aac', plain)
            portrait, timecode = root / 'portrait.mp4', root / 'timecode.mov'
            ffmpeg('-display_rotation', '90', '-i', plain, '-c', 'copy', portrait)
            ffmpeg('-i', plain, '-c', 'copy', '-timecode', '01:00:00:00', timecode)
            output = root / 'output'
            output.mkdir()
            target, _ = compress(portrait, output, (), Event(), lambda p: None, folder=Path('Phone/DCIM'))
            self.assertEqual(target, output / 'Phone' / 'DCIM' / 'portrait-compressed.mp4')
            result = inspect(probe(target, Event()))
            self.assertEqual((result.width, result.height, result.rotation, result.audio), (96, 128, 0, 1))
            target, _ = compress(timecode, output, (), Event(), lambda p: None)
            self.assertEqual(target, output / 'timecode-compressed.mp4')

    @unittest.skipUnless(HAS_X265, 'FFmpeg has no libx265')
    def test_hlg_hdr_stays_10_bit_hevc(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'hdr.mov'
            ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=128x96:rate=24', '-t', '1', '-c:v', 'libx265',
                   '-x265-params', 'log-level=error:crf=5', '-pix_fmt', 'yuv420p10le', '-color_primaries', 'bt2020',
                   '-color_trc', 'arib-std-b67', '-colorspace', 'bt2020nc', source)
            output = root / 'output'
            output.mkdir()
            target, _ = compress(source, output, (), Event(), lambda p: None)
            self.assertTrue(inspect(probe(target, Event())).hdr)
            self.assertEqual(stream_info(target), {'codec_tag_string': 'hvc1', 'pix_fmt': 'yuv420p10le',
                                                   'color_transfer': 'arib-std-b67'})

    def test_inspect_accepts_phone_metadata_and_rejects_unsafe_streams(self):
        rotated = {'side_data_list': [{'side_data_type': 'Display Matrix', 'displaymatrix': ROTATE_90, 'rotation': -90}]}
        self.assertEqual((inspect(info(rotated)).width, inspect(info(rotated)).rotation), (48, 270))
        self.assertEqual(inspect(info({}, extra=[{'codec_type': 'data'}])).audio, 1)
        hlg = {'pix_fmt': 'yuv420p10le', 'color_transfer': 'arib-std-b67', 'color_primaries': 'bt2020', 'color_space': 'bt2020nc'}
        dolby = {'side_data_type': 'DOVI configuration record', 'dv_bl_signal_compatibility_id': 4}
        self.assertTrue(inspect(info({**hlg, 'side_data_list': [dolby]})).hdr)
        rejected = [
            {'side_data_list': [{'side_data_type': 'Display Matrix', 'displaymatrix': MIRRORED, 'rotation': 90}]},
            {'side_data_list': [dolby]},
            {'side_data_list': [{'side_data_type': 'Spherical Mapping'}]},
            {**hlg, 'color_transfer': 'smpte2084'},
            {'tags': {'rotate': '45'}},
        ]
        for video in rejected:
            with self.subTest(video=video), self.assertRaisesRegex(ValueError, 'Skipped'):
                inspect(info(video))
        with self.assertRaisesRegex(ValueError, 'subtitle'):
            inspect(info({}, extra=[{'codec_type': 'subtitle'}]))
        with self.assertRaisesRegex(ValueError, 'audio'):
            inspect(info({}, audio=2))

    def test_cancellation_reaps_process(self):
        event = Event()
        event.set()
        with self.assertRaises(Cancelled):
            run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2','-f','null','-'], event)

    def test_hdr_rejected(self):
        with self.assertRaises(ValueError):
            inspect({'streams':[{'codec_type':'video','pix_fmt':'yuv420p10le'}]})
