# RESEARCH — DEFECT-31h: SW value-side scratch aliasing (rs2==x30/x29), measured

**Builder:** af3e62239ce2 (GLM cron, glyph-teleoperation + skeleton-handoff-contract loaded)
**Date:** 2026-09-26 ~01:0x CDT
**Head at measurement:** f4fe2946 (my BK-31 research lineage; tracked tree CLEAN)
**Probe:** `.builder_queue/dbg_d31h_sw_value_side_alias_af3e.py` (reuses the proven
dbg_d31f harness module — build_elf/by_pc/tree-vs-HEAD lowering identity/main loop;
tree==HEAD op streams byte-identical per pc in ALL 7 legs; deterministic across 3 runs)
**Backlog:** BK-32 filed to `systems/GLYPH_BACKLOG.md` (BK-31 grep-verified free first)

## Question

BK-31's receipt named a follow-on candidate: the SW VALUE-side collision (rs2==x30)
was observed only via L03, which was CONFOUNDED by the LW address defect (lw x30
destroyed the value before the store ever executed). Is there a clean, independently
measurable SW value-side aliasing class? (New leg of the 31-family, rule 5 satisfied:
31c/31e/31f/31g probed other paths; the value side was never cleanly measured.)

## Source reading (HEAD f4fe2946, tools/rv64i_to_glyph.py SW lowering ~:913-962)

On the UNGUARDED path (rs1 not in {29,30}): address temp = glyph `r30` (= RV x30
under the identity register map), byte_to_word shift scratch = glyph `r29` (= RV x29),
and the value operand is read at `ST` time — AFTER both scratch writes:

```
LDI r30 <imm>; ADD r30 r{rs1}   # r30 == RV x30
LDI r29 2; SHR r30 r29          # r29 == RV x29
ST r30 r{rs2}                   # value read here
```

Predicted: `sw x30, imm(<other>)` lowers to `ST r30 r30` → stores the ADDRESS;
`sw x29, imm(<other>)` lowers to `ST r30 r29` → stores the shift amount 2.
The DEFECT-31 fix paths (rs1==30 → `ST r28 r30`; rs1==29 → `ST r28 r29`) read the
value register untouched, so only the unguarded path aliases.

## Measured legs (all halted=True faulted=False = SILENT; mem[768] vs golden)

| Leg | asm | got | golden | verdict |
|---|---|---|---|---|
| L01 | `li x30,0xBEEF; sw x30,0(x18)` | 0x300 | 0xBEEF | RED — stores the ADDRESS |
| L02 | `li x30,0xBEEF; sw x30,4(x18)` | 0x0 | 0xBEEF | RED — address INTO address slot (self-overwrite: word 769=0x301) |
| L03 | `li x30,0xBEEF; sw x30,0(x0)` | 0x0 | 0xBEEF | RED — stores base 0 |
| L04 | `li x29,0xBEEF; sw x29,0(x18)` | 0x2 | 0xBEEF | RED — stores the shift amount |
| C05 | control: `sw x9,...` normal path | 0xBEEF | 0xBEEF | PASS |
| C06 | control: base-x30 DEFECT-31 fix path | 0xBEEF | 0xBEEF | PASS |
| C07 | control: `sw x30,0(x30)` value==base via fix path | 0xC00 | 0xC00 | PASS |

**3/7 PASS, 4 RED.** C07 is the decomposition proof: with the LW defect removed from
the picture, `sw x30,0(x30)` PASSES via the guarded path — BK-31's confounded L03
(0x300) is now fully attributed to the value-side class, not the LW address path.

## Honesty (rule 6 / rule-1 floors)

- All numbers are structural asserts from GlyphRunner receipts of real runs this tick
  (memory word values, halted/faulted flags) — no rate/latency claims → rule-1 floors
  do not attach.
- NOT verified: no WGSL twin leg; no live xv6-nano repro (latent-only scan pending —
  no landed gate is known to store x29/x30 as a VALUE through an unguarded base;
  the L02 self-overwrite shape writes a SECOND memory word, which is a corruption
  vector beyond the wrong-value class); fix not implemented (proposed in BK-32).
- One surprise vs prediction: L02 stores nothing at mem[768] because `ST r30 r30`
  writes the address into the address slot itself (word 769 = 0x301) — recorded
  exactly as measured.

## Proposed fix shape (BK-32, not implemented)

Extend the DEFECT-31 guard family to the value operand: when rs2 ∈ {29,30} (and rs1
is not already taking that scratch), push the colliding scratch and take the value
from the saved slot at `ST` time — same PUSH/POP pattern already proven twice
(DEFECT-31 store base, DEFECT-30 LBU). Gate: `tests/test_defect31h_sw_value_aliasing.py`
with L01–L04 as RED-first fixtures + C05–C07 controls + a non-vacuity leg (neuter
the new guard → RED).
