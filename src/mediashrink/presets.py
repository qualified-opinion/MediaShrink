"""Starting quality settings, not guaranteed size or visual-quality targets."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Preset:
    crf: int
    cq: int
    jpeg: int
    hevc_crf: int
    heic: int
    webp: int

PRESETS = {
    'High Quality': Preset(18, 19, 92, 22, 60, 90),
    'Balanced': Preset(23, 23, 85, 26, 50, 80),
    'Small Size': Preset(28, 28, 75, 30, 40, 70),
}
ENCODERS = {'CPU': 'libx264', 'NVIDIA H.264': 'h264_nvenc', 'NVIDIA HEVC': 'hevc_nvenc'}
# HLG HDR (e.g. iPhone video) keeps its BT.2020/HLG signalling in the output.
HLG = ['-color_primaries', 'bt2020', '-color_trc', 'arib-std-b67', '-colorspace', 'bt2020nc', '-color_range', 'tv']


def video_options(encoder, preset, hdr=False):
    quality = PRESETS[preset]
    if encoder not in ENCODERS.values():
        raise ValueError('Unsupported encoder')
    nvenc = ['-c:v', encoder, '-preset', 'p5', '-rc', 'vbr', '-cq', str(quality.cq), '-b:v', '0']
    if hdr:
        # H.264 cannot carry 10-bit HDR, so HDR always uses HEVC Main10 (CPU unless NVIDIA HEVC was chosen).
        if encoder == 'hevc_nvenc':
            options = [*nvenc, '-profile:v', 'main10', '-pix_fmt', 'p010le']
        else:
            options = ['-c:v', 'libx265', '-preset', 'medium', '-crf', str(quality.hevc_crf),
                       '-profile:v', 'main10', '-pix_fmt', 'yuv420p10le', '-x265-params', 'log-level=error']
        return [*options, *HLG, '-tag:v', 'hvc1']
    if encoder == 'libx264':
        return ['-c:v', encoder, '-preset', 'medium', '-crf', str(quality.crf), '-pix_fmt', 'yuv420p']
    # hvc1 is the HEVC tag Apple players require.
    return [*nvenc, '-pix_fmt', 'yuv420p', *(['-tag:v', 'hvc1'] if encoder == 'hevc_nvenc' else [])]
