#!/usr/bin/env python3
"""
generate.py — GlyphGPT code generation CLI + oracle end-to-end.

Phase 5.3: grammar-constrained (FSM) decoding. Glyph ISA v2 has a rigid
per-line grammar, so generate() masks illegal token classes at every step:

    LINE_START -> opcode | LABEL(def) | EOS
    opcode     -> first operand class per arity table below
    operands   -> subsequent operand classes, then back to LINE_START
    HALT       -> EOS forced (a program ends at its first halt)

Masking is a boolean logit mask (illegal ids set to -inf) — negligible
cost, and syntactic validity becomes structural rather than learned.
Value immediates still come from the value classifier head.

Full loop: prompt → tokenize → masked decode → cut at EOS → decode to
glyph text (label synthesis) → assemble → execute on GlyphCPUv2 →
PASS/FAIL receipt with full register state.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import numpy as np
import torch

_HERE = Path(__file__).resolve().parent
_TOOLS = _HERE.parent
_REPO = _TOOLS.parent
for p in (str(_REPO), str(_TOOLS), str(_HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from glyph_gpt.model import (
    GlyphGPT, GlyphGPTConfig, load_checkpoint, bin_to_value, value_to_bin,
)
from glyph_gpt.tokenizer import (
    GlyphTokenizer, PAD, BOS, EOS, NUM, LABEL, NEWLINE,
    atlas_label_value, ATLAS_LABEL_BASE,
)

# ─── Operand arity table (mirrors glyph_isa_v2.GlyphAssemblerV2.assemble) ──
# class names: REG (r-token), NUM (immediate), LABEL (branch target)
OP_ARITY = {
    "LDI":  ["REG", "NUM"],
    "ADD":  ["REG", "REG"], "SUB": ["REG", "REG"], "CMP": ["REG", "REG"],
    "AND":  ["REG", "REG"], "OR":  ["REG", "REG"], "XOR": ["REG", "REG"],
    "SHL":  ["REG", "REG"], "SHR": ["REG", "REG"], "ROTR": ["REG", "REG"],
    "LD":   ["REG", "REG"], "ST":  ["REG", "REG"],
    "JMPR": ["REG"], "CALLR": ["REG"], "KJMP": ["REG"],
    "PRT":  ["REG"], "PUSH": ["REG"], "POP": ["REG"],
    "SYSCALL": ["REG"],
    "JMP":  ["LABEL"], "JZ": ["LABEL"], "CALL": ["LABEL"],
    "HALT": [], "RET": [], "SYSRET": [],
}


class GlyphFSM:
    """Finite-state machine over token classes for masked decoding."""

    def __init__(self, tok: GlyphTokenizer,
                 ldi_reg_vals: "dict | None" = None,
                 family: "str | None" = None,
                 target_tile: "str | None" = None):
        self.tok = tok
        self.family = family
        self.target_tile = target_tile
        # Base family resolution: e.g. 'leaf_call:memcpy' -> 'leaf_call'
        self.base_family = family.split(":", 1)[0] if (family and ":" in family) else family
        if self.target_tile is None and family and ":" in family:
            self.target_tile = family.split(":", 1)[1]
        self.is_atlas_call = (self.base_family == "leaf_call" or self.target_tile is not None)
        vocab = tok.vocab_size
        inv = {i: t for t, i in tok.token_to_id.items()}
        self.op_ids = {}       # opcode name -> id
        self.reg_ids = set()   # ids of r0..r31
        for i in range(vocab):
            t = inv.get(i, "")
            if t in OP_ARITY:
                self.op_ids[t] = i
            elif t.startswith("r") and t[1:].isdigit():
                self.reg_ids.add(i)
        # model-side control tokens
        self.state = "LINE_START"
        # Phase 5.4 valcond: (LDI, reg) -> admissible value set, derived
        # from the oracle-verified corpus. None = feature disabled.
        self.ldi_reg_vals = ldi_reg_vals or {}
        # in-context copy prior: values already seen in this generation
        self.seen_vals: set = set()
        self._last_ldi_reg: "str | None" = None
        # family axiom state: last completed instruction line, e.g. 'LDI r1'
        self._last_complete_line: "str | None" = None
        self._last_line_ops: "list | None" = None
        self._force_call: bool = False
        # Phase 5.6: atlas caller dispatch done -> next line MUST be HALT
        self._force_halt: bool = False
        self._atlas_names: "list | None" = None

    # allowed token-id set for the current state
    def allowed(self) -> set:
        s = self.state
        if s == "LINE_START":
            return set(self.op_ids.values()) | {EOS} | {NEWLINE}
        if s.startswith("WANT:"):
            cls = s.split(":", 1)[1]
            if cls == "REG":
                return set(self.reg_ids)
            if cls == "NUM":
                return {NUM}
            if cls == "LABEL":
                return {LABEL}
        raise ValueError(f"bad state {s}")

    def advance(self, tok_id: int, val: "int | None" = None) -> None:
        inv = {i: t for t, i in self.tok.token_to_id.items()}
        t = inv.get(tok_id, "")
        s = self.state
        self._cur_val = val
        # Phase 5.6: after the forced-HALT line completes, release the
        # constraint (the caller is terminated; EOS follows naturally)
        if s == "LINE_START" and self._force_halt \
                and tok_id not in (NEWLINE,):
            self._force_halt = False
        # valcond bookkeeping: track the opcode whose operands we're
        # reading and the register an LDI targets (for value candidates)
        if s == "LINE_START":
            if tok_id == EOS:
                return
            self._pending_op = t
            if not (t.startswith("r") and t[1:].isdigit()):
                self._last_ldi_reg = None
            # family axiom tracking: remember the last completed instruction
            # line ('LDI r1' = the leaf_call call-setup idiom)
            if self._last_line_ops is not None:
                self._last_complete_line = " ".join(self._last_line_ops)
            self._last_line_ops = []
            arity = OP_ARITY.get(t)
            if arity is None:
                # label definition: own line, back to line start
                self.state = "LINE_START"
                return
            if not arity:
                # zero-operand op (HALT/RET): line done
                self.state = "LINE_START"
                return
            self.state = f"WANT:{arity[0]}"
            self._pending = arity[1:]
            return
        if s.startswith("WANT:"):
            if self._pending_op == "LDI" and t.startswith("r") \
               and t[1:].isdigit():
                self._last_ldi_reg = t
            # Phase 5.6: was the CALL operand an atlas ref? The LABEL's
            # reserved value rides in the values channel of this token.
            self._last_call_label_atlas = bool(
                self._pending_op == "CALL" and t == "<LABEL>"
                and self._cur_val is not None
                and self._cur_val >= ATLAS_LABEL_BASE
                and self._atlas_names)
            self._last_line_ops.append(t)
            arity_rest = list(getattr(self, "_pending", []))
            if arity_rest:
                self.state = f"WANT:{arity_rest[0]}"
                self._pending = arity_rest[1:]
            else:
                self.state = "LINE_START"
                # family axiom trigger: a just-completed 'LDI r1 <imm>'
                # line in leaf_call/atlas context MUST be followed by CALL
                self._force_call = (self.is_atlas_call
                                    and self._pending_op == "LDI"
                                    and self._last_ldi_reg == "r1")
                # Phase 5.6 caller-termination: a just-completed
                # 'CALL :atlas_*' line in an atlas family means the
                # dispatch is done — the linker contract says the caller
                # HALTs next. The atlas ref shows up as the LABEL token
                # consumed a moment ago (value >= ATLAS_LABEL_BASE).
                if (self.is_atlas_call
                        and self._pending_op == "CALL"
                        and self._last_call_label_atlas):
                    self._force_halt = True
                    self._force_call = False

    def value_candidates(self) -> set:
        """Admissible values for the NUM we're about to emit: the corpus
        (LDI, reg) set unioned with the in-context copy prior. Bin 0
        (untabled catch-all) never enters masks. Empty set = no mask."""
        if self.state != "WANT:NUM" or self._pending_op != "LDI" \
           or not self._last_ldi_reg:
            return set()
        cands = set(self.ldi_reg_vals.get(self._last_ldi_reg, ()))
        cands |= self.seen_vals
        return cands

    def mask_logits(self, logits: torch.Tensor) -> torch.Tensor:
        """Return logits with disallowed ids set to -inf. EOS only allowed
        at LINE_START (program ends at a halt boundary).

        Phase 5.5 family axiom: in leaf_call, the LDI-r1 setup idiom is
        ALWAYS followed by CALL (the family ABI: r1 = call config, then
        the subroutine invocation). The model prefers the cheaper inlined
        path even after upsampling; the contract requires the specific
        path, so — exactly like operand arity — the family ABI is an
        assembler-level truth the FSM may enforce. Scoped strictly:
        family == leaf_call, only at LINE_START right after an LDI r1 NUM
        line. No candidate family → no rule.

        Phase 5.6 caller-termination axiom: in an atlas family, once the
        caller has dispatched 'CALL :atlas_*', the caller's job is DONE —
        the atlas routine returns into the next PC and the caller must
        HALT. The line following a completed atlas-CALL line is therefore
        forced to HALT. Same class of fact as the CALL axiom: caller
        lifecycle after a dispatched call is defined by the linker's
        contract, not learned.
        """
        allowed = self.allowed()
        if (getattr(self, "_force_call", False)
                and self.state == "LINE_START"):
            call_id = self.op_ids.get("CALL")
            if call_id is not None:
                allowed = {call_id}
        if (getattr(self, "_force_halt", False)
                and self.state == "LINE_START"):
            halt_id = self.op_ids.get("HALT")
            if halt_id is not None:
                allowed = {halt_id}
        mask = torch.full_like(logits, float("-inf"))
        for i in allowed:
            mask[i] = 0.0
        return logits + mask


@torch.no_grad()
def generate(prompt_ids: list, prompt_values: list, model: GlyphGPT,
             max_new_tokens: int = 256, temperature: float = 0.8,
             greedy: bool = False, tok: GlyphTokenizer = None,
             use_fsm: bool = True,
             ldi_reg_vals: "dict | None" = None,
             family: "str | None" = None,
             atlas_names: "list | None" = None,
             target_tile: "str | None" = None) -> tuple:
    """Autoregressive decode with value head + FSM grammar mask + valcond
    value-candidate masking. Returns (new_ids, new_values)."""
    model.eval()
    ids = list(prompt_ids)
    values = list(prompt_values)
    max_seq = model.config.max_seq_len

    # Phase 5.8: resolve target atlas tile from parameter or family/intent
    resolved_tile = target_tile
    if resolved_tile is None and family:
        if ":" in family:
            resolved_tile = family.split(":", 1)[1]
        elif atlas_names and family in atlas_names:
            resolved_tile = family
    if resolved_tile is None and (family == "leaf_call" or (atlas_names and "double" in atlas_names)):
        resolved_tile = "double"

    fsm = GlyphFSM(tok, ldi_reg_vals, family=family, target_tile=resolved_tile) if (
        use_fsm and tok is not None) else None
    if fsm is not None:
        # Phase 5.6: the FSM needs the atlas namespace during warmup too
        fsm._atlas_names = atlas_names
    # fast-forward FSM over the prompt so masking starts in the right state
    if fsm is not None:
        for tid, v in zip(prompt_ids, prompt_values):
            if tid in (BOS, PAD):
                continue
            if fsm.state == "WANT:NUM" and fsm._pending_op == "LDI" \
               and fsm._last_ldi_reg:
                fsm.seen_vals.update(v_ for v_ in [v] if v not in (0, -1))
            fsm.advance(tid, v)
    for _ in range(max_new_tokens):
        ctx_ids = ids[-max_seq:]
        ctx_vals = values[-max_seq:]
        ids_t = torch.tensor([ctx_ids], dtype=torch.long)
        vals_t = torch.tensor([ctx_vals], dtype=torch.long)
        logits, _ = model(ids_t, vals_t)
        next_logits = logits[0, -1] / temperature
        if fsm is not None:
            next_logits = fsm.mask_logits(next_logits)
        # value head prediction for the token we're about to emit
        if model.config.value_head_mode == "cls":
            v_logits = model._last_value_pred[0, -1]
            v_bin = int(v_logits.argmax())
            # Phase 5.4 valcond: restrict to admissible value bins when
            # the next token will be an LDI immediate. Safety fallback:
            # empty candidate set (or all -inf) -> keep unmasked argmax.
            if fsm is not None and fsm.state == "WANT:NUM":
                cands = fsm.value_candidates()
                if cands:
                    cand_bins = [value_to_bin(v) for v in cands]
                    cand_bins = [b for b in cand_bins if b != 0]
                    if cand_bins:
                        sub = v_logits[cand_bins]
                        v_bin = cand_bins[int(sub.argmax())]
            next_val_pred = bin_to_value(v_bin)
        else:
            v_pred = float(model._last_value_pred[0, -1])
            next_val_pred = round(max(-1.0, min(1.0, v_pred))
                                  * model.config.value_scale)
        if greedy:
            next_id = int(next_logits.argmax())
        else:
            probs = torch.softmax(next_logits, dim=-1)
            next_id = int(torch.multinomial(probs, 1))
        if next_id == EOS:
            ids.append(EOS)
            values.append(0)
            break
        # value prediction lands only on NUM positions... except atlas
        # refs: a LABEL right after CALL in an atlas family is a tile
        # ref with a RESERVED value (ATLAS_LABEL_BASE + tile index). The
        # value head can't express those (outside bin table), so the
        # family ABI assigns it deterministically — same class of fact
        # as the CALL axiom. Phase 5.6/5.8.
        next_val = (next_val_pred if next_id == NUM else 0)
        if (next_id == LABEL and fsm is not None
                and getattr(fsm, "is_atlas_call", False)
                and fsm._pending_op == "CALL"
                and atlas_names):
            chosen_tile = getattr(fsm, "target_tile", None) or resolved_tile or "double"
            if chosen_tile not in atlas_names:
                chosen_tile = atlas_names[0] if atlas_names else "double"
            next_val = atlas_label_value(chosen_tile, atlas_names)
        ids.append(next_id)
        values.append(next_val)
        if fsm is not None:
            # copy prior: a just-emitted NUM value becomes admissible
            if next_id == NUM and next_val not in (0, -1):
                fsm.seen_vals.add(next_val)
            # Phase 5.6: FSM sees the values channel (atlas ref detection)
            fsm._atlas_names = atlas_names
            fsm.advance(next_id, next_val)
    return ids, values


def extract_to_halt(ids: list, eos_token_id: int = EOS) -> list:
    """Cut generation at first EOS (program terminator)."""
    out = []
    for t in ids:
        if t == eos_token_id:
            break
        out.append(t)
    return out


def ids_to_text(tok: GlyphTokenizer, ids: list, values: list,
                resolve_labels: bool = True) -> str:
    """Assembler-ready text: label synthesis on by default (Phase 5.2)."""
    return tok.decode(ids, values, resolve_labels=resolve_labels)


def run_generated(text: str, cols_instrs: int = 8) -> dict:
    """Assemble + execute generated glyph text. Returns receipt dict."""
    from rv64i_to_glyph import assemble_glyph_to_pixels
    from glyph_isa_v2 import OpcodeMapV2, GlyphCPUv2
    receipt: dict = {"assembled": False, "executed": False, "halted": False}
    try:
        img, labels = assemble_glyph_to_pixels(text, cols_instrs=cols_instrs)
        receipt["assembled"] = True
        cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=cols_instrs)
        with contextlib.redirect_stdout(io.StringIO()):
            steps = cpu.run(img, max_instructions=5000)
        receipt["executed"] = True
        # Lever #2: a bounds fault stops the CPU too, so `not cpu.running`
        # alone would mis-report an OOB store as a clean HALT. Surface the
        # fault explicitly and exclude it from `halted`.
        receipt["faulted"] = bool(getattr(cpu, "faulted", False))
        if receipt["faulted"]:
            receipt["fault_addr"] = int(getattr(cpu, "fault_addr", 0)) & 0xFFFFFFFF
        receipt["halted"] = (not cpu.running) and not receipt["faulted"]
        receipt["steps"] = int(steps)
        nreg = len(cpu.registers)
        receipt["registers_full"] = [int(cpu.registers[i]) & 0xFFFFFFFF
                                     for i in range(nreg)]
        receipt["registers"] = receipt["registers_full"][:8]
        receipt["memory"] = [int(m) & 0xFFFFFFFF for m in cpu.memory]
    except Exception as e:
        receipt["error"] = f"{type(e).__name__}: {e}"
    return receipt


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate Glyph code with GlyphGPT")
    ap.add_argument("prompt", nargs="?", default=None)
    ap.add_argument("--checkpoint", default=str(_HERE / "checkpoint.pt"))
    ap.add_argument("--tokenizer", default=str(_HERE / "tokenizer.json"))
    ap.add_argument("--tokens", type=int, default=128)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--greedy", action="store_true")
    ap.add_argument("--no-fsm", action="store_true",
                    help="disable grammar-constrained decoding")
    ap.add_argument("--no-valcond", action="store_true",
                    help="disable value-candidate masking")
    ap.add_argument("--no-run", action="store_true",
                    help="skip the execution oracle")
    ap.add_argument("-i", "--interactive", action="store_true")
    args = ap.parse_args()

    model = load_checkpoint(args.checkpoint)
    tok = GlyphTokenizer.load(args.tokenizer)

    # Phase 5.4 valcond: corpus-derived (LDI, reg) candidate sets
    ldi_reg_vals = None
    if not args.no_valcond:
        from glyph_gpt.synth import ldi_reg_value_sets
        ldi_reg_vals = ldi_reg_value_sets(_HERE / "synth_receipts.jsonl")

    prompt = args.prompt or ":__entry\nLDI r5 7\n"
    prompt_ids, prompt_vals = tok.encode(prompt)
    # feed prompt minus its EOS so generation continues from it
    ctx_ids = prompt_ids[:-1]
    ctx_vals = prompt_vals[:-1]
    ids, vals = generate(ctx_ids, ctx_vals, model,
                         max_new_tokens=args.tokens,
                         temperature=args.temperature, greedy=args.greedy,
                         tok=tok, use_fsm=not args.no_fsm,
                         ldi_reg_vals=ldi_reg_vals)
    # cut everything before the prompt end, then cut at first EOS
    gen_ids = extract_to_halt(ids[len(ctx_ids):])
    gen_vals = vals[len(ctx_ids):len(ctx_ids) + len(gen_ids)]
    text = ids_to_text(tok, [BOS] + gen_ids, [0] + gen_vals)

    print("=== generated glyph ===")
    print(text)
    if args.no_run:
        return
    receipt = run_generated(text)
    print("=== oracle receipt ===")
    print(json.dumps(receipt, indent=2))
    status = "PASS" if receipt.get("halted") else "FAIL"
    print(f"[{status}] halted={receipt.get('halted')} "
          f"steps={receipt.get('steps')} regs[:8]={receipt.get('registers')}")


if __name__ == "__main__":
    main()
