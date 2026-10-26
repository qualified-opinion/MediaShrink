# Handover

## Current milestone

Milestone 2: batch selection. Add multiple files or a recursively scanned folder to a read-only table model with original sizes and total bytes. Background discovery emits batches of 128 entries. Import can be cancelled; discovered files stay in the queue. Clear queue resets the paths and folder restrictions.

Destination selection requires an existing folder separate from imported trees, checked in either selection order and after resolving symlink destinations. All input symlinks are skipped. Extension matching is case insensitive. Only absolute path duplicates are skipped; there is no content duplicate detection. Missing/inaccessible paths are reported without aborting other imports. Queue state is not persisted.

No media contents are opened, no files/folders are written, and compression stays disabled. Destination permissions are not tested yet. Cancellation is cooperative; an in-progress filesystem call on a stalled mount can delay it. Closing cancels and waits asynchronously for the worker rather than destroying a running QThread.

## Validation

15 synthetic/offscreen tests cover startup, recursion, sizes, unchanged originals, filtering, repeated/overlapping selections, existing queue deduplication, symlink loops, missing paths, permission errors, bounded error reporting, cancellation, destination overlap in both orders, GUI event processing, close during import, and recovery after worker failure. CI runs on Python 3.11 and 3.13 and builds source/wheel distributions. Local checks use Python 3.12.

## Next

After merging this PR, implement milestone 3 from docs/ROADMAP.md on a new branch: FFprobe analysis and a background CPU FFmpeg engine with progress/cancellation and validated temporary output. Revalidate source/destination paths and writability at processing time; discovery checks are not a substitute for safe writes. Preserve originals, handle collisions, discard larger/invalid results, and explicitly skip unsupported HDR/streams. Use synthetic media for tests.

## Manual checks remaining

On Omarchy/Hyprland, check native file/folder dialogs (including uppercase filenames), scaling and resizing, importing a large phone backup, cancellation, and closing during a scan. Qt offscreen tests do not validate Wayland integration. No real codec/GPU tests or AppImage exist yet.
