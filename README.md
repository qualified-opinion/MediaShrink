# MediaShrink

An offline Linux desktop app for batch photo and video compression, targeting Omarchy (Arch Linux) and optional NVIDIA acceleration.

**Current status: import queue preview.** Add files or recursively scan folders, see original sizes, cancel import, clear the queue, and choose a separate output folder. Compression is not implemented yet. Import reads file information without opening media contents or modifying originals.

## Prepare a batch

1. Choose **Add files** or **Add folder** (includes subfolders).
2. Review the queue and total original size. Candidate extensions: MP4, MOV, MKV, JPEG/JPG, PNG, WebP and HEIC, regardless of letter case. The later encoding engines will validate actual formats and codec support.
3. Choose an existing output folder separate from imported folder trees. For individual files, their containing folder and its ancestors cannot be the output folder. Overlap is checked whether you select the destination before or after importing.

Import skips symlink files/folders, unsupported extensions, and duplicate absolute paths. It reports inaccessible or missing paths and continues. This is path deduplication, not content duplicate detection. The queue exists only for the current session.

**Cancel import** keeps files already discovered; **Clear queue** removes the queue and imported-folder restrictions. Scanning happens in a background thread. Closing requests cancellation and waits for the scan to stop; an in-progress filesystem operation on a stalled mount may delay cancellation. No output folders or files are created, and destination writability is not yet tested.

## Run on Omarchy / Arch

Use the distribution's Qt bindings, avoiding a separate Qt installation:

```bash
sudo pacman -Syu --needed python python-pip pyside6 git
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
python -m pip install -e . build
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

FFmpeg/libvips are not needed for the import queue. NVIDIA functionality must eventually be tested with a real encode on the target laptop. See [the roadmap](docs/ROADMAP.md) and [handover](HANDOVER.md) for the next steps.
