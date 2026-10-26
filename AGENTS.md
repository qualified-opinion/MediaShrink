# Working on MediaShrink

- Read README.md, HANDOVER.md, and docs/ROADMAP.md before making changes.
- Keep scope to offline photo/video compression on Linux. No accounts or telemetry.
- Work on one roadmap milestone per branch and PR against main. Do not merge automatically.
- Never overwrite or delete source media. Use synthetic fixtures for tests.
- Keep the GUI responsive; media processing must run outside the UI thread.
- Run `python -m unittest discover -s tests -v` with `QT_QPA_PLATFORM=offscreen` and `python -m build` for code changes.
- Record completed work, limitations, and the next milestone in HANDOVER.md.
