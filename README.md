# MediaShrink

An offline Linux desktop app for batch photo and video compression, targeting Omarchy (Arch Linux) and optional NVIDIA acceleration.

**Current status: CPU photo and video compression.** Add files or recursively scan folders, see original sizes, cancel import, clear the queue, and choose a separate output folder. CPU video compression is available through **Compress photos and videos**. Install FFmpeg (`sudo pacman -Syu --needed ffmpeg`). Default output is CPU H.264 MP4 using Balanced quality; AAC audio (the usual phone audio) is copied unchanged and other audio becomes AAC at no more than its original bitrate, up to 192 kbps; Optional NVIDIA H.264/HEVC encoding is available. Portrait (rotated) phone videos are supported, and HLG HDR video (the iPhone default) is kept as 10-bit HDR HEVC. Timecode and camera metadata tracks are dropped; HDR10/PQ, mirrored video, subtitles and extra audio/video streams are explicitly skipped. Outputs are fully decoded for validation and only kept if smaller. Outputs mirror the imported folder structure, existing outputs get a numbered filename, every batch writes a CSV results log, files already compressed into the same output folder are skipped on later runs, and originals are retained. Import reads file information without opening media contents or modifying originals.

## Prepare a batch

1. Choose **Add files** or **Add folder** (includes subfolders), or drag files and folders onto the window.
2. Review the queue and total original size. Select rows and choose **Remove selected** (or press Delete) to take files out of the queue. Candidate extensions: MP4, M4V, MOV, MKV, 3GP, AVI, JPEG/JPG, PNG, WebP, HEIC and HEIF, regardless of letter case. AVI is accepted for older cameras that record Motion JPEG; their 4:2:2 colour is reduced to the standard 4:2:0 used by MP4 video. The encoding engines validate actual formats and codec support.
3. Choose an existing output folder separate from imported folder trees. For individual files, their containing folder and its ancestors cannot be the output folder. Overlap is checked whether you select the destination before or after importing.

Import skips symlink files/folders, unsupported extensions, and duplicate absolute paths. It reports inaccessible or missing paths and continues. This is path deduplication, not content duplicate detection. The queue exists only for the current session.

**Cancel import** keeps files already discovered; **Clear queue** removes the queue and imported-folder restrictions. Scanning happens in a background thread. Closing requests cancellation and waits for the scan to stop; an in-progress filesystem operation on a stalled mount may delay cancellation. Import creates no output files. Compression uses a private temporary directory in the chosen output folder.

## Install on Omarchy / Arch

MediaShrink installs as a normal Arch package, built on your computer from this repository with Arch's own Python, Qt, FFmpeg and libvips:

```bash
sudo pacman -S --needed git base-devel
git clone https://github.com/qualified-opinion/MediaShrink.git
cd MediaShrink/packaging/arch
makepkg -sif
```

`makepkg` installs any missing dependencies, runs the test suite as a self-check, and installs the package (it asks for your password). MediaShrink then appears in the app launcher (Super + Space on Omarchy) with its icon; `mediashrink` also starts it from a terminal.

- **Update:** `cd MediaShrink && git pull && cd packaging/arch && makepkg -sif`
- **Uninstall:** `sudo pacman -R mediashrink` (compressed outputs and results logs are not touched)
- **NVIDIA encoding** needs the NVIDIA driver (`nvidia-utils`), which Omarchy installs on NVIDIA laptops.
- If the self-check fails on your system, `makepkg -sif --nocheck` installs anyway; please report the failing test.

CI builds and installs the same package in an Arch Linux container on every change and keeps the built `.pkg.tar.zst` as a download (`mediashrink-arch-package`); it can be installed with `sudo pacman -U mediashrink-*.pkg.tar.zst`.

## Development setup

To run directly from the checkout while changing the code, use the distribution's Qt bindings in a virtual environment:

```bash
sudo pacman -Syu --needed python python-pip python-setuptools pyside6 git libvips libheif python-pyvips ffmpeg
git clone https://github.com/qualified-opinion/MediaShrink.git
cd MediaShrink
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --no-deps --no-build-isolation -e .
mediashrink
```

The editable install requires setuptools 68 or newer. Use `python -m mediashrink` as an alternative launcher. If you installed this way before and now use the package, you can delete the `.venv` folder.

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

The wheel and source archive are Python packages, not self-contained Linux applications; on Arch, use the package above. Installation needs dependencies; the application itself makes no network requests.

## Planned version 0.1

- Batch file/folder selection and three quality presets.
- FFmpeg video encoding with CPU and optional NVIDIA NVENC.
- libvips photo compression where the installed build supports the format.
- Progress, output validation, and measured savings.
- Separate output destination; originals are never automatically overwritten or deleted.

FFmpeg and FFprobe are required for video compression; importing alone does not require them. If they are missing, each video reports how to install FFmpeg. NVIDIA functionality must eventually be tested with a real encode on the target laptop. See [the roadmap](docs/ROADMAP.md) and [handover](HANDOVER.md) for the next steps.

## Photo compression

