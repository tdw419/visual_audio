#!/usr/bin/env python3
"""BK-58 mouse-legs RED-first neuter (builder af3e, 2026-10-01).

Serves a NEUTERED copy of build_map_viewer.html (mousemove pick math broken:
cell coordinates report a 4-cell offset, so the pick lands on the wrong cell /
no cell), and asserts the M1 hover leg + M2 click leg FAIL against it while the
pristine tree passes. Run BEFORE the main legs to prove the legs discriminate.

Usage: python3 probe_bk58_mouse_red_af3e.py <cdp_port>
Assumes: the served docroot is the repo root on :8091 and this script may
temporarily swap tools/build_map_viewer.html (restored in finally).
"""
import json
import shutil
import subprocess
import sys
import time
import urllib.request

PORT = sys.argv[1] if len(sys.argv) > 1 else "9222"
HTML = "tools/build_map_viewer.html"
MARK = "      const mouseX = (e.clientX - rect.left - panX) / zoom;"
# Shift +5 (not +4 / +4.004): Chromium integer-truncates the dispatched
# event's clientX (measured live: tooltip.left = "421px" from clientX+16 with
# clientX 405.347 -> e.clientX arrived as 405). At panX=403.5, zoom=0.4619,
# the truncated map x is 3.247, so a +4 shift lands at 7.25 — STILL cell 0,
# RED check vacuous. +5 puts map x at 8.25 (or 8.247 truncated) -> cell (1,0)
# deterministically in both the truncated and non-truncated worlds.
NEUTER = "      const mouseX = (e.clientX - rect.left - panX) / zoom + 5;"


def served_url():
    return "http://127.0.0.1:8091/tools/build_map_viewer.html"


def main():
    src = open(HTML).read()
    assert MARK in src, "marker not found in viewer html"
    assert NEUTER not in src
    try:
        open(HTML, "w").write(src.replace(MARK, NEUTER))
        # reuse the main legs probe against the neutered tree
        r = subprocess.run(
            [sys.executable, ".builder_queue/probe_bk58_mouse_legs_af3e.py", PORT],
            capture_output=True, text=True, timeout=180)
        print(r.stdout[-2000:])
        print(r.stderr[-500:])
        # RED expectation: M1 and M2 fail (hover pick broken), M3 unaffected,
        # M4 may pass either way (broken math ALSO clears or mis-picks).
        m1 = "FAIL M1-hover-pick" in r.stdout
        m2 = "FAIL M2-click-drawer" in r.stdout
        total = "SUMMARY:" in r.stdout
        print("\nRED-CHECK:", "M1 FAIL:" , m1, "M2 FAIL:", m2,
              "probe-completed:", total, "exit:", r.returncode)
        return 0 if (m1 and m2 and total and r.returncode == 1) else 1
    finally:
        open(HTML, "w").write(src)


if __name__ == "__main__":
    raise SystemExit(main())
