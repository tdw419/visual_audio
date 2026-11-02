#!/usr/bin/env python3
"""
GlyphTokenizer — opcode-level tokenizer for Glyph assembly.

Design is copied from the proven pixel-hypervisor opcode_tokenizer.py
(266 discrete tokens → 100% syntactic validity at 530K params), adapted
to the Glyph ISA v2 dialect used by tools/glyph_isa_v2.py and emitted by
tools/rv64i_to_glyph.py:

    0..9      special tokens (PAD/BOS/EOS/NEWLINE/COMMENT/NUM/LABEL/STR/COMMA/COLON)
    10..      opcodes (from GlyphAssemblerV2's accepted opcode set)
    then      registers r0..r31 as discrete tokens

Unlike the pixel-hypervisor version, this tokenizer also carries a
*value channel*: NUM and LABEL tokens are backed by int32 values stored
in a parallel array, so the model can emit exact immediates (required
for the execution oracle to verify register results) without needing a
huge literal vocabulary.

This module is a pure deterministic utility — fully implemented in the
skeleton phase per skeleton-driven-development skill rule #2.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─── Special tokens (contract: order is frozen, never renumber) ────────────
PAD = 0
BOS = 1
EOS = 2
NEWLINE = 3
COMMENT = 4
NUM = 5
LABEL = 6
STR = 7
COMMA = 8
COLON = 9

SPECIAL_NAMES = {
    PAD: "<PAD>",
    BOS: "<BOS>",
    EOS: "<EOS>",
    NEWLINE: "<NL>",
    COMMENT: "<COMMENT>",
    NUM: "<NUM>",
    LABEL: "<LABEL>",
    STR: "<STR>",
    COMMA: "<COMMA>",
    COLON: "<COLON>",
}

# Phase 5.5 family-conditioning tokens: prepended after BOS to pin the
# program-family distribution (multi-modal value draws + CALL plumbing
# hinge on family context the token stream alone doesn't always carry).
FAMILY_TOKENS = [
    "<FAMILY_ALU_CHAIN>",
    "<FAMILY_COUNTED_LOOP>",
    "<FAMILY_CONDITIONAL>",
    "<FAMILY_MEM_PASS>",
    "<FAMILY_LEAF_CALL>",
]
FAMILY_TO_TOKEN = {
    "alu_chain": "<FAMILY_ALU_CHAIN>",
    "counted_loop": "<FAMILY_COUNTED_LOOP>",
    "conditional": "<FAMILY_CONDITIONAL>",
    "mem_pass": "<FAMILY_MEM_PASS>",
    "leaf_call": "<FAMILY_LEAF_CALL>",
}

NUM_SPECIAL = len(SPECIAL_NAMES) + len(FAMILY_TOKENS)

# Alias used by tests/importers: SPECIAL[NUM] → "<NUM>"
SPECIAL = {**SPECIAL_NAMES, **{t: t for t in FAMILY_TOKENS}}

# Register token: r0..r31 immediately after specials.
N_REGISTERS = 32


def build_default_vocab() -> Tuple[List[str], Dict[str, int]]:
    """Build the canonical vocab ordered [specials..., family..., registers..., opcodes...].

    Returns (token_strings, token_to_id).
    """
    tokens: List[str] = [SPECIAL_NAMES[i] for i in range(len(SPECIAL_NAMES))]
    tokens += FAMILY_TOKENS
    tokens += [f"r{i}" for i in range(N_REGISTERS)]
    return tokens, {t: i for i, t in enumerate(tokens)}


_LINE_RE = re.compile(
    r"""
    (?P<comment>;.*$)                 # comment: rest of line, single token
    |(?P<label>:[A-Za-z_][\w.]*)      # label definition or reference
    |(?P<num>0[xX][0-9a-fA-F]+|-?\d+) # hex or (signed) decimal literal
    |(?P<reg>\br\d{1,2}\b)            # r0..r31
    |(?P<str>"[^"]*")                 # quoted string
    |(?P<comma>,)
    |(?P<word>[A-Za-z_][\w.]*)        # opcode / bare identifier
    """,
    re.VERBOSE,
)


# Phase 5.6: atlas refs get RESERVED label values so the value channel
# names the tile deterministically. 'CALL :atlas_<name>' encodes as
# LABEL with value ATLAS_LABEL_BASE + index-in-names; decode maps back.
ATLAS_LABEL_BASE = 1000


def atlas_label_value(name: str, atlas_names: List[str]) -> int:
    return ATLAS_LABEL_BASE + atlas_names.index(name)


def atlas_label_name(value: int, atlas_names: List[str]) -> Optional[str]:
    idx = value - ATLAS_LABEL_BASE
    if 0 <= idx < len(atlas_names):
        return atlas_names[idx]
    return None


class GlyphTokenizer:
    """Encode Glyph assembly text to token ids (+ parallel value array), and back.

    Values channel: whenever a NUM or LABEL token is produced, the numeric
    value (immediate, or label's instruction index if known) is appended to
    the values array. All other tokens push 0. decode() ignores values; the
    value channel exists for constrained decoding and for the model to
    predict immediates exactly.
    """

    def __init__(self, opcodes: Optional[List[str]] = None):
        base_tokens, base_map = build_default_vocab()
        self.opcodes: List[str] = sorted(set(opcodes)) if opcodes else []
        self.tokens: List[str] = list(base_tokens) + self.opcodes
        self.token_to_id: Dict[str, int] = dict(base_map)
        for i, tok in enumerate(self.opcodes):
            self.token_to_id[tok] = len(base_tokens) + i
        self.vocab_size = len(self.tokens)

    # ── encode ────────────────────────────────────────────────────────────

    def encode(self, text: str, label_index: Optional[Dict[str, int]] = None,
               add_specials: bool = True,
               family: Optional[str] = None,
               atlas_names: Optional[List[str]] = None) -> Tuple[List[int], List[int]]:
        """Tokenize Glyph source. Returns (ids, values).

        label_index: optional {label_name_without_colon: instruction_index}
        so LABEL tokens can carry spatial coordinates in the value channel.
        family: optional program-family key (see FAMILY_TO_TOKEN); when set,
        a family conditioning token is inserted after BOS (Phase 5.5).
        atlas_names: ordered atlas tile names; ':atlas_<name>' refs encode
        as LABEL with reserved value ATLAS_LABEL_BASE + index (Phase 5.6).
        """
        ids: List[int] = [BOS] if add_specials else []
        values: List[int] = [0] if add_specials else []
        if family is not None and add_specials:
            base_family = family.split(":", 1)[0] if ":" in family else family
            if base_family not in FAMILY_TO_TOKEN and atlas_names and base_family in atlas_names:
                base_family = "leaf_call"
            ftok = FAMILY_TO_TOKEN.get(base_family)
            if ftok is not None:
                ids.append(self.token_to_id[ftok])
                values.append(0)
        first_line = True
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue  # transpiler header comments: dropped, not learned
            if not first_line:
                # Phase 5.6: explicit line separators — without them the
                # model glues instructions into one assembler line
                ids.append(NEWLINE)
                values.append(0)
            first_line = False
            pos = 0
            while pos < len(line):
                m = _LINE_RE.match(line, pos)
                if m is None:
                    pos += 1
                    continue
                pos = m.end()
                if m.lastgroup == "comment":
                    ids.append(COMMENT)
                    values.append(0)
                elif m.lastgroup == "label":
                    name = m.group("label")[1:]
                    ids.append(LABEL)
                    if atlas_names and name.startswith("atlas_"):
                        tile = name[len("atlas_"):]
                        values.append(atlas_label_value(tile, atlas_names))
                    else:
                        idx = (label_index or {}).get(name, -1)
                        values.append(int(idx))
                elif m.lastgroup == "num":
                    txt = m.group("num")
                    ids.append(NUM)
                    values.append(int(txt, 16) if txt.lower().startswith("0x") else int(txt))
                elif m.lastgroup == "reg":
                    ids.append(self.token_to_id[m.group("reg")])
                    values.append(0)
                elif m.lastgroup == "str":
                    ids.append(STR)
                    values.append(0)
                elif m.lastgroup == "comma":
                    ids.append(COMMA)
                    values.append(0)
                elif m.lastgroup == "word":
                    tok = m.group("word")
                    tid = self.token_to_id.get(tok)
                    if tid is None:
                        # Unknown identifier: emit as LABEL token, value -1
                        ids.append(LABEL)
                        values.append(-1)
                    else:
                        ids.append(tid)
                        values.append(0)
        if add_specials:
            ids.append(EOS)
            values.append(0)
        return ids, values

    # ── decode ────────────────────────────────────────────────────────────

    def decode(self, ids: List[int], values: Optional[List[int]] = None,
               resolve_labels: bool = False,
               atlas_names: Optional[List[str]] = None) -> str:
        """Reconstruct Glyph source text from ids.

        NUM/LABEL render using values when available. This is the text
        the assembler/oracle will consume. atlas_names: ordered atlas tile
        names, mapping reserved label values (>= ATLAS_LABEL_BASE) back to
        ':atlas_<name>' refs (Phase 5.6).

        resolve_labels=True guarantees assembler-ready output: any LABEL
        whose value is missing or negative (<0) gets a fresh sequential
        :lbl_N name (shared counter across the whole sequence) instead of
        the literal "<LABEL>" the assembler rejects. Numeric label values
        (≥0) still render as :lbl_<v>. Line reconstruction: NEWLINE and
        COMMENT tokens break lines; control-flow terminators (HALT/RET)
        also end the current line, since raw token streams from the model
        carry no newline tokens.
        """
        inv = {i: t for t, i in self.token_to_id.items()}
        out_lines: List[str] = []
        cur: List[str] = []
        lbl_counter = 0
        open_ref = None
        for k, tid in enumerate(ids):
            if tid == PAD:
                continue
            if tid in (BOS, EOS):
                continue
            tok = inv.get(tid)
            # family conditioning tokens are generation-time prefixes only;
            # never reconstructed into source text
            if tok is not None and tok.startswith("<FAMILY_"):
                continue
            if tid == NEWLINE:
                if cur:
                    out_lines.append(" ".join(cur))
                    cur = []
                continue
            tok = inv.get(tid)
            if tok is None:
                continue
            if tok == "<COMMENT>":
                if cur:
                    out_lines.append(" ".join(cur))
                    cur = []
                continue  # comments are not reconstructed
            v = values[k] if values and k < len(values) else None
            if tok == "<NUM>":
                cur.append(str(v) if v is not None else "<NUM>")
            elif tok == "<LABEL>":
                # LABEL semantics by position: first token on a line =
                # label DEFINITION; after other tokens = branch REFERENCE
                # (JMP/CALL/JZ target), always line-final. The model's
                # learned idiom (from transpiler output) is
                #   JMP :over ; :over: ; block
                # i.e. a REF is closed by the NEXT DEF. Pair them: a ref
                # opens a name, the next def reuses it. Unpaired refs at
                # end fall back to their own name; unpaired defs get
                # fresh names.
                # Phase 5.5 fix: flush after the label REGARDLESS of the
                # name source. Generation emits LABEL with value 0 (the
                # non-NUM default), which hit the v>=0 branch and skipped
                # the flush — gluing CALL targets to the next instruction
                # and resolving every label to "index 0".
                # Phase 5.6: reserved values (>= ATLAS_LABEL_BASE) are
                # atlas tile refs -> ':atlas_<name>', flushed like any ref.
                atlas_ref = bool(atlas_names) and v is not None \
                    and v >= ATLAS_LABEL_BASE
                if atlas_ref and atlas_names is not None:
                    tile = atlas_label_name(int(v), atlas_names)
                    cur.append(":atlas_" + (tile or f"unknown_{v}"))
                    out_lines.append(" ".join(cur))
                    cur = []
                elif v is not None and v >= 0:
                    cur.append(f":lbl_{v}")
                    out_lines.append(" ".join(cur))
                    cur = []
                elif resolve_labels:
                    is_ref = bool(cur)
                    if is_ref:
                        cur.append(f":lbl_{lbl_counter}")
                        open_ref = lbl_counter
                        lbl_counter += 1
                    else:
                        if open_ref is not None:
                            cur.append(f":lbl_{open_ref}")
                            open_ref = None
                        else:
                            cur.append(f":lbl_{lbl_counter}")
                            lbl_counter += 1
                    out_lines.append(" ".join(cur))
                    cur = []
                else:
                    cur.append("<LABEL>")
                    out_lines.append(" ".join(cur))
                    cur = []
            else:
                cur.append(tok)
                if tok in ("HALT", "RET", "SYSRET"):
                    out_lines.append(" ".join(cur))
                    cur = []
        if cur:
            out_lines.append(" ".join(cur))
        return "\n".join(out_lines) + ("\n" if out_lines else "")

    # ── persistence ───────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        Path(path).write_text(json.dumps({
            "opcodes": self.opcodes,
            "specials": SPECIAL_NAMES,
            "n_registers": N_REGISTERS,
        }, indent=2))

    @classmethod
    def load(cls, path: str) -> "GlyphTokenizer":
        data = json.loads(Path(path).read_text())
        return cls(opcodes=data["opcodes"])