Install libvips and pyvips (included in the Arch command above); in an isolated environment use `python -m pip install '.[photos]'` plus your distribution's libvips runtime. Missing loaders or encoders are reported per file; HEIC support depends on the installed libheif/libvips build. Video compression remains usable without pyvips.

JPEG inputs produce JPEG at quality 85. HEIC inputs produce HEIC (HEVC) at libheif quality 50, because a JPEG copy of a HEIC photo is almost always larger; this needs libheif's x265 encoder plugin, and HEIC files are reported as skipped without it. PNG and lossless WebP produce lossless WebP with exact alpha pixels; lossy WebP stays lossy WebP at quality 80. Dimensions are retained. HEIC auxiliary images (depth maps, HDR gain maps) are not carried over. EXIF orientation is applied to pixels and normalised. Supported EXIF/XMP/ICC metadata is retained by libvips, including location information when present; original modification time is retained. This is not a metadata scrubber. Validation checks full decoding, dimensions/channels, orientation, ICC/XMP and the original capture-date field when present; lossless WebP also gets a pixel comparison. It does not guarantee preservation of every vendor metadata tag.

Animated/multi-image inputs, unsupported colour spaces, high-bit-depth/HDR images and photos over 100 megapixels are skipped. Larger results are discarded. Several photos are processed at once (about half the CPU cores, at most four), each in its own worker process; videos then run one at a time because FFmpeg already uses every core. Photos use stage progress (0%, validation, complete), with cancellation terminating the isolated worker. Existing output names receive numeric suffixes. Test representative phone photos before using a large batch.

## Quality and NVIDIA encoding

Select High Quality, Balanced (default), or Small Size before starting. CPU video CRF values are 18/23/28 (H.264) and 22/26/30 (HEVC for HDR); NVIDIA CQ values are 19/23/28; JPEG qualities are 92/85/75; HEIC qualities are 60/50/40; lossy WebP qualities are 90/80/70. These are starting settings, not equivalent quality across encoders or guaranteed savings. **Keep outputs at least N% smaller** (default 5%, range 0–50%) discards outputs that save less, because re-compressing for a tiny saving costs quality; such files are reported as "only X% smaller" and logged as No reduction. PNG and lossless WebP stay lossless in every preset. Resolution is unchanged.

Video encoder choices: CPU H.264, NVIDIA H.264, NVIDIA HEVC. Photos always use CPU. NVIDIA selection performs a cancellable 15-second-limited real encode probe once per batch. If the probe fails, the visible encoder note explains the CPU H.264 fallback (including when HEVC was selected). A later per-file failure is reported without automatic retry. HEVC outputs use the `hvc1` tag that Apple players require; playback still depends on your player. HLG HDR videos always use HEVC Main10 (NVIDIA HEVC when selected, otherwise CPU x265, which is slower), because H.264 cannot keep 10-bit HDR. For iPhone Dolby Vision videos, the HLG base picture is kept and the Dolby Vision layer is dropped. No AV1 option is offered.

The probe and all processing run off the UI thread; controls are locked for the batch. GPU encoding still uses CPU decoding and validation. CI tests fallback with simulated failures and real CPU encoding; real NVENC, driver compatibility, quality and performance must be checked on the target laptop.

## Batch results and release status

Overall progress weights each queued file equally, so it is not a time estimate. The final summary shows saved outputs, no-reduction results, files already done in an earlier batch, unsupported (skipped) files, real failures, cancellations and files not processed. Reduction percentages use only successfully saved files. Originals remain on disk, so these figures do not represent space already freed. Long paths are shortened in the middle so file names stay visible; full error/output paths are available in table tooltips. **Open output folder** opens the destination in your file manager.

Before each file, the destination needs twice the source size plus 64 MiB free and must be writable. Space can still run out during work. exFAT/FAT32 drives and other destinations without hard links are supported: the output name is claimed exclusively and the finished file is renamed onto it, so an existing file is never replaced.

## Output folder layout and results log

Files from an added folder keep their layout under a folder with the same name, for example `Output/Phone/DCIM/100APPLE/IMG_0001-compressed.jpg`; individually added files go directly in the output folder. Imported folders with the same name share an output folder, and clashing names get numeric suffixes.

Each batch writes `mediashrink-results-<date>-<time>.csv` to the output folder (UTF-8, opens in spreadsheet apps). It lists every queued original with its output file, sizes, saving and result (Saved, No reduction, Skipped, Failed, Cancelled or Not processed). Use it to check which output belongs to which original before you remove any original yourself.

**Skip files already compressed into this output folder** (on by default) reads the earlier results logs in the output folder. An original is skipped when a log lists it as saved, no reduction or already done, its size is unchanged, and its saved output still exists. This lets you re-add a phone folder later and compress only the new files. Untick it to compress everything again, for example with a different quality preset. Deleting or moving the results logs makes MediaShrink forget earlier batches. See [release readiness](docs/RELEASE.md) for interruption behavior, native acceptance checks and the AppImage assessment. CI provides Python package artifacts; no self-contained app or public release is published yet.
