# Handover

Milestones 1–5 merged. Milestone 6 implementation adds overall per-file-weighted progress, structured batch counts and measured savings, conservative disk-space/write preflight for both engines, and downloadable CI Python packages. Savings refer to successful outputs only; originals remain. Cancellation preserves completed outputs and leaves unprocessed items counted separately. Starting another batch resets table results.

Acceptance fixes from code review (this branch):
- Phone videos: portrait/rotated videos are rotated in the pixels; timecode and camera/GPS data tracks are dropped instead of skipping the file; HLG HDR (iPhone default, including Dolby Vision profile 8.4) is encoded as 10-bit HEVC with HLG tags. HDR10/PQ, mirrored video, subtitles and extra audio/video streams remain skipped. HEVC outputs carry the Apple `hvc1` tag.
- Output layout: files from an imported folder keep their subfolders under the folder's name, and every batch writes a CSV results log mapping each original to its output and result.
- Photos: HEIC stays HEIC (JPEG copies were almost always larger and discarded); lossy WebP stays lossy. HEIC output needs libheif's x265 encoder and is reported as skipped without it.
- Storage: destinations without hard links (exFAT/FAT32) are supported by claiming the output name exclusively and renaming onto it; existing files are still never replaced.

Validation includes synthetic real media tests (portrait, timecode track, HLG HDR, HEIC, lossy WebP), a simulated no-hard-link destination, low-space cleanup, mixed success/no-reduction/failure totals, results-log contents and cancellation counts. Run the full unittest suite and package build. Native Omarchy/RTX 3050/HEIC/exFAT acceptance and real iPhone/Android media cannot be tested in this environment.

Known limitations still open from review: very long encodes (about 4 hours of encoding time) hit the 4 MB tool-output limit in `video.run`; audio is always re-encoded to 192 kbps AAC; unsupported files are counted with failures in the on-screen totals; missing FFmpeg gives a raw "No such file" error; re-running a batch creates numbered duplicates; no minimum-saving threshold; one photo subprocess at a time.

See docs/RELEASE.md for the packaging assessment, license inventory decision, interruption behavior and explicit manual acceptance checklist. AppImage and public release are deferred until native acceptance and an actual packaged artifact test. Milestone 6 is implementation-complete but acceptance remains open. Next: the open limitations above, then target-machine acceptance. Do not merge or publish automatically.
