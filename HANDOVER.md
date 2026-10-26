# Handover

Milestone 3 adds CPU H.264/AAC MP4 compression through the queue. Processing runs in a QThread with per-file progress and cooperative cancellation. Temporary output is validated by FFprobe and a full decode, then published with a no-clobber hard link only if smaller. Original modification time is retained. Existing names receive numeric suffixes.

Limitations: HDR, rotation/side data, non-8-bit 4:2:0 video and extra streams are skipped. Photo encoding, GPU and presets remain future milestones. Destination filesystem must support hard links. Filesystem changes during processing are detected for source inode/size/mtime; filesystem calls can delay cancellation. Test native Omarchy behavior and real phone samples before relying on outputs. Metadata preservation is limited to what FFmpeg maps into MP4.

Validation: existing 15 tests plus synthetic real FFmpeg compression/collision/original-preservation, cancellation, and HDR rejection tests. Source and wheel build required; CI installs FFmpeg.

Next after merging: milestone 4, libvips photo compression with safe output validation. Do not merge automatically.
