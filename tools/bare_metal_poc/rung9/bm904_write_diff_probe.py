#!/usr/bin/env python3
"""BM904 guest write-side pixel diff (inverse provenance gate).

Brief: .builder_queue/brief_bm904_guest_write_diff.md (contract-complete,
commits 2fc14918 + ac1ce868). BM903 proved the READ direction (guest file ==
pixel reconstruction == /peek). BM904 closes the WRITE direction: the guest
writes 256 random bytes at a known offset of a preallocated probe file, and
the host must predict EXACTLY which pixels change — turning correctness
(yes/no) into a live FS-block->pixel mapping tool (where).

Method (per brief):
  1. fallocate BEFORE writing -> extents known before data exists (kills the
     ext4 delayed-alloc chicken-and-egg).
  2. snapshot: decode affected frame PNGs to RGBA arrays (decoded level,
     never PNG bytes).
  3. guest writes 256 random bytes (guest /dev/urandom, saved guest-side,
     content retrieved host-side via a read-only base64 cat) at a known
     offset via dd conv=notrunc + sync.
  4. barrier: compact_journal fold + frame-mtime wait (Container.barrier).
  5. diff + assert: changed-pixel set (decoded, any-channel) must equal the
     set PREDICTED from the retrieved random bytes mapped through the chain
     (logical block -> extent -> physical block -> disk byte -> frame/x/y/ch)
     against the snapshot's actual old pixel values, plus measured control
     noise: |changed \\ predicted| <= |control noise| on the same frames
     (exact equality asserted when the control floor is zero).
  6. control leg (noise floor): identical snapshot/barrier/decode cycle with
     NO guest write.
  7. R1 (measured, not forced): pre-writeback /peek at the first written
     disk byte vs the PNG decode — record which plane leads; a finding either
     way, never tuned.
  8. R2 sensitivity: host paints one byte of the written region back
     differing (livemap_probe conventions), re-decode must catch EXACTLY
     that channel; restore, re-verify byte-identical.
  9. cleanup: guest rm + sync.

Survives-the-shim test (brief endgoal section): the deliverable here is the
medium contract — address chain + decoded-pixel diff primitive + control-leg
noise-floor method. R1 is shim-forensics and is measured, not deepened.

Self-check (non-vacuity, deterministic, no guest): --selfcheck drives the
predictor + comparator against a synthetic frame and proves the gate can go
RED (a neutered diff and a corrupted prediction are both caught).

Usage: python3 tools/bare_metal_poc/rung9/bm904_write_diff_probe.py
Exit 0 = all legs green. Artifacts: output/bm904_*.json
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools" / "pixel_container"))

from locate_in_container import (  # noqa: E402
    Container, DEFAULT_CONTAINER, DEFAULT_SSH, BYTES_PER_FRAME, BS,
    disk_byte_of, guest_meta,
)
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

ART = REPO / "output"
PROBE = "/var/tmp/bm904_probe.bin"
RAND = "/var/tmp/bm904_rand.bin"
FRAME_PX = 4096
WRITE_LEN = 256
FRAME_BYTES = 64 * 1024 * 1024


def sh(cmd: str, timeout: int = 90) -> str:
    r = subprocess.run(DEFAULT_SSH + [cmd], capture_output=True, text=True,
                       timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"guest ssh failed rc={r.returncode}: {cmd!r} "
                           f"{r.stderr[:300]}")
    return r.stdout


def decode_frame(fno: int) -> np.ndarray:
    a = np.asarray(Image.open(DEFAULT_CONTAINER / f"frame_{fno:05d}.png"),
                   dtype=np.uint8)
    assert a.shape == (4096, 4096, 4), f"unexpected frame shape {a.shape}"
    return a


# ---------------------------------------------------------------- mapping ---

class Chain:
    """File logical offsets -> disk bytes -> frame/x/y/channel (locked ABI,
    imported from locate_in_container — never re-derived here)."""

    def __init__(self, meta: dict):
        self.meta = meta
        self.v = meta["vda3_start_sectors"]
        self.extents = meta["extents"]  # sorted by logical_first (filefrag -v)

    def disk_byte(self, logical_offset: int) -> int:
        lb = logical_offset // BS
        for e in self.extents:
            if e["logical_first"] <= lb < e["logical_first"] + e["blocks"]:
                pb = e["physical_first"] + (lb - e["logical_first"])
                return disk_byte_of(pb, self.v) + logical_offset % BS
        raise RuntimeError(f"offset {logical_offset} not in any extent")

    def pixel(self, disk_byte: int) -> tuple[int, int, int, int]:
        fno = 1 + disk_byte // FRAME_BYTES
        intra = disk_byte % FRAME_BYTES
        return fno, (intra % (FRAME_PX * 4)) // 4, intra // (FRAME_PX * 4), intra % 4


def predict_changes(chain: Chain, offset: int, new_bytes: bytes,
                    snap: dict[int, np.ndarray]) -> set[tuple[int, int, int]]:
    """Exact predicted changed-pixel set: every written byte mapped through
    the chain, compared against the snapshot's actual pixel values."""
    predicted: set[tuple[int, int, int]] = set()
    for i, b in enumerate(new_bytes):
        fno, x, y, ch = chain.pixel(chain.disk_byte(offset + i))
        old = snap[fno][y, x].copy()
        new = old.copy()
        new[ch] = b
        if not np.array_equal(old, new):
            predicted.add((fno, int(y), int(x)))
    return predicted


