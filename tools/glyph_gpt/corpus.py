#!/usr/bin/env python3
"""
corpus.py — collect .glyph programs from the repo and from transpiler synthesis.

Phase 3a implementation. Two dialects, two runners:

  isa_v2           — Glyph ISA v2 text (LDI/ADD/CMP/...), emitted by
                     rv64i_to_glyph.py. Runner: assemble_glyph_to_pixels
                     → GlyphCPUv2 (tools/glyph_isa_v2.py).
  pixel_interpreter — SET/STORE/LOAD_COORD/... text. Runner: assembler.assemble
                     → PixelCPU (pixel_interpreter/).

Dialect detection uses disjoint discriminator opcode sets (verified against
both OPCODE tables; 13 shared mnemonics are never used as discriminators).

Every corpus entry carries an execution receipt (oracle_status) so training
can filter verified positives (pass) and keep realistic negatives (fail)
for DPO. Receipts come from actually running each program — never assumed.

CLI:
    python3 tools/glyph_gpt/corpus.py                # build corpus.jsonl
    python3 tools/glyph_gpt/corpus.py --summary     # dialect/receipt breakdown
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_TOOLS_DIR = _REPO_ROOT / "tools"
_PIXEL_INTERP_DIR = _REPO_ROOT / "pixel_interpreter"

# Where the collected corpus is written (JSONL, one program per line).
CORPUS_PATH = Path(__file__).parent / "corpus.jsonl"

# ─── Dialect discriminators (verified disjoint; see SKELETON_SIGNED_OFF.md) ──

ISA_V2_DISCRIMINATORS = {
    "LDI", "ST", "PRT", "ROTR", "PUSH", "JMPR", "CALLR", "KJMP", "SYSCALL",
    "SYSRET", "PARALLEL_LD", "PARALLEL_ST", "PARALLEL_ADD", "PARALLEL_ST",
    "PARALLEL_SUB", "PARALLEL_REDUCE_SUM",
}

PIXEL_INTERP_DISCRIMINATORS = {
    "SET", "LOAD", "STORE", "LOAD_COORD", "MUL", "ADD_COORD", "ADD_MEM",
    "SUB_MEM", "NOP", "SEI", "CLI", "CTX_SAVE", "CTX_LOAD", "JMP_PC_IMM",
    "STORE_XY", "DIR_RIGHT", "DIR_DOWN", "DIR_LEFT", "DIR_UP", "CH_READ",
    "CH_WRITE_MEM", "SET_ADDR_HIGH", "SET_ADDR_LOW", "INDIRECT_STORE_MEM",
}

_WORD_RE = None  # compiled lazily in detect_dialect


# ─── Dialect detection ────────────────────────────────────────────────────

def detect_dialect(text: str) -> str:
    """Classify .glyph source by discriminator mnemonics.

    Returns "isa_v2", "pixel_interpreter", or "unknown".
    """
    import re
    counts = {"isa_v2": 0, "pixel_interpreter": 0}
    for m in re.finditer(r"^\s*([A-Z_]+)\b", text, re.M):
        op = m.group(1)
        if op in ISA_V2_DISCRIMINATORS:
            counts["isa_v2"] += 1
        elif op in PIXEL_INTERP_DISCRIMINATORS:
            counts["pixel_interpreter"] += 1
    if counts["isa_v2"] == 0 and counts["pixel_interpreter"] == 0:
        return "unknown"
    return max(counts, key=counts.get)


# ─── Oracle passes ────────────────────────────────────────────────────────

def oracle_pass_isa_v2(text: str, cols_instrs: int = 64,
                       max_instructions: int = 100_000) -> Dict:
    """Assemble + execute Glyph ISA v2 text on GlyphCPUv2.

    Returns receipt {"status": pass|syntax_error|no_halt|timeout, ...}.
    Note: uses rv64i_to_glyph.assemble_glyph_to_pixels (two-pass label
    resolution), NOT GlyphAssemblerV2.assemble directly (discovery #1).
    """
    try:
        sys.path.insert(0, str(_TOOLS_DIR))
        from rv64i_to_glyph import assemble_glyph_to_pixels
        from glyph_isa_v2 import OpcodeMapV2, GlyphCPUv2
        img, labels = assemble_glyph_to_pixels(text, cols_instrs=cols_instrs)
    except Exception as e:
        return {"status": "syntax_error", "error": f"{type(e).__name__}: {e}"}

    try:
        cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=cols_instrs)
        ran = cpu.run(img, max_instructions=max_instructions)
        steps = int(ran) if not isinstance(ran, tuple) else int(ran[0])
    except Exception as e:
        status = "fault" if "Fault" in type(e).__name__ else "timeout"
        return {"status": status, "error": f"{type(e).__name__}: {e}"}

    if steps >= max_instructions:
        return {"status": "no_halt", "steps": steps}
    return {"status": "pass", "steps": steps}


def oracle_pass_pixel_interpreter(text: str, max_cycles: int = 20_000) -> Dict:
    """Assemble + execute pixel_interpreter text on PixelCPU.

    Returns receipt {"status": pass|syntax_error|no_halt|timeout, ...}.
    """
    try:
        sys.path.insert(0, str(_PIXEL_INTERP_DIR))
        from assembler import assemble
        from cpu_emulator import PixelCPU
        img = assemble(text)  # 256x256x4 uint8
    except Exception as e:
        return {"status": "syntax_error", "error": f"{type(e).__name__}: {e}"}

    try:
        cpu = PixelCPU(256, 256)
        cpu.memory[:, :, :] = img.astype(np.uint32)
        cpu._read_state()
        res = cpu.run(max_cycles=max_cycles)
    except Exception as e:
        return {"status": "timeout", "error": f"{type(e).__name__}: {e}"}

    if not res.get("halted"):
        return {"status": "no_halt", "cycles": res.get("cycles", 0)}
    return {"status": "pass", "steps": res.get("cycles", 0)}


def run_oracle_for_dialect(text: str, dialect: str) -> Dict:
    """Dispatch to the dialect's runner. Unknown dialect → untagged."""
    if dialect == "isa_v2":
        return oracle_pass_isa_v2(text)
    if dialect == "pixel_interpreter":
        return oracle_pass_pixel_interpreter(text)
    return {"status": "unknown_dialect"}


# ─── Corpus collection ────────────────────────────────────────────────────

# Files under these dirs are skipped: infrastructure, not corpus.
# .worktrees/ is a git-worktree mirror of the repo — 322 of 370 raw *.glyph
# hits were its duplicates (discovered by sha256 dedupe in the first run).
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".worktrees"}


