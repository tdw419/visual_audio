# GlyphGPT Skeleton — Signed Off

**Date**: 2026-09-05
**Branch**: glyph-transpiler-autoloop
**Status**: Phase 1/2 complete — skeleton verified 25/25, no implementation committed.

## Purpose

Opcode-level LLM that generates Glyph assembly for the spatial OS, trained on
transpiler ground truth and gated by the GlyphCPUv2 execution oracle.

## Boundary Map

```
.glyph corpus (370 files)        RV64I/C binaries
        │                              │
        ▼                              ▼
   corpus.py ─────────────▶ corpus.jsonl ◀──── transpile synth
        │                              │
        └──────────────┬───────────────┘
                       ▼
          tokenizer.py  (GlyphTokenizer: text ⇄ ids + value channel)
                       ▼
          dataset.py   (ids → npz training sequences)
                       ▼
          model.py     (small decoder-only transformer)
                       ▼
          train.py     (training loop → ckpt.pt)
                       ▼
          generate.py ─▶ .glyph text ─▶ oracle.py ─▶ GlyphCPUv2
                                          │
                                          ▼
                          PASS (regs + memory hash) / FAIL → DPO pairs
```

## External Contracts (locked against live code, verified in test_skeleton.py)

| Module | Contract | Verified by |
|--------|----------|-------------|
| tokenizer.GlyphTokenizer | text ⇄ (ids, values); NUM/LABEL carry int values; BOS/EOS framing; round-trip stable modulo COMMENT | test [2] on real rv64i_to_glyph output |
| tokenizer | handles BOTH dialects: Glyph ISA v2 (`LDI r1 0x5`) and pixel_interpreter (`SET`, `LOAD_COORD (222, 221)`) | test [3] on fib.glyph |
| corpus.collect_repo_glyph_files | repo *.glyph → [{path, text, source}] | stub present |
| corpus.synthesize_from_rv64i | binaries → transpile → oracle-gated synth entries with register ground truth | stub present |
| dataset.build_sequences | corpus → (ids, values) int32 arrays, chunked to seq_len | stub present |
| model.GlyphGPT | forward(ids, values, targets) → (logits, loss); config in checkpoint | test [5]: shapes + loss contract on stub |
| oracle.run_oracle | text → OracleResult{passed, steps, registers, memory_hash}; expect_registers gate | stub present; contract proven interactively (see below) |
| train.train | dataset npz → checkpoint + metrics dict | stub present |
| generate | ckpt → constrained decode → cut at EOS → oracle gate | stub present; extract_to_halt implemented + tested |

## Execution Oracle — Live Proof (pre-skeleton)

```python
prog = bytes([0x93,0x00,0x50,0x00, 0x13,0x01,0x70,0x00, 0xb3,0x80,0x10,0x00])
# addi x1,x0,5; addi x2,x0,7; add x3,x1,x2
asm_text = transpile_rv32i_to_glyph(prog)
img, labels = assemble_glyph_to_pixels(asm_text, cols_instrs=8)   # (19, 32, 3)
cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
cpu.run(img, max_instructions=500)   # 6 steps
# Register receipt: r1=10, r2=7. ADD semantics: rd += rs2 (accumulator-style).
# The transpiler emits extra moves to emulate three-operand RISC-V adds.
# **The oracle ground truth comes from GlyphCPUv2 execution, never from
# assumed semantics.**
```

Key discovery: `ADD r1 r1` → r1=10 (5+5), i.e. the accumulator-style
`ADD rd rs2` semantics of Glyph ISA v2. The transpiler emits `ADD r3 r2`-style
sequences to emulate three-operand RISC-V adds. **The oracle ground truth comes
from GlyphCPUv2 execution, never from assumed semantics.**

## Tokenizer Design Decision

Value channel (parallel int32 array next to token ids) — NUM/LABEL tokens
carry their numeric payload. Rationale: the execution oracle checks exact
register values, so immediates must be exactly recoverable; a `<NUM>`-only
vocab cannot express that. This is an addition over pixel-hypervisor's
266-token design, which had no value channel.

## Interface Discovery During Skeleton (Round 1→2 adjustments)

1. `SPECIAL` is the id→name map (alias of SPECIAL_NAMES); token constants
   PAD=0..COLON=9 are module-level ints.
2. decode() drops COMMENT tokens by design — comments don't affect assembler
   semantics. Round-trip stability is defined modulo COMMENT (test [2]).
3. GlyphAssemblerV2.assemble does NOT resolve labels; label→coordinate
   resolution lives in rv64i_to_glyph.assemble_glyph_to_pixels (two-pass).
   Oracle must use assemble_glyph_to_pixels, not GlyphAssemblerV2 directly.
4. The pixel_interpreter dialect and Glyph ISA v2 are different instruction
   sets. Corpus entries carry `source` so training can be filtered by dialect.

## Implementation Roadmap

- **Phase 3a**: corpus.py — collect 370 repo files, dedupe, write JSONL
- **Phase 3b**: corpus.synthesize_from_rv64i — transpile + oracle-gate synthetic programs
- **Phase 3c**: dataset.py — sequences → npz
- **Phase 3d**: model.py real forward (causal attention, value embeddings)
- **Phase 3e**: train.py — real loop, checkpoint with embedded config
- **Phase 4a**: oracle.run_oracle + check_generation
- **Phase 4b**: generate.py end-to-end (prompt → tokens → text → oracle PASS/FAIL receipt)
- **Phase 4c**: quality loop (observe → evaluate → act) cloned from pixelflow pattern
- **Phase 5**: acceptance gate — ≥95% syntactic validity, ≥80% oracle PASS on
  held-out prompts, measured by tools/glyph_gpt/test_skeleton.py successors

## Verification

```bash
python3 tools/glyph_gpt/test_skeleton.py
# Skeleton verification: 25 passed, 0 failed
```
