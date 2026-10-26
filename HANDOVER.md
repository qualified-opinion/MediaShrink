# Handover

Milestones 1–5 merged. Milestone 6 implementation adds overall per-file-weighted progress, structured batch counts and measured savings, conservative disk-space/write preflight for both engines, and downloadable CI Python packages. Savings refer to successful outputs only; originals remain. Cancellation preserves completed outputs and leaves unprocessed items counted separately. Starting another batch resets table results.

Acceptance fixes from code review (this branch):
- Phone videos: portrait/rotated videos are rotated in the pixels; timecode and camera/GPS data tracks are dropped instead of skipping the file; HLG HDR (iPhone default, including Dolby Vision profile 8.4) is encoded as 10-bit HEVC with HLG tags. HDR10/PQ, mirrored video, subtitles and extra audio/video streams remain skipped. HEVC outputs carry the Apple `hvc1` tag.
- Output layout: files from an imported folder keep their subfolders under the folder's name, and every batch writes a CSV results log mapping each original to its output and result.
- Photos: HEIC stays HEIC (JPEG copies were almost always larger and discarded); lossy WebP stays lossy. HEIC output needs libheif's x265 encoder and is reported as skipped without it.
- Storage: destinations without hard links (exFAT/FAT32) are supported by claiming the output name exclusively and renaming onto it; existing files are still never replaced.

Validation includes synthetic real media tests (portrait, timecode track, HLG HDR, HEIC, lossy WebP), a simulated no-hard-link destination, low-space cleanup, mixed success/no-reduction/failure totals, results-log contents and cancellation counts. Run the full unittest suite and package build. Native Omarchy/RTX 3050/HEIC/exFAT acceptance and real iPhone/Android media cannot be tested in this environment.

Second round of review fixes:
- Long encodes: ffmpeg progress output is parsed but no longer stored, so the 4 MB output cap only applies to commands whose output is read (ffprobe, photo worker).
- Audio: AAC is copied; other audio becomes AAC at no more than the source bitrate (32–192 kbps).
- Totals separate unsupported (skipped) files from real failures, and count files already done.
- Missing FFmpeg gives an install instruction instead of a raw "No such file" error.
- Re-runs skip originals that earlier results logs in the output folder record as done (same size, output present); a checkbox, on by default, turns this off.

Final round of review improvements:
- Minimum saving setting (default 5%): outputs saving less are discarded and reported as "only X% smaller".
- Photos run in parallel (about half the cores, max four) on worker threads, each with its own libvips subprocess; results are recorded on the batch thread. Videos follow one at a time. Overall progress never moves backwards.
- File types: .m4v, .3gp, .avi (Motion JPEG 4:2:2 is accepted and output as 4:2:0) and .heif (output .heic).
- Window: remove selected rows (button or Delete), drag-and-drop import, Open output folder, middle-elided paths, stretchable status column, two-row settings, scrolling content at small sizes, encoder note reset on Clear queue, progress bar accessible name per mode.

Dependency note: PySide6 6.12.0 loses a reference to `True` on every signal emit; on Python 3.11 this crashes the app (and CI) after a few thousand emits. pyproject excludes 6.12.0 on Python < 3.12 only; revisit when a fixed release appears.

All review items are addressed. Remaining work is the target-machine acceptance checklist in docs/RELEASE.md, then packaging.

See docs/RELEASE.md for the packaging assessment, license inventory decision, interruption behavior and explicit manual acceptance checklist. AppImage and public release are deferred until native acceptance and an actual packaged artifact test. Milestone 6 is implementation-complete but acceptance remains open. Next: target-machine acceptance. Do not merge or publish automatically.
