# MediaShrink

An offline Linux desktop app for batch photo and video compression, targeting Omarchy (Arch Linux) and optional NVIDIA acceleration.

**Current status: desktop shell only.** The window opens, but importing and compressing media are not implemented yet. No media is accessed or modified by this preview.

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

FFmpeg/libvips are not needed for this shell. NVIDIA functionality must eventually be tested with a real encode on the target laptop. See [the roadmap](docs/ROADMAP.md) and [handover](HANDOVER.md) for the next steps.
