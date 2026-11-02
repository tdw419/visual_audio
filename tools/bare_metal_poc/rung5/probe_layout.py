#!/usr/bin/env python3
"""Rung-5 medium corruption archaeology probe.

Q1: does the guest decode OUR stage2.bin byte-exactly when stage1's
    EXPECTED_CRC is computed from OUR stage2.bin? (probe_dump_run.py
    answered YES for probe_dump.bin: dump byte-exact, CRC PASS.)
Q2: with stage2.bin = our REAL stage2 (pad -> 65536, consts regenerated),
    does the guest PASS? If the guest FAILS with a CRC that differs, the
    scatter fault is data-dependent: something in the payload itself.
    Candidate mechanism: the ATA write-cache/flush or int13 WRITE in an
    earlier boot; but a FRESH encode boots clean in rung-4. OUR rung-5
    encode differs from rung-4's in ONE way: img2 planes at LBA 129+.
    stage1 reads ONLY [1,128]. So candidate 2: DMA boundary / sectors
    129+ influence? Probe: encode WITHOUT img2 (rung4-style, but with
    rung-5 stage2.bin) and boot. PASS there + FAIL with img2 = medium
    layout interaction; PASS in both = earlier build dirt.
"""
import json
import shutil
import subprocess
import sys

MODE = sys.argv[1]  # "with_img2" | "no_img2"

# rebuild stage2.bin + consts from our real stage2 code
subprocess.run([sys.executable, "rung4_pad.py", "65536", "stage2_code.bin",
                "stage2.bin"], check=True)
subprocess.run([sys.executable, "rung4_consts.py"], check=True)
subprocess.run(["nasm", "-f", "bin", "stage1.asm", "-o", "stage1.bin"], check=True)

if MODE == "with_img2":
    enc = ["stage1.bin", "stage2.bin", "img2.bin", "rung5_probe2.png",
           "rung5_probe2.raw", "rung5_probe2_meta.json"]
else:
    # rung-4 style: two-image encode with a ZERO img2 is still 3-arg, so
    # emulate no-img2 by encoding with rung4_codec.py (4-plane stage2 only)
    enc = None

if enc:
    subprocess.run([sys.executable, "rung5_codec.py", "encode", *enc],
                   check=True, stdout=subprocess.DEVNULL)
    raw = "rung5_probe2.raw"
    meta = "rung5_probe2_meta.json"
else:
    subprocess.run([sys.executable, "../rung4/rung4_codec.py", "encode",
                    "stage1.bin", "stage2.bin", "rung5_probe2.png",
                    "rung5_probe2.raw", "rung5_probe2_meta.json"],
                   check=True, stdout=subprocess.DEVNULL)
    raw = "rung5_probe2.raw"
    meta = "rung5_probe2_meta.json"

print("meta payload_crc32:", json.load(open(meta))["payload_crc32"])
subprocess.run(["timeout", "25", "qemu-system-x86_64",
                "-drive", f"file={raw},format=raw,if=ide",
                "-display", "none", "-no-reboot",
                "-serial", "file:serial_probe2.log"], check=False)
print(open("serial_probe2.log", "rb").read().decode(errors="replace"))
