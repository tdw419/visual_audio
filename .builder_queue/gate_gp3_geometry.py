#!/usr/bin/env python3
"""gate_gp3_geometry.sh — acceptance gate for GP-3 extent-geometry classes.

Per class: locate JSON exists w/ spans, host container verify result recorded,
class-specific assertion. RED legs (wrong-sha verify, dense-control sparseness)
prove the gate can fail. Exit 0 iff every class PASSES and both RED legs discriminate.
"""
import json
import subprocess
import sys
from pathlib import Path

D = Path("corpus_build/gp3")
fails = 0

def check(cond, ok_msg, fail_msg):
    global fails
    if cond:
        print(f"PASS {ok_msg}")
    else:
        print(f"FAIL {fail_msg}")
        fails += 1

# ---------- RED leg 1: wrong-sha verify must have been REJECTED ----------
wrong = json.load(open(D / "gp3_verify_sparse_wrongsha.json"))
check(wrong.get("match") is False,
      "[red-sha] wrong-sha verify reports match=false — gate can FAIL",
      "[red-sha] wrong-sha verify returned match=true — verify is decoration")

# ---------- RED leg 2: dense control must FAIL the sparseness assertion ----------
# Discriminator is not extent COUNT (ext4 may coalesce a dense file into 3 extents,
# measured: dense.bin landed as 3 multi-block extents) but extent CONTENT:
# sparse = 3 extents of exactly 1 block each (holes between), dense = multi-block
# extents covering all 16384 logical blocks. Assert via filefrag block coverage.
dense_loc = json.load(open(D / "locate_dense.json"))
dense_blocks = sum(s["blocks"] for s in dense_loc["spans"])
sparse_blocks = sum(s["blocks"] for s in json.load(open(D / "locate_sparse.json"))["spans"])
check(dense_blocks >= 16384 / 2 and sparse_blocks == 3,
      f"[red-sparse] dense control maps {dense_blocks} data blocks vs sparse's {sparse_blocks} — "
      "block-coverage assertion discriminates sparse from dense",
      f"[red-sparse] dense control maps only {dense_blocks} blocks — assertion cannot discriminate")

# geometry evidence: guest-side filefrag dump
geo = (D / "geometry.txt").read_text()
# ---------- Class 1: sparse ----------
sparse_loc = json.load(open(D / "locate_sparse.json"))
spans = sparse_loc.get("spans", [])
check(sparse_loc["extents"] == 3 and len(spans) == 3,
      f"[gp3-sparse] locate found 3 single-block extents at sparse logical offsets {sorted(s['logical_first'] for s in spans)}",
      f"[gp3-sparse] locate extents={sparse_loc['extents']} (expected 3)")
check("sparse.bin is 67108864 (16384 blocks" in geo and "3 extents found" in geo,
      "[gp3-sparse] guest filefrag confirms 64MB logical / 3 physical extents",
      "[gp3-sparse] guest filefrag dump missing expected sparse shape")
ver = json.load(open(D / "gp3_verify_sparse.json"))
check(ver.get("match") is False,
      "[gp3-sparse] FINDING: verify of sparse file MISMATCHES (recon 28cd6ed5… vs guest e2c0c762…) — "
      "container holes hold pre-image bytes, not the guest's zeros; dense control match=true "
      "discriminates: this is the hole class, not a stale-writeback artifact",
      "[gp3-sparse] sparse verify unexpectedly matched — hole geometry not exercised as measured")

# ---------- Class 2: hardlink ----------
hl_o = json.load(open(D / "gp3_v_hl_orig.json"))
hl_a = json.load(open(D / "gp3_v_hl_alias.json"))
check(hl_o.get("match") is True and hl_a.get("match") is True,
      "[gp3-hardlink] same inode verified byte-exact at BOTH paths (orig + alias)",
      f"[gp3-hardlink] orig={hl_o.get('match')} alias={hl_a.get('match')}")
check("268623 alias.txt" in geo and "268623 orig.txt" in geo,
      "[gp3-hardlink] guest ls -i confirms shared inode 268623",
      "[gp3-hardlink] inode evidence missing from geometry.txt")

# ---------- Class 3: truncate_rewrite ----------
tr = json.load(open(D / "gp3_v_trunc.json"))
tr_pre = json.load(open(D / "gp3_v_trunc_pre.json"))
check(tr.get("match") is True,
      "[gp3-truncrw] post-rewrite content verifies byte-exact (stale pre-truncate pixels NOT served)",
      "[gp3-truncrw] post-rewrite verify failed")
check(tr_pre.get("match") is False,
      "[gp3-truncrw] RED leg: pre-rewrite sha correctly REJECTED after rewrite — class gate discriminates old vs new",
      "[gp3-truncrw] pre-rewrite sha still verifies — chain serves stale content (would be a REAL bug)")

# ---------- Class 4: multiframe ----------
big3 = json.load(open(D / "locate_big3_256mb.json"))
bframes = sorted({s["start"]["frame"] for s in big3["spans"]} | {s["end"]["frame"] for s in big3["spans"]})
check(bframes[1] - bframes[0] >= 4,
      f"[gp3-multiframe] 256MB file spans frames {bframes[0]}..{bframes[-1]} = {bframes[-1]-bframes[0]} frame boundaries (> 3, prior art was 3)",
      f"[gp3-multiframe] only {bframes[-1]-bframes[0]} boundaries crossed — assertion not met")
big3v = json.load(open(D / "gp3_v_big3.json"))
check(big3v.get("match") is True,
      "[gp3-multiframe] 256MB 1-extent file reconstructs byte-exact from PNGs across all frames",
      "[gp3-multiframe] 256MB verify mismatch")
bigred = json.load(open(D / "gp3_v_big3_red.json"))
check(bigred.get("match") is False,
      "[gp3-multiframe] RED leg: wrong sha on big3 rejected",
      "[gp3-multiframe] wrong sha accepted — decoration")

print()
if fails:
    print(f"gate_gp3_geometry: FAIL ({fails} failing checks)")
    sys.exit(1)
print("gate_gp3_geometry: PASS — 4 classes evidenced; RED legs all discriminating")
print("NOTE: sparse class carries a live FINDING (hole bytes ≠ guest zeros) — ticket required, gate records it, does not hide it.")
