#!/usr/bin/env python3
"""Non-vacuity probe for SUITE-FIX-1 cluster (2) syscall handlers.

Neuters ONE behaviour at a time in tools/glyph_isa_v2.py, runs the corresponding
gate leg, and requires it to go RED. Restores the file byte-identical (md5 checked).
"""
import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
TARGET = REPO / "tools/glyph_isa_v2.py"
PY = "/usr/bin/python3"

PROBES = [
    (
        "FILE_READ-missing-must-return--1",
        # neuter: a missing file returns 0 instead of -1
        '\n                    print(f"[SYSCALL] FILE_READ: file not found at path at {path_addr}")\n                    return -1\n',
        '\n                    print(f"[SYSCALL] FILE_READ: file not found at path at {path_addr}")\n                    return 0\n',
        ["tests/test_glyph_file_io.py::test_syscall_file_read_not_found"],
    ),
    (
        "AUDIO_IN-must-decode-and-write-back",
        # neuter: decode steps are skipped entirely
        "                decoded = Phy16Tone.decode(audio_samples)\n",
        "                decoded = b\"\"\n",
        ["tests/test_glyph_audio_io.py"],
    ),
]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    original = TARGET.read_text()
    before = md5(TARGET)
    print(f"repo file md5 before: {before}")
    failures = 0
    try:
        for name, old, new, legs in PROBES:
            if old not in original:
                print(f"PROBE {name}: SKIP — marker not found (file changed?)")
                failures += 1
                continue
            TARGET.write_text(original.replace(old, new, 1))
            proc = subprocess.run(
                [PY, "-m", "pytest", *legs, "-q", "-p", "no:cacheprovider"],
                cwd=REPO, capture_output=True, text=True,
            )
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-1]
            verdict = "RED (expected)" if proc.returncode != 0 else "GREEN (NOT DISCRIMINATING)"
            print(f"PROBE {name}: rc={proc.returncode} {verdict} :: {tail}")
            if proc.returncode == 0:
                failures += 1
            TARGET.write_text(original)
    finally:
        TARGET.write_text(original)

    after = md5(TARGET)
    print(f"repo file md5 after:  {after}  identical={after == before}")
    if after != before:
        print("REPO FILE NOT RESTORED — abort")
        return 2
    print("PROBE RESULT:", "PASS (both probes discriminate, file restored)" if failures == 0
          else f"FAIL ({failures} probe problem(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
