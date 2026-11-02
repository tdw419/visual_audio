# Synthetic Corpus Receipt — Phase 3b

**Date**: 2026-09-05
**Generator**: `tools/glyph_gpt/synth.py` (seed 1337, fully deterministic)
**Receipts**: `tools/glyph_gpt/synth_receipts.jsonl` (1250 entries)
**Command**: `python3 tools/glyph_gpt/synth.py --n 250 --out tools/glyph_gpt/synth_receipts.jsonl`

## Result: 1250/1250 oracle-verified matches

| family | match | total | trains |
|---|---|---|---|
| alu_chain | 250 | 250 | ALU dependence chains, accumulator semantics |
| conditional | 250 | 250 | forward branches, branch-over-block (abs) |
| counted_loop | 250 | 250 | backward branches, countdown accumulators |
| mem_pass | 250 | 250 | sw/lw roundtrips, safe data arena |
| leaf_call | 250 | 250 | JAL/JALR, glyph CALL/RET, ra discipline |

## Pipeline per program

RV32I bytes (seeded template) → `rv64i_to_glyph.transpile_rv32i_to_glyph` →
`assemble_glyph_to_pixels` (two-pass labels) → `GlyphCPUv2.run` → register
receipt compared against independent Python reference executing the same
control flow. Match requires exact 32-bit equality on checked registers at
ECALL and steps < max_instructions.

## Generator bugs the oracle caught (why gate-everything matters)

1. **Nondeterministic reference** (alu_chain v1): the reference re-drew its
   initial constant instead of using the emitted one → guaranteed mismatch.
   Deterministic receipts require the reference to read the SAME constants
   the assembler bytes carry.
2. **S-type immediate sign violation** (mem_pass): addrs above 2047 wrapped
   negative (2668 → −1428), stores landed in unmapped/aliased memory, lw
   returned 0. Fixed: addr ∈ [0, 2047), 4-aligned, below PTR_TABLE_BASE.
   Guardrail #3 from the plan caught live.

## Transpiler/CPU semantic contracts discovered (probes 1-10)

- **ECALL is the only clean terminal** (transpiles to glyph HALT). EBREAK is
  the syscall trap (`SYSCALL r10`) — it does NOT halt; a syscall-0 fires and
  execution falls through.
- **JAL/JALR leaf calls work** via glyph CALL/RET with r31 stack; return
  address in ra is byte-accurate (probe: x1=8 for pc 4 jal).
- **BNE emission shape**: `CMP r_r28; JZ :__skip; JMP :target; :__skip` —
  the pattern the model must learn for "branch if not equal".
- **Imm-const lowering**: `ADDI rX, rY, -1` becomes `LDI r29 0xffffffff;
  ADD rY r29` — 64-bit two's-complement via a scratch register (r28/r29/r30
  are transpiler-reserved scratch; programs that clobber them would break.
  Templates avoid registers 28-31).
- `run()` returns the step count; `running` False = halted; steps ==
  max_instructions ⇒ no_halt (timeout).

## Receipt schema (JSONL)

{"path": "synth/<family>_<id>.S", "sha256": …, "dialect": "isa_v2",
 "source": "synth", "family": …, "asm_hex": …,
 "oracle": {"match": bool, "steps": int, "expected_regs": {…},
            "observed_regs": {…}, "error": null}}

## Next (Phase 3c)

dataset.py: corpus.jsonl (48 repo) + synth_receipts.jsonl (1250 synth) →
transpile asm_hex → glyph text → tokenize (value channel) → npz sequences.
Family-balanced sampling; SFT set = oracle match only.
