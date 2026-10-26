# MediaShrink

An offline Linux desktop app for batch photo and video compression, targeting Omarchy (Arch Linux) and optional NVIDIA acceleration.

**Current status: CPU photo and video compression.** Add files or recursively scan folders, see original sizes, cancel import, clear the queue, and choose a separate output folder. CPU video compression is available through **Compress photos and videos**. Install FFmpeg (`sudo pacman -Syu --needed ffmpeg`). Default output is CPU H.264/AAC MP4 using Balanced quality; Optional NVIDIA H.264/HEVC encoding is available. HDR, rotation metadata and extra streams are explicitly skipped. Outputs are fully decoded for validation and only kept if smaller. Existing outputs get a numbered filename; originals are retained. Import reads file information without opening media contents or modifying originals.

## Prepare a batch

1. Choose **Add files** or **Add folder** (includes subfolders).
2. Review the queue and total original size. Candidate extensions: MP4, MOV, MKV, JPEG/JPG, PNG, WebP and HEIC, regardless of letter case. The encoding engines validate actual formats and codec support.
3. Choose an existing output folder separate from imported folder trees. For individual files, their containing folder and its ancestors cannot be the output folder. Overlap is checked whether you select the destination before or after importing.

Import skips symlink files/folders, unsupported extensions, and duplicate absolute paths. It reports inaccessible or missing paths and continues. This is path deduplication, not content duplicate detection. The queue exists only for the current session.

**Cancel import** keeps files already discovered; **Clear queue** removes the queue and imported-folder restrictions. Scanning happens in a background thread. Closing requests cancellation and waits for the scan to stop; an in-progress filesystem operation on a stalled mount may delay cancellation. Import creates no output files. Compression uses a private temporary directory in the chosen output folder.

## Run on Omarchy / Arch

Use the distribution's Qt bindings, avoiding a separate Qt installation:

```bash
sudo pacman -Syu --needed python python-pip pyside6 git libvips python-pyvips ffmpeg
git clone https://github.com/qualified-opinion/MediaShrink.git
cd MediaShrink
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --no-deps --no-build-isolation -e .
mediashrink
```

The editable install requires setuptools 68 or newer. If it is unavailable in the environment, install it with `python -m pip install 'setuptools>=68'` and repeat the editable install. Use `python -m mediashrink` as an alternative launcher.

For a conventional isolated development environment (Python 3.11+):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[photos]' build
mediashrink
```

The isolated environment downloads PySide6 and needs the system OpenGL/EGL libraries. Qt uses the desktop's native theme; no fixed dark theme is required.

## Development checks

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
python -m pip install build
python -m build
```

The wheel and source archive are Python packages, not self-contained Linux applications. Installation needs dependencies; the application itself makes no network requests.

## Planned version 0.1

- Batch file/folder selection and three quality presets.
- FFmpeg video encoding with CPU and optional NVIDIA NVENC.
- libvips photo compression where the installed build supports the format.
- Progress, output validation, and measured savings.
- Separate output destination; originals are never automatically overwritten or deleted.

FFmpeg and FFprobe are required for video compression; importing alone does not require them. NVIDIA functionality must eventually be tested with a real encode on the target laptop. See [the roadmap](docs/ROADMAP.md) and [handover](HANDOVER.md) for the next steps.

## Photo compression

Install libvips and pyvips (included in the Arch command above); in an isolated environment use `python -m pip install '.[photos]'` plus your distribution's libvips runtime. Missing loaders or encoders are reported per file; HEIC support depends on the installed libheif/libvips build. Video compression remains usable without pyvips.

JPEG and supported HEIC inputs produce JPEG at quality 85. PNG and WebP produce lossless WebP with exact alpha pixels; dimensions are retained. EXIF orientation is applied to pixels and normalised. Supported EXIF/XMP/ICC metadata is retained by libvips, including location information when present; original modification time is retained. This is not a metadata scrubber. Validation checks full decoding, dimensions/channels, orientation, ICC/XMP and the original capture-date field when present; lossless WebP also gets a pixel comparison. It does not guarantee preservation of every vendor metadata tag.

Animated/multi-image inputs, unsupported colour spaces, high-bit-depth/HDR images and photos over 100 megapixels are skipped. Larger results are discarded. Photos use stage progress (0%, validation, complete), with cancellation terminating the isolated worker. Existing output names receive numeric suffixes. As with video, publication currently requires a filesystem with hard-link support. Test representative phone photos before using a large batch.

## Quality and NVIDIA encoding

Select High Quality, Balanced (default), or Small Size before starting. CPU video CRF values are 18/23/28; NVIDIA CQ values are 19/23/28; JPEG qualities are 92/85/75. These are starting settings, not equivalent quality across encoders or guaranteed savings. PNG/WebP stays lossless in every preset. Resolution is unchanged.

Video encoder choices: CPU H.264, NVIDIA H.264, NVIDIA HEVC. Photos always use CPU. NVIDIA selection performs a cancellable 15-second-limited real encode probe once per batch. If the probe fails, the visible encoder note explains the CPU H.264 fallback (including when HEVC was selected). A later per-file failure is reported without automatic retry. HEVC playback compatibility depends on your player. No AV1 option is offered.

The probe and all processing run off the UI thread; controls are locked for the batch. GPU encoding still uses CPU decoding and validation. CI tests fallback with simulated failures and real CPU encoding; real NVENC, driver compatibility, quality and performance must be checked on the target laptop.

## Batch results and release status

Overall progress weights each queued file equally, so it is not a time estimate. The final summary shows saved outputs, no-reduction results, failed/unsupported files, cancellations and files not processed. Reduction percentages use only successfully saved files. Originals remain on disk, so these figures do not represent space already freed. Full error/output paths are available in table tooltips.

Before each file, the destination needs twice the source size plus 64 MiB free and working write/hard-link support. Space can still run out during work. See [release readiness](docs/RELEASE.md) for interruption behavior, native acceptance checks and the AppImage assessment. CI provides Python package artifacts; no self-contained app or public release is published yet.
