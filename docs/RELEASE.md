# Release readiness and packaging decision

This is a development build, not an accepted public release. The automated implementation milestones are present; the target-machine checks below remain outstanding.

## Build artifacts

CI builds a Python wheel and source archive and uploads them for inspection. They require Python and separately installed Qt, FFmpeg and libvips dependencies. They are not AppImages. Use README's native Arch setup for testing.

AppImage assessment: defer bundling until the native Omarchy build has passed the checks below. A self-contained image must account for the photo subprocess using the correct Python environment, Qt Wayland plugins, external FFmpeg/libvips codec support, and host NVIDIA driver compatibility. A wheel renamed to AppImage would not meet these requirements.

Before distributing a bundled build, choose a project license (none is currently declared), inventory exact dependency versions and license files, review redistribution requirements for the actual FFmpeg/libvips codec builds and Qt components, and include required notices/source arrangements. No bundled-distribution compliance claim is made by this PR.

## Required target-machine checks

Record the commit, Omarchy version, NVIDIA driver and FFmpeg/libvips versions with results:

- [ ] Install and launch from a clean native environment; verify dialogs, resizing and Wayland scaling.
- [ ] Compress representative phone JPEG/PNG/WebP/HEIC samples; check orientation, colours, alpha, dates and expected metadata.
- [ ] Compare CPU and NVIDIA H.264/HEVC outputs at all presets, including sound and full playback.
- [ ] Confirm unsupported HDR/rotated/extra-stream videos are reported clearly.
- [ ] Process a large mixed batch; verify totals and errors. Savings measure output reduction, not disk space freed.
- [ ] Cancel during encoding and close during work; originals and previous successful outputs must remain.
- [ ] Test insufficient space, unavailable destination and filename collisions on the intended storage device.
- [ ] Test the exact proposed packaged artifact before publishing any release.

## Interruption and storage behavior

Jobs run sequentially. Before each encode, the destination must have twice the current source size plus 64 MiB free and must pass a write/hard-link probe. This conservative estimate is not a reservation; another process or a larger temporary encode can still exhaust storage. Such failures are reported and normal exception/cancellation cleanup removes that job's temporary directory.

The queue and results are session-only. A power loss or force-kill may leave a `.mediashrink-*` temporary directory in the output location. No automatic deletion sweep is performed: after confirming that no MediaShrink process is running, inspect and remove only leftover temporary directories. Completed outputs remain valid, separately named files. Restarting a batch can produce additional numbered copies.

Next work is target-machine acceptance and any resulting fixes, followed by packaging. Do not call milestone 6 fully accepted or publish a release until that evidence exists.
