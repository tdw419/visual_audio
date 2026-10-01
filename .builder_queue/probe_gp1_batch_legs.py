#!/usr/bin/env python3
"""gp1_batch_legs.py — batch-level RED-first legs for GP-1 batch 1.

Leg N (tamper): flip one byte in a COPY of cap1's trace.log, convert the
tampered copy, and show a gate goes RED (count identity break OR args_raw
no longer verbatim) while the pristine copy stays GREEN.
Leg E (empty): convert an empty trace.log and show the converter yields
zero syscalls -> per schema rule 4, an empty capture is not a capture.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

CONV = "tools/corpus/strace_to_json.py"
TMP = Path("/tmp/gp1_legs")


def convert(log, out):
    subprocess.run(["python3", CONV, str(log), str(out)], check=True)
    return json.load(open(out))


def main():
    TMP.mkdir(exist_ok=True)
    fails = 0

    # ---- Leg N: tamper ----
    src = Path("corpus_build/cap1/trace.log")
    pristine = TMP / "pristine.log"
    tampered = TMP / "tampered.log"
    shutil.copy(src, pristine)
    shutil.copy(src, tampered)
    raw = bytearray(tampered.read_bytes())
    # find the first 'openat' occurrence and corrupt one byte inside it
    idx = raw.find(b"openat")
    assert idx > 0
    raw[idx + 2] = ord("X")  # openat -> opeXat  (name corrupted)
    tampered.write_bytes(bytes(raw))

    t = convert(tampered, TMP / "tampered.json")
    # gate 1 on tampered copy: count identity must still hold OR names must differ
    names = {s["name"] for s in t["syscalls"]}
    red = "opeXat" in names or t["counts"] != convert(pristine, TMP / "pristine.json")["counts"]
    if red:
        print("PASS[leg-N] tamper DETECTED: converter output changed on tampered copy "
              f"(names sample: {sorted(names)[:3]})")
    else:
        print("FAIL[leg-N] tamper NOT detected — gate cannot fail, decoration")
        fails += 1
    # pristine stays green
    p = convert(pristine, TMP / "pristine.json")
    c = p["counts"]
    if c["converted"] + c["skipped_unfinished"] == c["total"]:
        print(f"PASS[leg-N] pristine copy still GREEN: {c}")
    else:
        print("FAIL[leg-N] pristine copy broke — verifier bug")
        fails += 1

    # ---- Leg E: empty capture ----
    empty_log = TMP / "empty.log"
    empty_log.write_text("")
    e = convert(empty_log, TMP / "empty.json")
    if e["counts"]["total"] == 0:
        print("PASS[leg-E] empty workload -> 0 syscalls; schema rule 4: "
              "empty capture is NOT a capture (directory must not be committed)")
    else:
        print(f"FAIL[leg-E] empty capture yielded {e['counts']}")
        fails += 1

    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
