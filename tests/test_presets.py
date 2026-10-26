from threading import Event
import unittest
from unittest.mock import patch
from mediashrink.presets import video_options
from mediashrink.video import choose_encoder, Cancelled

class EncoderTest(unittest.TestCase):
    def test_gpu_failure_falls_back_with_reason(self):
        messages = []
        with patch('mediashrink.video.run', side_effect=RuntimeError('driver missing')):
            self.assertEqual(choose_encoder('h264_nvenc', 'Balanced', Event(), messages.append), 'libx264')
        self.assertIn('driver missing', messages[-1])
        self.assertIn('CPU', messages[-1])

    def test_gpu_success_and_cancellation(self):
        with patch('mediashrink.video.run', return_value=b'') as run:
            self.assertEqual(choose_encoder('hevc_nvenc', 'Small Size', Event(), lambda _: None), 'hevc_nvenc')
            self.assertIn('hevc_nvenc', run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs['timeout'], 15)
        with patch('mediashrink.video.run', side_effect=Cancelled()):
            with self.assertRaises(Cancelled):
                choose_encoder('h264_nvenc', 'Balanced', Event(), lambda _: None)

    def test_cpu_does_not_probe_and_unknown_encoder_rejected(self):
        with patch('mediashrink.video.run') as run:
            self.assertEqual(choose_encoder('libx264', 'Balanced', Event(), lambda _: None), 'libx264')
            run.assert_not_called()
        with self.assertRaises(ValueError):
            video_options('av1_nvenc', 'Balanced')

    def test_hevc_is_apple_compatible_and_hdr_uses_main10(self):
        self.assertIn('hvc1', video_options('hevc_nvenc', 'Balanced'))
        self.assertNotIn('hvc1', video_options('h264_nvenc', 'Balanced'))
        for encoder, codec in (('libx264', 'libx265'), ('h264_nvenc', 'libx265'), ('hevc_nvenc', 'hevc_nvenc')):
            options = video_options(encoder, 'Balanced', hdr=True)
            self.assertEqual(options[options.index('-c:v') + 1], codec)
            self.assertIn('main10', options)
            self.assertIn('arib-std-b67', options)