def collect_repo_glyph_files(root: Path = _REPO_ROOT) -> List[Dict]:
    """Find all *.glyph under `root`, dedupe, tag dialect, run oracle.

    Each entry: {"path": str (relative), "sha256": ..., "dialect": ...,
                 "oracle": {...}, "text": str}.
    """
    entries: List[Dict] = []
    seen: Dict[str, str] = {}  # sha256 → first path
    for path in sorted(root.rglob("*.glyph")):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        h = hashlib.sha256(text.encode()).hexdigest()
        if h in seen:
            entries.append({
                "path": str(path.relative_to(root)),
                "sha256": h, "dialect": "dup",
                "oracle": {"status": "dup_of", "dup_of": seen[h]}, "text": "",
            })
            continue
        seen[h] = str(path.relative_to(root))
        dialect = detect_dialect(text)
        receipt = run_oracle_for_dialect(text, dialect)
        entries.append({
            "path": str(path.relative_to(root)),
            "sha256": h,
            "dialect": dialect,
            "oracle": receipt,
            "text": text,
        })
    return entries


def synthesize_from_rv64i(binaries: List[Path], out_path: Path,
                          cols_instrs: int = 64) -> List[Dict]:
    """Phase 3b — implemented in the next round. Interface locked."""
    raise NotImplementedError("Phase 3b")


def write_corpus(entries: List[Dict], path: Path = CORPUS_PATH) -> int:
    """Write JSONL corpus. Returns count written."""
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return len(entries)


def load_corpus(path: Path = CORPUS_PATH) -> List[Dict]:
    """Load JSONL corpus."""
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


# ─── CLI ──────────────────────────────────────────────────────────────────

def _summary(entries: List[Dict]) -> str:
    by_dialect = Counter(e["dialect"] for e in entries)
    by_status = Counter(e["oracle"].get("status", "?") for e in entries)
    cross = Counter((e["dialect"], e["oracle"].get("status", "?")) for e in entries)
    lines = [
        f"total files: {len(entries)}",
        f"by dialect: {dict(by_dialect)}",
        f"by oracle status: {dict(by_status)}",
        "cross-tab:",
    ]
    for (d, s), n in sorted(cross.items()):
        lines.append(f"  {d:20s} {s:14s} {n}")
    return "\n".join(lines)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Build GlyphGPT corpus.jsonl")
    ap.add_argument("--root", default=str(_REPO_ROOT))
    ap.add_argument("--summary", action="store_true",
                    help="only print the breakdown of an existing corpus")
    args = ap.parse_args()

    if args.summary:
        entries = load_corpus()
    else:
        entries = collect_repo_glyph_files(Path(args.root))
        n = write_corpus(entries)
        print(f"wrote {n} entries to {CORPUS_PATH}")
    print(_summary(entries))


if __name__ == "__main__":
    main()
