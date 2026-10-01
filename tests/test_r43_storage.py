"""R4.3 gate: storage — block device with the writeback contract, ENOSPC-safe.

PRODUCT_ROADMAP.md:75 (R4.3). The probe (.builder_queue/
probe_r43_storage.py) is the deliverable; these legs drive it as a
subprocess so the exit contract (GREEN 0 / RED 1) is what is gated,
plus one in-process atomicity leg.

Legs:
  1. GREEN: probe exits 0 — the guest storage client (GlyphCPUv2 CPU
     oracle) services 10 block jobs through the request mailbox; 6
     sectors persist to the host backing file with valid per-sector
     checksums; the sector-3 read-back is word-exact; the
     out-of-range write returns ENOSPC and the guest CONTINUES; the
     committed data is intact after the ENOSPC attempt.
  2. RED / discriminating: --no-flush exits 1 — the seat skips the
     writeback entirely and the host-side persistence check REJECTS
     (backing file missing) — the writeback contract is load-bearing.
  3. RED / discriminating: --torn-block exits 1 — ONE byte of one
     committed sector flipped in the backing file post-write is
     REJECTED by the per-sector checksum (torn-write detection).
  4. RED / discriminating: --corrupt-verify exits 1 — the verifier
     rejects a good run under corrupted expectations (it is not a
     rubber stamp).
  5. Atomic writeback (in-process): the backing file is written via
     tmp + os.replace; a leftover .tmp from an interrupted write is
     ignored on read and the committed container is intact — the
     crash-mid-write analogue from the R3.2 container pattern.

What this does NOT prove: no real block hardware (the device channel
is the mailbox ABI + a host file, not virtio-blk); NO WGSL shader-path
leg (request servicing needs a per-step host hook — the same measured
gap R4.1 recorded; run_wgsl runs to HALT in one call); no filesystem
layer (raw block device only — no names, no directories); sector
payload exercises DATA0 (one word per sector) — a full multi-word
sector is the same loop with more guest stores, not a new mechanism;
no rate or floor claims.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools"), str(_REPO / ".builder_queue")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PROBE = _REPO / ".builder_queue" / "probe_r43_storage.py"


def _run_probe(*flags: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(PROBE), *flags],
                       capture_output=True, text=True, timeout=300)
    return r.returncode, (r.stdout + r.stderr).strip()


def test_r43_green_exit_contract():
    rc, out = _run_probe()
    assert rc == 0, f"probe exit {rc}: {out[-400:]}"
    assert "STORAGE: MATCH" in out
    assert "committed=6" in out


def test_r43_no_flush_rejected():
    rc, out = _run_probe("--no-flush")
    assert rc == 1, f"vacuous: no-flush exit {rc}: {out[-400:]}"
    assert "data loss detected" in out


def test_r43_torn_block_detected():
    rc, out = _run_probe("--torn-block")
    assert rc == 1, f"vacuous: torn-block exit {rc}: {out[-400:]}"
    assert "torn write detected" in out


def test_r43_corrupt_verify_rejected():
    rc, out = _run_probe("--corrupt-verify")
    assert rc == 1, f"vacuous: corrupt-verify exit {rc}: {out[-400:]}"
    assert "correct discrimination" in out


def test_r43_atomic_writeback_survives_interrupted_tmp():
    """Crash-mid-write analogue: a stale .tmp is ignored; the committed
    container is readable and checksum-clean."""
    import tempfile

    import probe_r43_storage as P
    with tempfile.TemporaryDirectory() as d:
        backing = Path(d) / "blockdev.gbd"
        sectors = {0: 0xAAA00001, 3: 0xBBB00008, 7: 0xCCC00080}
        P._write_backing_file(backing, sectors)
        stale = backing.with_suffix(".tmp")
        stale.write_bytes(b"GARBAGE-FROM-AN-INTERRUPTED-WRITE" * 16)
        got = P._sectors_from_file(backing)   # must ignore the .tmp
        for s, w in sectors.items():
            data, csum = got[s]
            assert data[0] == w
            assert csum == (sum(data)) & 0xFFFFFFFF
