#!/usr/bin/env python3
"""Non-vacuity probe for DEFECT-28 file (2): VCC encoder + round-trip legs.

(i) Neuters the new encoder (drop + SPECIAL_OFFSET so id_val = byte) and runs
    the round-trip legs, showing them RED.
(ii) Flips one byte of the input and shows the decoded payload differs
    (the round-trip is discriminating, not vacuous).
Restores tools/vcc_validate.py byte-identical (md5 verified).
"""
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
TARGET = REPO / "tools/vcc_validate.py"
PY = "/usr/bin/python3"


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def test_probe_neutered(original_content: str) -> bool:
    old = "        id_val = byte_val + SPECIAL_OFFSET\n"
    new = "        id_val = byte_val\n"
    if old not in original_content:
        print("PROBE (i) FAIL: marker not found in TARGET")
        return False

    TARGET.write_text(original_content.replace(old, new, 1))
    try:
        legs = [
            "tests/test_vcc_validation.py::TestVCCHilbertMapping::test_hilbert_round_trip_consistency",
            "tests/test_vcc_validation.py::TestVCCEncodingDecoding::test_large_payload",
        ]
        proc = subprocess.run(
            [PY, "-W", "ignore", "-m", "pytest", *legs, "-q", "-p", "no:cacheprovider"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        print(f"PROBE (i) neutered-offset round-trip legs: rc={proc.returncode} tail={tail}")

        proc_all = subprocess.run(
            [PY, "-W", "ignore", "-m", "pytest", "tests/test_vcc_validation.py", "-q", "-p", "no:cacheprovider"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        tail_all = proc_all.stdout.strip().splitlines()[-1] if proc_all.stdout.strip() else ""
        print(f"PROBE (i) neutered-offset full suite:      rc={proc_all.returncode} tail={tail_all}")

        if proc.returncode != 0 and "failed" in tail:
            print("PROBE (i) RESULT: RED (expected — dropping SPECIAL_OFFSET fails round-trip legs)")
            return True
        else:
            print("PROBE (i) RESULT: GREEN (UNEXPECTED — legs did not fail!)")
            return False
    finally:
        TARGET.write_text(original_content)


def test_probe_flip_input() -> bool:
    sys.path.insert(0, str(REPO / "tools"))
    import vcc_validate

    data_orig = bytes(range(256))
    data_flipped = bytearray(data_orig)
    data_flipped[42] ^= 0x55
    data_flipped = bytes(data_flipped)

    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f_orig, \
         tempfile.NamedTemporaryFile(mode="wb", delete=False) as f_flip, \
         tempfile.NamedTemporaryFile(suffix=".rts.png", delete=False) as f_png:
        f_orig.write(data_orig)
        f_orig.flush()
        f_flip.write(data_flipped)
        f_flip.flush()
        orig_path = f_orig.name
        flip_path = f_flip.name
        png_path = f_png.name

    try:
        vcc_validate.encode_rts_png(flip_path, png_path, grid_size=256)
        decoded = vcc_validate.decode_rts_png(png_path, grid_size=256)
        if decoded == data_flipped and decoded != data_orig:
            diff_idx = [i for i in range(len(data_orig)) if decoded[i] != data_orig[i]]
            print(f"PROBE (ii) flip-input: decoded differs from orig at index {diff_idx}, matches flipped payload")
            print("PROBE (ii) RESULT: DISCRIMINATING (1-byte input flip changes decoded payload)")
            return True
        else:
            print(f"PROBE (ii) RESULT: NOT DISCRIMINATING (decoded==data_orig: {decoded == data_orig})")
            return False
    finally:
        for p in (orig_path, flip_path, png_path):
            if os.path.exists(p):
                os.unlink(p)


def main() -> int:
    original = TARGET.read_text()
    before = md5(TARGET)
    print(f"repo file md5 before: {before}")

    success_i = False
    success_ii = False
    try:
        success_i = test_probe_neutered(original)
        success_ii = test_probe_flip_input()
    finally:
        TARGET.write_text(original)

    after = md5(TARGET)
    print(f"repo file md5 after:  {after}  identical={after == before}")
    if after != before:
        print("REPO FILE NOT RESTORED — abort")
        return 2

    if success_i and success_ii:
        print("ALL NON-VACUITY PROBES PASSED (discriminating and file restored)")
        return 0
    else:
        print("NON-VACUITY PROBE FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