def changed_pixels(frames: list[int],
                   a: dict[int, np.ndarray], b: dict[int, np.ndarray]
                   ) -> set[tuple[int, int, int]]:
    out: set[tuple[int, int, int]] = set()
    for f in frames:
        d = np.any(a[f] != b[f], axis=2)
        for y, x in np.argwhere(d):
            out.add((f, int(y), int(x)))
    return out


def selfcheck() -> None:
    """Deterministic non-vacuity: the predictor/comparator must be able to
    fail. Synthetic 1-frame snapshot, 3-byte write, then two corruptions."""
    frame = np.zeros((FRAME_PX, FRAME_PX, 4), dtype=np.uint8)
    snap = {5: frame}
    chain = Chain({"vda3_start_sectors": 0,
                   "extents": [{"logical_first": 0, "physical_first": 65536,
                                "blocks": 16}]})
    # bytes 0..2 -> disk bytes 65536*4096 = 256MiB.. -> frame 1+256MiB/64MiB=5,
    # intra 0 -> pixel (x=0,y=0,channel R)
    fno, x, y, ch = chain.pixel(chain.disk_byte(0))
    assert (fno, x, y, ch) == (5, 0, 0, 0), (fno, x, y, ch)
    pred = predict_changes(chain, 0, b"\x01\x02\x03", snap)
    assert pred == {(5, 0, 0)}, pred          # 3 bytes, one pixel
    empty_a = {5: frame}
    empty_b = {5: frame.copy()}
    assert changed_pixels([5], empty_a, empty_b) == set()
    b_changed = {5: frame.copy()}
    b_changed[5][0, 0, 0] = 1
    assert changed_pixels([5], empty_a, b_changed) == {(5, 0, 0)}
    # RED: a corrupted address chain (off-by-one physical block) must be
    # caught by the comparator — the load-bearing property for the real gate
    bad_chain = Chain({"vda3_start_sectors": 0,
                       "extents": [{"logical_first": 0, "physical_first": 65537,
                                    "blocks": 16}]})
    assert changed_pixels([5], empty_a, b_changed) != predict_changes(
        bad_chain, 0, b"\x01\x02\x03", snap)
    print("SELFCHECK PASS: predictor/comparator discriminate (synthetic RED shown)")


