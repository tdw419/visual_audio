#!/usr/bin/env python3
"""Research probe (af3e, 2026-09-27): is the L1 shell's wc/head swap
refusal (glyph_l1_shell.py:505-513, '16-byte window' rationale) STALE
post-BK-24? Measure _shell_native('wc', ...) directly vs the host shim,
plus a saturation leg (stream > 256 bytes) to bound what the swap must
document. Verdicts from returned STRINGS + file bytes, never stdout."""
import sys, tempfile, hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "experiments"))

from glyph_l1_shell import GlyphL1Shell, L1Session  # noqa: E402

results = {}

with tempfile.TemporaryDirectory(prefix="b9w_") as td:
    td = Path(td)
    session = L1Session(root=td)
    shell = GlyphL1Shell(session=session)
    # fixture A: small file — wc report is short, must fit any window
    a = td / "small.txt"
    a.write_bytes(b"hello world\nsecond line here\n")
    # fixture B: >256-byte stream — bounds the ring-saturation class
    b = td / "big.txt"
    big = (b"word " * 80) + b"\n"          # 401 bytes, 81 words, 1 line
    b.write_bytes(big)
    # fixture C: multi-line large file for wc stats
    c = td / "multi.txt"
    c.write_bytes(b"".join(b"line %d\n" % i for i in range(40)))

    rel = lambda p: p.name  # session root-relative

    # 1) host shim reference for small
    results["host_wc_small"] = shell._wc(rel(a))
    # 2) native wc on small (the refused swap, exercised directly)
    try:
        results["native_wc_small"] = shell._shell_native("wc", rel(a))
    except Exception as exc:  # noqa: BLE001
        results["native_wc_small"] = f"EXC:{type(exc).__name__}:{exc}"
    # 3) native wc on the large multi-line file
    try:
        results["native_wc_multi"] = shell._shell_native("wc", rel(c))
    except Exception as exc:  # noqa: BLE001
        results["native_wc_multi"] = f"EXC:{type(exc).__name__}:{exc}"
    # 4) host reference for multi
    results["host_wc_multi"] = shell._wc(rel(c))
    # 5) native head on big (stream = 401 bytes > 256-byte ring: saturation bound)
    try:
        results["native_head_big"] = shell._shell_native("head", rel(b))
    except Exception as exc:  # noqa: BLE001
        results["native_head_big"] = f"EXC:{type(exc).__name__}:{exc}"
    # 6) native wc on big — does wc's own report (small) survive a big input?
    try:
        results["native_wc_big"] = shell._shell_native("wc", rel(b))
    except Exception as exc:  # noqa: BLE001
        results["native_wc_big"] = f"EXC:{type(exc).__name__}:{exc}"

import json  # noqa: E402
blob = json.dumps(results, indent=1, sort_keys=True)
print(blob)
md5 = hashlib.md5(blob.encode()).hexdigest()
print(f"results_md5={md5}")
