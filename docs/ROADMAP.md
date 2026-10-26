# Compression-only roadmap

Target: Omarchy / Arch Linux, including an RTX 3050 laptop. All processing offline.
Each milestone is a separate branch and PR; GitHub assigns actual PR numbers.

Progress: milestones 1–5 merged. Milestone 6 implementation is in the release-readiness PR; native acceptance and packaged release remain open (see RELEASE.md).

1. **Project shell** — Python package, native PySide6 window, headless startup CI, documentation.
2. **Batch selection** — file/folder import, recursive scan outside the UI thread, supported-format filtering, duplicate path prevention, destination selection. Never write media during import.
3. **Video engine** — FFprobe analysis and CPU FFmpeg encoding for MP4/MOV/MKV; background jobs, progress and cancellation. Write temporary output only in the destination; validate before publishing. Keep originals and discard larger results. Explicitly skip unsupported HDR/streams until handled safely.
4. **Photo engine** — libvips compression for JPEG/PNG/WebP/HEIC, capability detection, orientation and metadata policy, animation handling. Reuse safe output validation; skip unsupported inputs explicitly.
5. **GPU and presets** — High Quality/Balanced/Small Size, runtime NVENC encode probe, H.264/HEVC, clear CPU fallback. No AV1 encoding through RTX 3050. Compare representative synthetic media; savings are never guaranteed.
6. **Release readiness** — aggregate progress/savings, failure reporting, collision/disk-space/interruption checks, Omarchy manual testing, then evaluate AppImage packaging and dependency licensing. Publish only after actual artifact testing.

Safety is introduced with each processing engine, not deferred to release. Outputs always go to a separate destination. No automatic deletion or replacement of originals.

Not in version 0.1: duplicate discovery, media organization, cloud services, accounts, telemetry, automatic original deletion. Queue persistence and comparison previews can be considered later.
