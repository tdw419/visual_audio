#!/usr/bin/env python3
"""FACT-4 — pixel-behavior proof index (RULING_factory_trust_infra_supply.md).

Scrapes .builder_queue/RESEARCH_*.md and RECEIPT_*.md for opcode + posture +
verdict evidence and rolls it into one generated per-opcode table
(OPCODE_PROOF_INDEX.md), cross-linked to the OpcodeMapV2 inline spec in
tools/glyph_isa_v2.py (and its glyph_dispatch mirror).

Scope guarantees (from the ruling):
- AGGREGATION ONLY: this tool never re-measures, never re-opens a closed BK
  row, and makes no new containment claims. It indexes what receipts already
  prove and states the limits of that indexing.
- Regeneratable: the output doc is a pure function of the receipt corpus and
  the OpcodeMapV2 opcode table. No wall-clock stamps in the output (only the
  corpus file names and their counts), so regeneration is byte-identical for
  an unchanged tree.

Honesty limits (stated in the output header too):
- Attribution is FILE-level: a receipt "covers" an opcode it names; posture
  and verdict vocabulary is counted per receipt, not per measurement leg.
  The index tells you WHERE the proof lives (which file, which BK rows), not
  what each leg concluded — read the receipt for that.
- An opcode with no receipt coverage is listed as UNPROVED (no evidence
  found), which is not a claim that it is broken — only that this corpus
  contains no verdict-bearing receipt naming it.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent

# The canonical opcode table lives in OpcodeMapV2 (tools/glyph_isa_v2.py).
# Import it rather than duplicating the list; fall back to the mirror only if
# the primary import fails.
def load_opcodes() -> Dict[str, str]:
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    try:
        from tools.glyph_isa_v2 import OpcodeMapV2  # type: ignore

        return dict(OpcodeMapV2.OPCODES)
    except Exception:
        pass
    mirror = REPO / "glyph_dispatch" / "src" / "glyph" / "glyph_isa_v2.py"
    if mirror.exists():  # pragma: no cover - environment fallback
        import importlib.util

        spec = importlib.util.spec_from_file_location("gd_isa", mirror)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load mirror {mirror}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return dict(mod.OpcodeMapV2.OPCODES)
    raise RuntimeError("no OpcodeMapV2 found (primary or glyph_dispatch mirror)")


# Posture vocabulary — observed across the BK-2xx receipt line (measured
# 2026-10-07: box 96, tile 97+15, walk 38, remap 69, paged 48, unpaged 15,
# identity 31, twin 98+9, USER 61, SUPER 52 occurrences in RESEARCH_bk24*).
POSTURES = [
    "box", "tile", "walk", "remap", "paged", "unpaged", "identity",
    "twin", "USER", "SUPER",
]

# Verdict vocabulary — the receipt line's own verbs (measured 2026-10-07:
# landed 1053, lands 334, refused 234, silent 238, no-fault 104 in
# RESEARCH_*/RECEIPT_*).
VERDICTS = [
    "LANDS", "LANDED", "REFUSES", "REFUSED", "SILENT", "NO FAULT",
]


def _word_boundary(term: str) -> str:
    return r"\b" + re.escape(term) + r"\b"


def scan_receipt(path: Path, opcodes: Dict[str, str]) -> Optional[dict]:
    """Extract one receipt's opcode/posture/verdict evidence (file-level)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    found_opcodes = sorted(
        op for op in opcodes if re.search(_word_boundary(op), text)
    )
    if not found_opcodes:
        return None
    bk_rows = sorted(set(re.findall(r"\bBK-\d+\b", text)))
    postures = sorted(
        p for p in POSTURES if re.search(_word_boundary(p), text)
    )
    verdicts = sorted(
        v for v in VERDICTS if re.search(_word_boundary(v), text, re.IGNORECASE)
    )
    # First heading line as the receipt's human title.
    title = ""
    for line in text.splitlines():
        if line.startswith("#"):
            title = line.lstrip("# ").strip()
            break
    return {
        "file": path.name,
        "title": title[:160],
        "opcodes": found_opcodes,
        "bk_rows": bk_rows,
        "postures": postures,
        "verdicts": verdicts,
    }


