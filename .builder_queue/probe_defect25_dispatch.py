#!/usr/bin/env python3
"""Orchestrator discriminating probe for DEFECT-25 (leg 5 / loop legs).

Question this answers: the pinned supply dispatches by SUBSTRING of the task
text (`"1026" in task`). If every op's augmented task contains the same digits,
all three ops receive the SAME tile and the sibling is coverage theater.

Method: install a recording `aa.escalate` seam (no monkeypatch fixture needed —
we setattr directly and restore), run all three ops through admit_syscall, and
report for each op the task tail, the tile identity selected, and whether the
oracle passed.
"""
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import tools.glyph_gpt.autoatlas as aa
from tools.glyph_gpt.autoatlas import admit_syscall
from tools.glyph_gpt.baker import pixel_fs_v2_kernel_image, FSV2_N_APPEND
from tools.glyph_gpt.escalate import EscalationResult
from tools.glyph_gpt.oracle import run_oracle
from tools.glyph_gpt.runner import GlyphRunner
from tools.glyph_gpt.atlas import build_default_atlas

sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO))
from tests.fixtures.fs_v2_op_tiles import (
    FSV2_APPEND_TILE, FSV2_RENAME_TILE, FSV2_UNLINK_TILE,
    dispatch_fs_tile_by_contract,
)

NAMES = {10: "fs_append", 11: "fs_rename", 12: "fs_unlink"}
IDENT = {FSV2_APPEND_TILE: "APPEND", FSV2_RENAME_TILE: "RENAME",
         FSV2_UNLINK_TILE: "UNLINK"}

record = []
_orig = aa.escalate


def _recording_escalate(task, expect_registers=None, seed_memory=None,
                        input_registers=None, max_attempts=6, model="x",
                        extra_vectors=None):
    try:
        tile = dispatch_fs_tile_by_contract(task)
        tid = IDENT.get(tile, "STRANGER")
    except ValueError as e:
        tile, tid = None, f"DISPATCH-RAISED({e})"
    ores = run_oracle(tile, expect_registers=expect_registers,
                      seed_memory=seed_memory,
                      input_registers=input_registers) if tile else None
    passed = bool(ores and ores.passed)
    record.append((tid, passed, task[-90:].replace("\n", " | ")))
    if passed:
        return EscalationResult(contract=task, verified=True, attempts=1,
                                glyph_text=tile, oracle=ores)
    return EscalationResult(contract=task, verified=False, attempts=1,
                            glyph_text=None, oracle=ores,
                            error=(ores.error if ores else "no tile"))


aa.escalate = _recording_escalate
try:
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "probe.npy"
        pixel_fs_v2_kernel_image(build_default_atlas(), out_path=out)
        runner = GlyphRunner(out, ram_words=16384)
        # per-op expected verdicts, exactly as the legs specify:
        # append/rename succeed (r2=0); unlink's seed refcount=2 forces the
        # clean-fail refuse path whose verdict IS the errno 69 (ord('E')).
        EXPECT = {10: 0, 11: 0, 12: 69}
        results = {}
        for n in (10, 11, 12):
            results[n] = admit_syscall(runner, n, contract="fs op tile",
                                       argv={0: 65}, expected=EXPECT[n])
finally:
    aa.escalate = _orig

print("== DEFECT-25 dispatch discriminating probe (orchestrator) ==")
for n in (10, 11, 12):
    print(f"\nSYS {n} ({NAMES[n]}): ok={results[n].ok} code={results[n].code} "
          f"table_word={results[n].table_word:#x}")
    print(f"   result word 754 == {results[n].detail[:80] if not results[n].ok else 'ok'}")

print("\ntiles served through the seam (in call order):")
for i, (tid, passed, tail) in enumerate(record):
    print(f"  [{i}] tile={tid:<24} oracle_passed={passed}")
    print(f"       task tail: ...{tail}")

tiles_served = [r[0] for r in record]
distinct = sorted(set(tiles_served))
print(f"\ncalls={len(record)} distinct_tiles={distinct}")
all_passed = all(r[1] for r in record)
print(f"every served tile passed the REAL oracle: {all_passed}")
print("VERDICT:", "OK — per-op dispatch is real and tiles are oracle-verified"
      if all_passed and len(distinct) == 3 and "DISPATCH-RAISED" not in str(distinct)
      else "SUSPECT — same tile for all ops, or an oracle failure: COVERAGE THEATER")
sys.exit(0 if (all_passed and len(distinct) == 3) else 1)
