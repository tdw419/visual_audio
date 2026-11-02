#!/usr/bin/env python3
"""
test_atlas.py — Phase 5.6 gates for the Patch-and-Copy routine atlas.

1. Default atlas builds and every tile carries a passing receipt.
2. Linked form of the canonical caller executes+halts with a0 doubled.
3. Atlas persistence round-trips (save/load/link identical).
4. Unknown tile refs raise (never silently link wrong code).
5. Unverified tiles refused at registration (assembler failure).
6. Atlas-caller training view: pack text is caller-only (no inline
   callee), and linked + executed still satisfies a0 = 2*v.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOOLS = _HERE.parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from glyph_gpt.atlas import (
    RoutineAtlas, build_default_atlas,
    ACCUMULATE_HARNESS, MEMCPY_HARNESS, TILE_CLEAR_HARNESS,
)
from glyph_gpt.dataset import _atlas_caller_view

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def main() -> None:
    print("== RoutineAtlas gates ==")

    # 1. default atlas: tiles verified
    atlas = build_default_atlas()
    receipt = atlas.tiles["double"]["receipt"]
    check("tile 'double' registered with passing receipt",
          receipt.get("assembled") and receipt.get("halted"), str(receipt))

    # 2. canonical caller: linked form doubles a0
    caller = (":__entry\nLDI r31 4351\nJMP :main\n:main\n"
              "LDI r10 0x7\nCALL :atlas_double\nHALT\n")
    r = atlas.run_linked(caller)
    a0 = r["registers_full"][10] if r.get("registers_full") else None
    check("linked caller executes+halts, a0 == 14",
          r.get("halted") and a0 == 14, f"a0={a0} {r.get('error', '')}")

    # 3. persistence round-trip
    import tempfile, os
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        p = Path(f.name)
    try:
        atlas.save(p)
        atlas2 = RoutineAtlas.load(p)
        r2 = atlas2.run_linked(caller)
        check("save/load round-trip links identically",
              r2.get("halted") and r2["registers_full"][10] == 14,
              str(r2.get("error", "")))
    finally:
        os.unlink(p)

    # 4. unknown tile ref raises
    bad = caller.replace(":atlas_double", ":atlas_nope")
    try:
        atlas.run_linked(bad)
        check("unknown tile ref raises", False, "no exception")
    except ValueError:
        check("unknown tile ref raises", True)

    # 5. unverified tile refused
    try:
        a3 = RoutineAtlas()
        a3.register("broken", ":atlas_broken\nFROB r1 r2 r3\nRET\n",
                    family="test")
        check("unverified tile refused", False, "registered anyway")
    except ValueError:
        check("unverified tile refused", True)

    # 6. atlas-caller training view: caller-only, then link still works
    full_text = (":__entry\nLDI r31 4351\nJMP :pc_00000000\n\n"
                 ":pc_00000000\nLDI r10 0x9\n:pc_00000004\nLDI r1 0x8\n"
                 "CALL :pc_00000010\n:pc_00000008\nHALT\n"
                 ":pc_0000000c\n:pc_00000010\nADD r10 r10\n:pc_00000014\nRET\n")
    view = _atlas_caller_view(full_text)
    check("caller view drops inline callee",
          "ADD r10 r10" not in view and "RET" not in view
          and "CALL :atlas_double" in view and "HALT" in view, view)
    # strip the transpiler comment for assembly
    asm_view = "\n".join(l for l in view.splitlines()
                         if not l.startswith("#"))
    r6 = atlas.run_linked(asm_view)
    a6 = r6["registers_full"][10] if r6.get("registers_full") else None
    check("caller view + atlas link: a0 == 2*v",
          r6.get("halted") and a6 == 18, f"a0={a6} {r6.get('error', '')}")

    # ── Phase 5.7: grown font — functional gates on the new tiles ────────
    check("default atlas has 4 tiles",
          set(atlas.tiles) == {"double", "accumulate", "memcpy",
                               "tile_clear"}, str(sorted(atlas.tiles)))
    check("new tiles carry passing harness receipts",
          all(bool(atlas.tiles[n].get("harness_receipt", {}).get("halted"))
              for n in ("accumulate", "memcpy", "tile_clear")))

    # accumulate: [7,9,5] -> tile returns sum in r10 (a0); caller must
    # HALT right after CALL (any LD would clobber the returned value)
    acc_caller = ("LDI r11 500\nLDI r14 7\nST r11 r14\nLDI r14 9\n"
                  "LDI r15 501\nST r15 r14\nLDI r14 5\nLDI r15 502\n"
                  "ST r15 r14\nLDI r12 3\nCALL :atlas_accumulate\n"
                  "HALT\n")
    r7 = atlas.run_linked(acc_caller)
    a7 = r7["registers_full"][10] if r7.get("registers_full") else None
    check("accumulate: sum([7,9,5]) == 21 in a0",
          bool(r7.get("halted")) and a7 == 21,
          f"a0={a7} {r7.get('error', '')}")

    # memcpy: [111,222,333] 500->600, verify word 0 landed
    mc_caller = (MEMCPY_HARNESS.rstrip("\n").rsplit("HALT", 1)[0] +
                 "LDI r9 600\nLD r10 r9\nHALT\n")
    r8 = atlas.run_linked(mc_caller)
    a8 = r8["registers_full"][10] if r8.get("registers_full") else None
    check("memcpy: word 0 copied (600 == 111)",
          bool(r8.get("halted")) and a8 == 111,
          f"a0={a8} {r8.get('error', '')}")

    # tile_clear: fill 4 words at 400 with 0xDEAD, verify the LAST word
    cl_caller = (TILE_CLEAR_HARNESS.rstrip("\n").rsplit("HALT", 1)[0] +
                 "LDI r9 403\nLD r10 r9\nHALT\n")
    r9 = atlas.run_linked(cl_caller)
    a9 = r9["registers_full"][10] if r9.get("registers_full") else None
    check("tile_clear: last filled word (403 == 0xDEAD)",
          bool(r9.get("halted")) and a9 == 57005,
          f"a0={a9} {r9.get('error', '')}")

    # ── Lever #2: out-of-bounds store traps loudly (len(memory)-relative) ──
    # Default GlyphCPUv2 RAM is 1024 words. A store to word 2000 was silently
    # dropped before; it must now fault (faulted=True) and NOT report a clean
    # HALT, so a bad pointer can't masquerade as success.
    oob_caller = "LDI r1 2000\nLDI r2 305419896\nST r1 r2\nHALT\n"
    r_oob = atlas.run_linked(oob_caller)
    check("OOB store to word 2000 faults, not a clean halt",
          bool(r_oob.get("faulted")) and not r_oob.get("halted"),
          f"faulted={r_oob.get('faulted')} halted={r_oob.get('halted')} "
          f"fault_addr={r_oob.get('fault_addr')}")
    # positive control: an in-bounds store (word 900) still executes+halts
    ib_caller = "LDI r1 900\nLDI r2 42\nST r1 r2\nLDI r9 900\nLD r10 r9\nHALT\n"
    r_ib = atlas.run_linked(ib_caller)
    a_ib = r_ib["registers_full"][10] if r_ib.get("registers_full") else None
    check("in-bounds store to word 900 still halts cleanly",
          bool(r_ib.get("halted")) and not r_ib.get("faulted") and a_ib == 42,
          f"a0={a_ib} faulted={r_ib.get('faulted')} {r_ib.get('error', '')}")

    print(f"\nAtlas tests: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
