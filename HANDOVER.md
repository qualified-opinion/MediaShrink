# Handover

## Current milestone

Milestone 1: project shell. The native window opens with an empty queue and a disabled compression button. It does not scan, encode, read or write media, or probe hardware.

## Validation

CI runs the offscreen Qt startup/close test and builds the Python source archive and wheel on Python 3.11 and 3.13. This does not validate Wayland integration or GPU encoding.

## Next

After the project-shell PR is merged, implement milestone 2 from docs/ROADMAP.md on a new branch. Keep import responsive and verify recursive scans, unsupported files, duplicate paths, cancellation and source/destination overlap.

## Manual checks remaining

Open the installed shell under Omarchy/Hyprland and check window scaling, text, resizing and closing. FFmpeg, libvips and NVIDIA runtime integration are future milestones. No AppImage or usable compressor is shipped yet.
