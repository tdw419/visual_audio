#!/usr/bin/env python3
"""DEFECT-25 orchestrator probes — non-vacuity (sensor) + discrimination (sibling).

PART 1 — sensor non-vacuity
    Build a mutated copy of the audit module (in /tmp, repo untouched) with ONLY
    the new Signal-4 clause removed, and show that the pre-fix GH-20 fixture then
    yields ZERO violations. If it still yields five, the new predicate is not what
    the replay leg is testing and L4 is decoration.

PART 2 — sibling discrimination
    Serve a MUTANT append tile through the same seam: identical to the pinned
    FSV2_APPEND_TILE plus one extra store into FSTAB slot-1 word 1032. Arm A
    (control, pinned tile) must PASS the sibling's assertion chain; arm B (mutant)
    must FAIL it on the neighbour-slot guard. A sibling that passes with a
    corrupting tile is not a gate.

Repo files are never modified; md5 of both is recorded before and after.
"""
import hashlib
import importlib.util
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import tools.glyph_gpt.autoatlas as aa
from tools.glyph_gpt.autoatlas import admit_syscall
from tools.glyph_gpt.baker import (pixel_fs_v2_kernel_image, FSV2_N_APPEND,
                                   _gh18_tile_pc)
from tools.glyph_gpt.runner import GlyphRunner
from tools.glyph_gpt.atlas import build_default_atlas
from tools.glyph_gpt.escalate import EscalationResult
from tools.glyph_gpt.oracle import run_oracle

AUDIT = REPO / "tests" / "test_arc_determinism_audit.py"
PREFIX_FIXTURE = REPO / "tests" / "fixtures" / "arc_determinism_prefix_gh20.py"
TILES = REPO / "tests" / "fixtures" / "fs_v2_op_tiles.py"
LIVE_GH20 = REPO / "tests" / "test_gh20_fs_v2.py"


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


print("== DEFECT-25 orchestrator probes ==")
before = {p.name: md5(p) for p in (AUDIT, TILES, LIVE_GH20)}

# ── PART 1 ───────────────────────────────────────────────────────────────
real = load_module(AUDIT, "audit_real")
prefix_src = PREFIX_FIXTURE.read_text(encoding="utf-8")
real_v = real.find_unmarked_live_tests(prefix_src, "prefix_gh20")

mut_src = AUDIT.read_text(encoding="utf-8")
if "or has_contract_call" not in mut_src:
    print("PART1: FAIL — cannot neuter Signal 4 (clause not found)")
    sys.exit(1)
mut_src = mut_src.replace("or has_contract_call", "")
tmp = Path(tempfile.mkdtemp()) / "audit_neutered.py"
tmp.write_text(mut_src, encoding="utf-8")
neut = load_module(tmp, "audit_neutered")
neut_v = neut.find_unmarked_live_tests(prefix_src, "prefix_gh20")

print("\nPART 1 — sensor non-vacuity")
print(f"  real   sensor on pre-fix gh20 : {len(real_v)} violations")
print(f"  neutered (Signal 4 removed)   : {len(neut_v)} violations {neut_v}")
part1_ok = len(real_v) == 5 and neut_v == []
print(f"  -> {'PASS: the new predicate is load-bearing (5 -> 0 when neutered)' if part1_ok else 'FAIL'}")

# ── PART 2 ───────────────────────────────────────────────────────────────
from tests.fixtures.fs_v2_op_tiles import FSV2_APPEND_TILE
import tests.test_gh20_fs_v2 as gh20

_orig = aa.escalate
MUTANT = FSV2_APPEND_TILE.replace(
    "LDI r15 754\nST r15 r2\nHALT",
    "LDI r15 1032\nLDI r5 7\nST r15 r5\nLDI r15 754\nST r15 r2\nHALT")
assert MUTANT != FSV2_APPEND_TILE, "mutant construction failed"


def make_seam(tile):
    def _seam(task, expect_registers=None, seed_memory=None,
              input_registers=None, max_attempts=6, model="x", extra_vectors=None):
        ores = run_oracle(tile, expect_registers=expect_registers,
                          seed_memory=seed_memory, input_registers=input_registers)
        return EscalationResult(contract=task, verified=ores.passed, attempts=1,
                                glyph_text=tile if ores.passed else None,
                                oracle=ores, error=None if ores.passed else ores.error)
    return _seam


def run_leg_sibling(tile):
    """Replicate test_gh20_fs_append_grows_extents_clean_deterministic exactly."""
    aa.escalate = make_seam(tile)
    with tempfile.TemporaryDirectory() as d:
        runner = gh20._bake(Path(d))
        res = admit_syscall(runner, FSV2_N_APPEND,
                            contract="fs_append(name,start,len): grow "
                                     "extent by staged words @750",
                            argv={0: gh20.NAME_A}, expected=0)
        assert res.ok, f"{res.code}: {res.detail}"
        assert res.table_word != 0, "table entry must be live"
        assert res.table_word == _gh18_tile_pc(mode="fs_v2")
        receipt = runner.drive(seeds={}, max_instructions=60000)
        assert receipt["halted"] is True and not receipt["faulted"]
        slot1 = 1024 + gh20.FSV2_SLOT_WORDS
        for w in range(slot1, slot1 + gh20.FSV2_SLOT_WORDS):
            assert receipt["memory"][w] == 0, f"slot 1 word {w} clobbered"
    return True


print("\nPART 2 — sibling discrimination (same seam, two tiles)")
arm = {}
for label, tile in (("A control (pinned tile)", FSV2_APPEND_TILE),
                    ("B mutant (also writes slot-1 word 1032)", MUTANT)):
    try:
        run_leg_sibling(tile)
        arm[label] = "PASS"
    except AssertionError as e:
        arm[label] = f"RED: {e}"
    except Exception as e:                                   # noqa: BLE001
        arm[label] = f"ERROR: {type(e).__name__}: {e}"
aa.escalate = _orig

for k, v in arm.items():
    print(f"  {k:<42} {v}")

part2_ok = (not arm["A control (pinned tile)"].startswith(("RED", "ERROR"))
            and arm["B mutant (also writes slot-1 word 1032)"].startswith("RED"))
print(f"  -> {'PASS: the sibling catches a tile that verifies but corrupts a neighbour' if part2_ok else 'FAIL'}")

after = {p.name: md5(p) for p in (AUDIT, TILES, LIVE_GH20)}
untouched = before == after
print(f"\nrepo files byte-identical after probing: {untouched} "
      f"({', '.join(f'{k}={v[:8]}' for k, v in after.items())})")
print("\nVERDICT:", "PASS" if (part1_ok and part2_ok and untouched) else "FAIL")
sys.exit(0 if (part1_ok and part2_ok and untouched) else 1)
