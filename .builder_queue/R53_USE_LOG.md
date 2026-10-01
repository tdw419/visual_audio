# R5.3 — The 30-day gate: use log

Gate (PRODUCT_ROADMAP.md:82): Jericho boots Glyph OS for real work
>=15 days in 30. Measured by his own report. This file is that report.

Contract: one line per real-work day. A real-work day = Jericho booted
the product and did actual work in it (not a demo, not a verification
pass). Cheap, honest, falsifiable — no tooling, no automation. A day
that produces a defect is still a real-work day; the defect becomes a
ticket, not a failed day.

Clock start: 2026-09-22 ~07:3x CDT (Jericho, in-channel).
Installer: glyphos_installer.py (6.2 MB, sha256-manifested).
Pre-use sanity (2026-09-22, two independent parties): RED leg exits 1
on corrupted manifest, GREEN integrity 21 members OK, full boot exit 0
in <3s — receipt 0x5eed0005, results {6,12,20,30} on the WGSL shader
path. Zero residue.

---

## Log

(2026-09-22 | day 1 in progress — line lands when the day's real work does)
2026-09-22 | day 1 | Jericho: sat at the interactive shell myself, typed two real requests ("list the files in my home directory", "what time is it"). Both echoed back verbatim. I don't know how to use it because there is nothing to use — the shell only repeats you, the demo is the machine talking to itself, and the compiler assumes you already speak its language. No user surface exists yet. (Diagnostic support from Hermes session, hands-on-typing and this sentence are mine.)
