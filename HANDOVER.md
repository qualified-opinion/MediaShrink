# Handover

Milestones 1–4 merged; milestone 5 adds quality presets and NVIDIA H.264/HEVC selection. Batch settings are captured before processing and controls locked. NVIDIA uses a real short encode probe with a 15-second timeout in the worker. Probe failure visibly falls back to CPU H.264; cancellation propagates without fallback. Later per-file failures are reported, not retried. Photos use CPU and PNG/WebP remain lossless in every preset. Quality values are documented in README.

Validation: existing real synthetic CPU video/photo tests plus mocked NVENC success, failure, cancellation, timeout configuration and CPU bypass. Real GPU encoding cannot be validated here and remains a target-laptop check. Compare representative videos across presets before relying on quality/size tradeoffs. Source/wheel build and both CI matrix checks required.

Next: milestone 6 release readiness: aggregate progress/savings, failure reporting, disk-space/interruption checks, native Omarchy tests, then assess AppImage packaging and dependency licensing. Existing exclusions for HDR/rotation/extra video streams and unsupported photos still apply. Do not merge automatically.