# ------------------------------------------------------------------- gate ---

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--skip-r1", action="store_true",
                    help="skip the shim-forensics peek leg")
    ap.add_argument("--mutant", action="store_true",
                    help="corrupt the predictor chain (physical block +1 on "
                         "extent 0) — the gate MUST go RED on the first "
                         "treatment leg; proves the assertion is load-bearing")
    args = ap.parse_args()
    selfcheck()
    if args.selfcheck:
        return 0

    ART.mkdir(exist_ok=True)
    results: dict = {"legs": {}}

    # ---------- setup: preallocate, extents BEFORE data ----------
    sh(f"rm -f {PROBE} {RAND} && fallocate -l 67108864 {PROBE} && "
       f"dd if=/dev/zero of={PROBE} bs=4096 count=1 conv=notrunc seek=0 && sync")
    meta = guest_meta(PROBE, DEFAULT_SSH)
    chain = Chain(meta)
    if args.mutant:  # RED probe: corrupt the chain, gate must fail
        chain.extents[0]["physical_first"] += 1
        print("MUTANT: predictor chain corrupted (extent0 physical_first +1)")
    size = meta["size"]
    assert size >= 67108864, size
    frames = sorted({chain.pixel(chain.disk_byte(o))[0]
                     for o in (0, size - 1)})
    # every extent's span, in case of fragmentation
    for e in meta["extents"]:
        for off in (e["logical_first"] * BS,
                    (e["logical_first"] + e["blocks"]) * BS - 1):
            frames.append(chain.pixel(chain.disk_byte(off))[0])
    frames = sorted(set(frames))
    assert len(frames) >= 2, f"expected frame-crossing file, got frames={frames}"
    print(f"probe: {PROBE} size={size} extents={len(meta['extents'])} "
          f"frames={frames} vda3_start={chain.v}")
    results["setup"] = {"size": size, "extents": len(meta["extents"]),
                        "frames": frames, "vda3_start_sectors": chain.v}

    # sanity: preallocated region decodes as zeros through the pixel chain
    c = Container(DEFAULT_CONTAINER)
    head = c.read(chain.disk_byte(0), 32)
    assert head == b"\x00" * 32, f"prealloc region not zero in pixels: {head!r}"

    def snapshot() -> dict[int, np.ndarray]:
        return {f: decode_frame(f) for f in frames}

    def barrier() -> None:
        ok = c.barrier()
        results["legs"].setdefault("barrier_fails", [])
        if not ok:
            results["legs"]["barrier_fails"].append(time.time())

    # ---------- control leg: noise floor, NO guest write ----------
    a = snapshot()
    barrier()
    b = snapshot()
    noise = changed_pixels(frames, a, b)
    results["legs"]["control"] = {"changed": len(noise),
                                  "pixels": sorted(map(list, noise))[:20]}
    print(f"control noise floor: {len(noise)} px on frames {frames}")

    # ---------- treatment legs ----------
    # offsets: mid-frame-0 and a computed frame-boundary crosser
    off_mid = 32 * 1024 * 1024
    file_start_db = chain.disk_byte(0)
    boundary = ((file_start_db // FRAME_BYTES) + 1) * FRAME_BYTES
    to_b = boundary - file_start_db          # bytes from file start to boundary
    off_cross = max(0, to_b - 128)           # straddle: start near, cross mid-write
    assert 0 <= off_cross and off_cross + WRITE_LEN <= size
    offsets = [off_mid, off_cross]
    assert off_cross + WRITE_LEN > to_b > off_cross, "must cross boundary"

    treatment_noise_total = 0
    for run, off in enumerate(offsets, 1):
        # guest writes 256 fresh random bytes, saved guest-side; content
        # retrieved host-side READ-ONLY (base64 cat) for the exact predictor
        sh(f"dd if=/dev/urandom of={RAND} bs=1 count={WRITE_LEN} 2>/dev/null && "
           f"sync")
        b64 = sh(f"base64 -w0 {RAND}").strip()
        new_bytes = base64.b64decode(b64)
        assert len(new_bytes) == WRITE_LEN
        sha = hashlib.sha256(new_bytes).hexdigest()
        snap0 = snapshot()
        # the write
        sh(f"dd if={RAND} of={PROBE} bs=1 seek={off} conv=notrunc && "
           f"sync && dd if={PROBE} bs=1 skip={off} count={WRITE_LEN} 2>/dev/null "
           f"| sha256sum")
        quoted = sh(f"dd if={PROBE} bs=1 skip={off} count={WRITE_LEN} 2>/dev/null "
                    f"| sha256sum").split()[0]
        assert quoted == sha, f"guest readback sha mismatch: {quoted} != {sha}"
        # R1 (measured, not forced): AFTER the write, BEFORE writeback —
        # /peek serves the live disk (overlay plane), PNGs still decode the
        # pre-writeback bytes. Which plane leads is the finding.
        if not args.skip_r1:
            first_db = chain.disk_byte(off)
            try:
                from livemap_probe import evict, peek
                evict("http://127.0.0.1:8769", DEFAULT_CONTAINER)
                pk = peek("http://127.0.0.1:8769", first_db)
            except Exception as e:  # shim co-tenancy: record, never tune
                pk, peek_err = None, str(e)
            else:
                peek_err = None
            fp = chain.pixel(first_db)
            png_byte = int(snap0[fp[0]][fp[2], fp[1], fp[3]])
            results["legs"][f"r1_run{run}"] = {
                "first_disk_byte": first_db, "peek": pk, "png_byte": png_byte,
                "written_byte": new_bytes[0], "peek_error": peek_err,
                "peek_leads_png": pk == new_bytes[0] and png_byte != new_bytes[0]}
            print(f"R1 run{run}: peek={pk} png={png_byte} "
                  f"written={new_bytes[0]} (recorded, not gated)")
        barrier()
        snap1 = snapshot()
        changed = changed_pixels(frames, snap0, snap1)
        predicted = predict_changes(chain, off, new_bytes, snap0)
        extra = changed - predicted
        missing = predicted - changed
        leg = {
            "offset": off, "sha256": sha, "changed": len(changed),
            "predicted": len(predicted), "extra": len(extra),
            "missing": len(missing),
            "extra_px": sorted(map(list, extra))[:20],
            "missing_px": sorted(map(list, missing))[:20],
            "control_noise": len(noise),
        }
        if len(noise) == 0:
            leg["verdict"] = "EXACT" if not extra and not missing else "FAIL"
            ok_leg = not extra and not missing
        else:
            leg["verdict"] = "NOISE-ATTRIB" if len(extra) <= len(noise) and not missing else "FAIL"
            ok_leg = len(extra) <= len(noise) and not missing
        results["legs"][f"treatment_run{run}"] = leg
        print(f"treatment run{run}: off={off} changed={len(changed)} "
              f"predicted={len(predicted)} extra={len(extra)} "
              f"missing={len(missing)} -> {leg['verdict']}")
        if not ok_leg:
            (ART / "bm904_gate_result.json").write_text(json.dumps(results, indent=1))
            return 1
        treatment_noise_total += len(extra)

    # ---------- R2: one-byte sensitivity via host paint + restore ----------
    from livemap_probe import paint as paint_px
    # find an R-channel byte inside run2's written region
    off = offsets[1]
    target = None
    for i in range(WRITE_LEN):
        fno, x, y, ch = chain.pixel(chain.disk_byte(off + i))
        if ch == 0:
            target = (fno, x, y)
            break
    assert target, "no R-channel byte in written region?!"
    fno, x, y = target
    pre = decode_frame(fno)
    old_r = int(pre[y, x, 0])
    paint_px(DEFAULT_CONTAINER, fno, x, y, old_r ^ 0xFF)
    post = decode_frame(fno)
    diff = changed_pixels([fno], {fno: pre}, {fno: post})
    # changed_pixels yields (frame, y, x); target carries (frame, x, y)
    ok_r2 = diff == {(fno, y, x)} and int(post[y, x, 0]) == (old_r ^ 0xFF)
    paint_px(DEFAULT_CONTAINER, fno, x, y, old_r)  # restore
    post2 = decode_frame(fno)
    restored = np.array_equal(pre, post2)
    results["legs"]["r2_sensitivity"] = {
        "pixel": [fno, x, y], "old_r": old_r,
        "caught_exactly_one": ok_r2, "restored_byte_identical": restored}
    print(f"R2: paint 1 byte -> diff={sorted(diff)} catch={ok_r2} "
          f"restore={restored}")
    if not (ok_r2 and restored):
        (ART / "bm904_gate_result.json").write_text(json.dumps(results, indent=1))
        return 1

    # ---------- cleanup ----------
    sh(f"rm -f {PROBE} {RAND} && sync")
    gone = sh(f"test -e {PROBE} && echo PRESENT || echo GONE").strip()
    results["cleanup"] = {"probe": gone}
    results["verdict"] = "GATE PASS"
    (ART / "bm904_gate_result.json").write_text(json.dumps(results, indent=1))
    print(f"cleanup: {gone}")
    print("GATE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
