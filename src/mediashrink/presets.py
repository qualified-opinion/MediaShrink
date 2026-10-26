"""Starting quality settings, not guaranteed size or visual-quality targets."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Preset:
    crf: int
    cq: int
    jpeg: int

PRESETS = {
    'High Quality': Preset(18, 19, 92),
    'Balanced': Preset(23, 23, 85),
    'Small Size': Preset(28, 28, 75),
}
ENCODERS = {'CPU': 'libx264', 'NVIDIA H.264': 'h264_nvenc', 'NVIDIA HEVC': 'hevc_nvenc'}


def video_options(encoder, preset):
    quality = PRESETS[preset]
    if encoder == 'libx264':
        return ['-c:v', encoder, '-preset', 'medium', '-crf', str(quality.crf)]
    if encoder not in ('h264_nvenc', 'hevc_nvenc'):
        raise ValueError('Unsupported encoder')
    return ['-c:v', encoder, '-preset', 'p5', '-rc', 'vbr', '-cq', str(quality.cq), '-b:v', '0']