def build_index(
    queue_dir: Path,
    opcodes: Dict[str, str],
) -> Tuple[str, dict]:
    """Return (index_markdown, stats). Deterministic for a fixed corpus."""
    receipts: List[dict] = []
    for pattern in ("RESEARCH_*.md", "RECEIPT_*.md"):
        for path in sorted(queue_dir.glob(pattern)):
            rec = scan_receipt(path, opcodes)
            if rec:
                receipts.append(rec)

    by_opcode: Dict[str, List[dict]] = {op: [] for op in opcodes}
    for rec in receipts:
        for op in rec["opcodes"]:
            by_opcode[op].append(rec)

    covered = {op for op, recs in by_opcode.items() if recs}
    unproved = sorted(op for op in opcodes if op not in covered)

    lines: List[str] = []
    lines.append("# OPCODE_PROOF_INDEX — generated pixel-behavior proof index")
    lines.append("")
    lines.append(
        "**Generated by** `tools/build_opcode_proof_index.py` (FACT-4, "
        "RULING_factory_trust_infra_supply.md). Regenerate: "
        "`python3 tools/build_opcode_proof_index.py`."
    )
    lines.append("")
    lines.append(
        f"- Opcode table source: `OpcodeMapV2.OPCODES` "
        f"(tools/glyph_isa_v2.py; glyph_dispatch mirror "
        f"`glyph_dispatch/src/glyph/glyph_isa_v2.py`) — "
        f"{len(opcodes)} opcodes."
    )
    lines.append(
        f"- Corpus: `.builder_queue/RESEARCH_*.md` + `RECEIPT_*.md` — "
        f"{len(receipts)} receipts name at least one opcode."
    )
    lines.append(
        f"- Coverage: {len(covered)} opcodes have receipt evidence; "
        f"{len(unproved)} have none in this corpus."
    )
    lines.append("")
    lines.append(
        "> HONESTY LIMITS: attribution is FILE-level (a receipt 'covers' an "
        "opcode it names; posture/verdict vocabulary is counted per receipt, "
        "not per measurement leg). This index says WHERE a proof lives, not "
        "what each leg concluded — read the receipt. 'UNPROVED' means no "
        "receipt in this corpus names the opcode; it is not a defect claim. "
        "This tool aggregates; it re-measures nothing and makes no new "
        "containment claims."
    )
    lines.append("")

    # Per-opcode table: proven postures (as receipt-level posture terms),
    # the receipts citing each, and the BK rows.
    lines.append("## Per-opcode evidence")
    lines.append("")
    lines.append(
        "| Opcode | Receipts | BK rows | Posture terms seen | Verdict terms seen |"
    )
    lines.append("|---|---|---|---|---|")
    for op in sorted(opcodes):
        recs = by_opcode[op]
        if not recs:
            lines.append(f"| {op} | _(none in corpus)_ | — | — | — |")
            continue
        files = ", ".join(f"`{r['file']}`" for r in recs[:8])
        more = (
            f" … (+{len(recs) - 8} more)" if len(recs) > 8 else ""
        )
        bk = sorted({b for r in recs for b in r["bk_rows"]})
        bk_s = ", ".join(bk[:12]) + (" …" if len(bk) > 12 else "")
        post = sorted({p for r in recs for p in r["postures"]})
        verd = sorted({v for r in recs for v in r["verdicts"]})
        lines.append(
            f"| {op} | {len(recs)}: {files}{more} | {bk_s or '—'} | "
            f"{', '.join(post) or '—'} | {', '.join(verd) or '—'} |"
        )
    lines.append("")

    lines.append("## Unproved in this corpus")
    lines.append("")
    if unproved:
        lines.append(
            "No receipt in `.builder_queue/` names these opcodes: "
            + ", ".join(f"`{op}`" for op in unproved)
            + "."
        )
    else:
        lines.append("Every OpcodeMapV2 opcode is named by at least one receipt.")
    lines.append("")

    lines.append("## Receipt inventory (opcode-bearing)")
    lines.append("")
    lines.append("| Receipt | Opcodes named | BK rows |")
    lines.append("|---|---|---|")
    for rec in sorted(receipts, key=lambda r: r["file"]):
        ops = ", ".join(rec["opcodes"][:10]) + (
            " …" if len(rec["opcodes"]) > 10 else ""
        )
        bk = ", ".join(rec["bk_rows"][:10]) + (
            " …" if len(rec["bk_rows"]) > 10 else ""
        )
        lines.append(f"| `{rec['file']}` | {ops} | {bk or '—'} |")
    lines.append("")

    stats = {
        "receipts": len(receipts),
        "covered": len(covered),
        "unproved": unproved,
        "opcodes": len(opcodes),
    }
    return "\n".join(lines), stats


def index_is_current(queue_dir: Path, out_path: Path) -> Tuple[bool, str]:
    """--check mode: True iff the on-disk index equals a fresh regeneration."""
    if not out_path.exists():
        return False, "index file missing"
    opcodes = load_opcodes()
    fresh, _ = build_index(queue_dir, opcodes)
    on_disk = out_path.read_text(encoding="utf-8", errors="replace")
    if on_disk == fresh:
        return True, "byte-identical to regeneration"
    # Locate the first divergence for a useful message.
    a = on_disk.splitlines()
    b = fresh.splitlines()
    for i, (la, lb) in enumerate(zip(a, b)):
        if la != lb:
            return False, f"stale at line {i + 1}: disk vs fresh differ"
    return False, f"stale: line-count {len(a)} vs {len(b)}"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--queue-dir",
        type=Path,
        default=REPO / ".builder_queue",
        help="receipt corpus directory (default: <repo>/.builder_queue)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO / "OPCODE_PROOF_INDEX.md",
        help="output index path (default: <repo>/OPCODE_PROOF_INDEX.md)",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 if the index is missing or stale",
    )
    args = ap.parse_args(argv)

    opcodes = load_opcodes()
    if args.check:
        ok, why = index_is_current(args.queue_dir, args.out)
        print(f"{'CURRENT' if ok else 'STALE'}: {args.out} — {why}")
        return 0 if ok else 1

    markdown, stats = build_index(args.queue_dir, opcodes)
    args.out.write_text(markdown, encoding="utf-8")
    print(
        f"wrote {args.out}: {stats['receipts']} opcode-bearing receipts, "
        f"{stats['covered']}/{stats['opcodes']} opcodes covered, "
        f"{len(stats['unproved'])} unproved"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
