# Handover

Milestones 1–3 merged; milestone 4 adds libvips photo compression to the same sequential CPU queue. JPEG/HEIC become JPEG Q85; PNG/WebP become lossless exact WebP. Orientation is applied to pixels. Supported EXIF/XMP/ICC remains, including GPS if present; original modification time is retained. Unsupported colour/depth/HDR, animations/multiple pages and >100 MP inputs are skipped. HEIC depends on the installed loader and is not guaranteed by extension alone.

Photo work runs in an isolated Python subprocess through the existing cancellable runner. Temporary output is fully decoded, dimensions/channels/orientation checked, ICC/XMP/capture date checked when present, and lossless pixels compared. Only smaller outputs are atomically published with no-clobber hard links. Existing files and originals remain intact. Hard-link-capable destination required. No promise is made for all vendor metadata. Photo progress reports stages rather than a continuous percentage.

Validation: 24 local tests cover existing import/video behavior plus synthetic alpha preservation, original bytes/mtime, collisions, rotated JPEG and capture date, animation and high-bit-depth rejection, corrupt input cleanup, cancellation and larger-result discard. CI installs system libvips and the photos extra; local tests used libvips 8.18. Source/wheel builds required. Real HEIC and native Omarchy checks remain manual.

Next after merge: milestone 5, quality presets and runtime NVIDIA NVENC probe with CPU fallback. Keep one branch/PR per milestone; do not merge automatically.
