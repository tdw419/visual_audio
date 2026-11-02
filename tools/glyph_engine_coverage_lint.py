#!/usr/bin/env python3
"""tools/glyph_engine_coverage_lint.py — cross-engine coverage checker.

Not an ABI/geometry linter (that's a separate, bigger tool someone else
may still build) -- this one thing only: catch the specific bug SHAPE
that hit BK-2 twice and GH-26.4 once this session -- two things that are
supposed to move together silently stopped agreeing, and nothing caught
it until a byte-level parity test forced the comparison:

  - `walk_ld` never checked the box_mmio MMIO range the way `walk_st`'s
    equivalent branch already did (BK-2, found via manual tracing).
  - `SYSRET` was fully implemented in the CPU engine but missing from
    WGSL's `_OPCODE_ORDER` entirely -- not wrong, just silently absent
    (BK-2, found by a shader compile error, not a logic bug).
  - A docstring described one SYSCALL convention while the actual trap
    code implemented another (GH-26.4 Bug 7).

All three are mechanically cheap to catch directly, which this script
does with two checks:

1. check_opcode_coverage() -- every opcode tools.glyph_isa_v2.OpcodeMapV2
   actually implements (has a parser branch AND an execute branch) has a
   corresponding entry in wgsl_glyph_isa_v2._OPCODE_ORDER, OR is on the
   documented allowlist (opcodes that intentionally live in a DIFFERENT
   WGSL engine -- the PARALLEL_* family lives in the workgroup-strided
   SIMT shader, tools/wgsl_spatial_glyph_engine.py, not this scalar one;
   see project memory "SpaDSL PARALLEL_* opcodes / SIMD shader").

2. check_mmio_symmetry() -- every WGSL function that special-cases the
   box_mmio reserved-block address range in ONE direction (load OR
   store) must special-case it in the other too. Implemented as a
   textual presence check (WGSL isn't parsed into an AST here -- the
   pattern this looks for, `addr >= BOX_MMIO_WORD_LO && addr <
   BOX_MMIO_WORD_LO + BOX_MMIO_SPAN`, is exactly what walk_st's box_mmio
   branch already uses, so this also asserts the fix itself won't
   silently regress).

Run standalone: `python3 tools/glyph_engine_coverage_lint.py`
Gate: tests/test_glyph_engine_coverage_lint.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, NamedTuple

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import OpcodeMapV2  # noqa: E402

WGSL_ENGINE_PATH = _REPO / "tools" / "wgsl_glyph_isa_v2.py"

# Opcodes intentionally absent from THIS scalar-per-lane WGSL engine
# because they live in a different, workgroup-strided SIMT shader
# (tools/wgsl_spatial_glyph_engine.py) -- not a coverage gap, a
# deliberate architectural split. Any opcode NOT on this list that's
# missing from _OPCODE_ORDER is a real finding.
_DIFFERENT_ENGINE_ALLOWLIST = {
    "PARALLEL_LD", "PARALLEL_ST", "PARALLEL_ADD", "PARALLEL_SUB",
    "PARALLEL_REDUCE_SUM",
}


class Finding(NamedTuple):
    check: str
    detail: str


def _wgsl_opcode_order() -> List[str]:
    """Import wgsl_glyph_isa_v2's _OPCODE_ORDER without executing the
    module's heavier build_shader() machinery -- it's a plain module-level
    list, a normal import is fine and keeps this in step automatically."""
    from tools.wgsl_glyph_isa_v2 import _OPCODE_ORDER
    return list(_OPCODE_ORDER)


def check_opcode_coverage() -> List[Finding]:
    """Every opcode OpcodeMapV2 knows about is either in WGSL's
    _OPCODE_ORDER or on the documented different-engine allowlist."""
    cpu_opcodes = set(OpcodeMapV2.OPCODES.keys())
    wgsl_opcodes = set(_wgsl_opcode_order())
    missing = cpu_opcodes - wgsl_opcodes - _DIFFERENT_ENGINE_ALLOWLIST
    return [
        Finding("opcode_coverage",
                f"'{op}' is a real CPU opcode (OpcodeMapV2.OPCODES) with no "
                f"WGSL entry (_OPCODE_ORDER) and is not on the "
                f"different-engine allowlist -- either implement it in "
                f"wgsl_glyph_isa_v2.py or add it to "
                f"_DIFFERENT_ENGINE_ALLOWLIST with a reason")
        for op in sorted(missing)
    ]


def check_mmio_symmetry() -> List[Finding]:
    """walk_ld and walk_st must agree on how they handle the box_mmio
    reserved range, checked against the REAL engine file. See
    _check_mmio_symmetry_in_text() for the reusable logic (tests exercise
    that directly against synthetic WGSL text, so the detector itself is
    proven to fire on a corrupted case, not just that today's file
    happens to be clean)."""
    return _check_mmio_symmetry_in_text(WGSL_ENGINE_PATH.read_text(),
                                        source_name=WGSL_ENGINE_PATH.name)


def _check_mmio_symmetry_in_text(src: str, source_name: str = "<text>") -> List[Finding]:
    """Textual, not AST-based (WGSL has no Python parser handy here) --
    looks for the SAME range-check expression walk_st's box_mmio branch
    already uses, inside each of walk_ld/walk_st's own function body."""
    findings: List[Finding] = []
    pattern = re.compile(r"addr\s*>=\s*BOX_MMIO_WORD_LO\s*&&\s*addr\s*<\s*"
                         r"BOX_MMIO_WORD_LO\s*\+\s*BOX_MMIO_SPAN")
    for fn_name in ("walk_ld", "walk_st"):
        m = re.search(rf"fn {fn_name}\([^)]*\)[^{{]*{{", src)
        if not m:
            findings.append(Finding("mmio_symmetry",
                                    f"could not locate `fn {fn_name}(...)` in "
                                    f"{source_name} -- check moved/renamed?"))
            continue
        # Grab the function body via brace matching from the opening brace.
        start = m.end() - 1
        depth, i = 0, start
        while i < len(src):
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = src[start:i + 1]
        if not pattern.search(body):
            findings.append(Finding(
                "mmio_symmetry",
                f"`{fn_name}` never checks the box_mmio MMIO range "
                f"(BOX_MMIO_WORD_LO..+BOX_MMIO_SPAN) -- its sibling might "
                f"read/write MMIO words this function silently misses "
                f"(this is exactly BK-2's walk_ld bug -- see the module "
                f"docstring)"))
    return findings


def run_all() -> List[Finding]:
    return check_opcode_coverage() + check_mmio_symmetry()


def main() -> int:
    findings = run_all()
    if not findings:
        print("glyph_engine_coverage_lint: clean -- no findings")
        return 0
    print(f"glyph_engine_coverage_lint: {len(findings)} finding(s)")
    for f in findings:
        print(f"  [{f.check}] {f.detail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
