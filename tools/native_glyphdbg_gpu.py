#!/usr/bin/env python3
"""tools/native_glyphdbg_gpu.py — click-to-execute executor (BK-82 RUNG 3).

The map's own cells become launch targets (the browser drawer's glyphdbg
flow, NATIVE): a Glyph program is assembled with the REAL assembler
(GlyphAssemblerV2/OpcodeMapV2 — no host-side re-derivation) and executed on
the live WGSL TWIN (GlyphRunner.run_wgsl, wgpu, RTX 5090). The Rung 2
vtshell ran a FIXED image (xv6-nano); Rung 3 runs the caller's program on
the SAME GPU path the parity gates use (tests/test_se024_wgsl_parity.py).

Every launch (accepted OR refused) appends a receipt to
.builder_queue/decision_log.jsonl with the SAME schema as the bridge's
bk58_bridge_launch records (class/detail/verdict/ts/evidence_hash/kind),
produced by tools.build_map_bridge.log_launch itself — not a re-implementation.

Directive: .builder_queue/DIRECTIVE_BK82_NATIVE_UI_LADDER.md (RUNG 3)
Gate: tests/test_bk82_rung3_native_glyphdbg.py
Oracles untouched: glyph_isa_v2.py / wgsl_glyph_isa_v2.py / glyph_vt.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.build_map_bridge import log_launch  # noqa: E402  (the SAME receipt writer)

_GLYPHDBG_MAX_PROG = 8192    # matches build_map_bridge._PROGRAM_RE cap
_GLYPHDBG_MAX_STEPS = 2000   # matches build_map_bridge.handle_glyphdbg cap


def _validate_program(program: Any, max_steps: Any) -> tuple:
    """Returns (error, program, max_steps). Closed-set validation, loud refusals."""
    if not isinstance(program, str):
        return ("program must be a string", None, None)
    if not program or len(program) > _GLYPHDBG_MAX_PROG:
        return (f"program must be 1..{_GLYPHDBG_MAX_PROG} chars", None, None)
    for ch in program:
        if not (ch in "\n\r\t" or 0x20 <= ord(ch) <= 0x7E):
            return ("program must be printable ASCII (+ whitespace)", None, None)
    if not program.strip():
        return ("program is empty after stripping", None, None)
    if max_steps is None:
        max_steps = 200
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) \
            or not (1 <= max_steps <= _GLYPHDBG_MAX_STEPS):
        return (f"max_steps must be int 1..{_GLYPHDBG_MAX_STEPS}", None, None)
    return (None, program, max_steps)


def run_glyphdbg_gpu(program: str = "", max_steps: Optional[int] = 200,
                     log: bool = True) -> Dict[str, Any]:
    """Assemble + execute a caller-supplied Glyph program on the WGSL twin.

    Scoped: no host shell, no client-supplied FS paths, bounded steps.
    Every launch (accepted or refused) logged via the bridge's log_launch.
    """
    err, program, max_steps = _validate_program(program, max_steps)
    if err is not None:
        if log:
            log_launch("glyphdbg-native", {"params": {"max_steps": max_steps},
                                           "error": err}, "refused")
        return {"ok": False, "error": err}
    assert max_steps is not None  # narrowed by _validate_program

    from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2

    lines = [l for l in program.splitlines() if l.strip()]
    opcode_map = OpcodeMapV2()
    try:
        try:
            image = _assemble(asm_mod(), opcode_map, lines)
        except Exception as e:
            result = {"ok": False, "error": f"assemble failed: {e}"}
            if log:
                log_launch("glyphdbg-native",
                           {"params": {"max_steps": max_steps},
                            "result_ok": False, "error": result["error"]},
                           "error")
            return result

        from tools.glyph_gpt.runner import GlyphRunner
        runner = GlyphRunner(image, cols_instrs=8)
        wgsl = runner.run_wgsl(max_steps=max_steps)

        if not wgsl.get("executed", False):
            result = {"ok": False,
                      "error": f"GPU run failed: {wgsl.get('error', 'unknown')}"}
        elif not wgsl.get("halted", False):
            result = {"ok": False,
                      "error": f"twin did not halt within {max_steps} steps"}
        else:
            result = {
                "ok": True,
                "engine": "wgsl-twin",
                "steps": int(wgsl["steps"]),
                "halted": True,
                "faulted": bool(wgsl.get("faulted", False)),
                "registers_full": wgsl["registers_full"],
                "output": wgsl.get("output", []),
            }
    finally:
        try:
            opcode_map.close()
        except Exception:
            pass

    if log:
        log_launch("glyphdbg-native",
                   {"params": {"max_steps": max_steps},
                    "result_ok": bool(result["ok"]),
                    "steps": result.get("steps")},
                   "ok" if result["ok"] else "error")
    return result


def asm_mod():
    from tools import glyph_isa_v2
    return glyph_isa_v2


def _assemble(gi, opcode_map, lines):
    return gi.GlyphAssemblerV2(opcode_map).assemble(lines, width_instrs=8)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="BK-82 Rung 3 native glyphdbg")
    parser.add_argument("--program", required=True,
                        help="Glyph program text (newline-separated instructions)")
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--no-log", action="store_true",
                        help="skip decision_log receipt (gate plumbing only)")
    args = parser.parse_args()
    print(json.dumps(run_glyphdbg_gpu(program=args.program,
                                      max_steps=args.max_steps,
                                      log=not args.no_log)))


if __name__ == "__main__":
    main()
