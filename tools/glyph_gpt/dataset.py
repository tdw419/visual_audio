#!/usr/bin/env python3
"""
dataset.py — tokenized training sequences → npz.

Round 4a implementation. Contract (per Jericho's Phase 3c spec):

  - One sequence per program, framed [BOS] tokens... [EOS] [PAD]...
  - ids: int32 (N, seq_len), PAD=0
  - values: int32 (N, seq_len), 0 except NUM/LABEL positions
  - targets are derived at train time (next-token shift) with ignore
    wherever the TARGET id is PAD — loss only on active tokens.

Sequence source:
  - synth receipts: asm_hex → transpile → glyph text → tokenize
  - repo corpus: text field → tokenize directly (dialect as-is)

Programs longer than seq_len are skipped and counted in the receipt
(never silently truncated — a truncated program teaches broken HALT
placement).
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_TOOLS_DIR = _REPO_ROOT / "tools"


def _entry_to_glyph_text(entry: Dict) -> Optional[str]:
    """Get glyph text for a corpus/synth entry, or None if unavailable.

    Atlas entries (meta.atlas=true, Phase 5.6): return CALLER-ONLY text —
    the callee body lives in the routine atlas and is spliced by
    atlas.link() at run time. The full transpile would inline the callee,
    which is exactly the layout-planning burden we're removing from the
    model's target."""
    if entry.get("text"):
        return entry["text"]
    if entry.get("asm_hex"):
        sys_path = str(_TOOLS_DIR)
        if sys_path not in __import__("sys").path:
            __import__("sys").path.insert(0, sys_path)
        from rv64i_to_glyph import transpile_rv32i_to_glyph
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                text = transpile_rv32i_to_glyph(bytes.fromhex(entry["asm_hex"]))
        except Exception:
            return None
        if entry.get("atlas"):
            return _atlas_caller_view(text)
        return text
    return None


def _atlas_caller_view(text: str) -> str:
    """Rewrite full transpiled leaf_call text into the atlas caller view.

    Full form: ... :pc_main LDI r10 v ; LDI r1 imm ; CALL :callee ;
    :pc_after HALT ; ... :callee ADD r10 r10 ; RET.
    Caller view: keep everything up to and including the CALL's target
    line rewritten to :atlas_double, then cut at the first HALT and drop
    the inline callee (everything from the callee's label to RET)."""
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # cut at HALT: everything after (callee body) is atlas-supplied
        if line == "HALT":
            out.append("HALT")
            break
        # rewrite the CALL target to the atlas namespace
        if line.startswith("CALL :"):
            out.append("CALL :atlas_double")
            i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out) + "\n"


def build_sequences(entries: List[Dict], tokenizer, seq_len: int = 128,
                    oracle_key: str = "oracle",
                    require_match: bool = True) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """Encode each entry, frame, pad to seq_len. Returns (ids, values, receipt).

    require_match: skip entries whose oracle receipt exists but doesn't say
    match (execution-unverified text still allowed if no oracle key present,
    e.g. no_halt repo programs — controlled by oracle_key="").
    """
    import sys as _sys
    tools = str(_TOOLS_DIR)
    if tools not in _sys.path:
        _sys.path.insert(0, tools)

    all_pairs: List[Tuple[List[int], List[int]]] = []
    skipped = {"no_text": 0, "oracle_fail": 0, "too_long": 0}
    per_family: Dict[str, int] = {}
    max_len_seen = 0

    for entry in entries:
        if require_match and oracle_key and oracle_key in entry:
            if not entry[oracle_key].get("match"):
                skipped["oracle_fail"] += 1
                continue
        text = _entry_to_glyph_text(entry)
        if text is None:
            skipped["no_text"] += 1
            continue
        # Phase 5.5: family conditioning token prefix (synth entries carry
        # family; repo entries get none — the token simply isn't inserted)
        ids, values = tokenizer.encode(
            text, family=entry.get("family"),
            atlas_names=["double"] if entry.get("atlas") else None)
        if len(ids) > seq_len:
            skipped["too_long"] += 1
            continue
        max_len_seen = max(max_len_seen, len(ids))
        all_pairs.append((ids, values))
        fam = entry.get("family", entry.get("source", "repo"))
        per_family[fam] = per_family.get(fam, 0) + 1

    n = len(all_pairs)
    ids_arr = np.zeros((n, seq_len), dtype=np.int32)
    val_arr = np.zeros((n, seq_len), dtype=np.int32)
    for i, (ids, values) in enumerate(all_pairs):
        ids_arr[i, :len(ids)] = ids
        val_arr[i, :len(values)] = values

    receipt = {
        "total_entries": len(entries),
        "sequences": n,
        "skipped": skipped,
        "per_family": per_family,
        "seq_len": seq_len,
        "max_len_seen": max_len_seen,
        "vocab_size": tokenizer.vocab_size,
    }
    return ids_arr, val_arr, receipt


def save_dataset(ids: np.ndarray, values: np.ndarray, path: Path,
                 meta: Optional[Dict] = None) -> None:
    payload: Dict[str, np.ndarray] = {"ids": ids, "values": values}
    if meta:
        payload["meta_json"] = np.frombuffer(
            json.dumps(meta).encode(), dtype=np.uint8)
    np.savez_compressed(path, **payload)


def load_dataset(path: Path) -> Tuple[np.ndarray, np.ndarray, Optional[Dict]]:
    data = np.load(path, allow_pickle=False)
    ids = data["ids"]
    values = data["values"]
    meta = None
    if "meta_json" in data:
        meta = json.loads(data["meta_json"].tobytes().decode())
    return ids, values, meta
