# RESEARCH — DEFECT-31g candidate: LW address-path scratch aliasing (rs1==x30)

- **Tick:** 2026-09-26 ~00:4x CDT, builder af3e62239ce2, Phase-1c research (no new supply: queue active=null, item-25 RESERVED operator-signoff, no RULING newer than last landed commit 7c0d62da)
- **HEAD measured:** 7c0d62da; tracked tree clean at tick start
- **Family:** LW/SW ADDRESS path (new op-family; 31c = SB/SH else branches, 31e = store fix branches value-side, 31f = ALU/imm — the load path was never probed)

## Question

Does the LW lowering alias its glyph-r30 address temp with an rs1==x30 RV base register (the exact DEFECT-31 shape SW was fixed for), and does it do so silently?

## Method

- Source reading: `tools/rv64i_to_glyph.py:899-909` — LW emits `LDI r30 <imm>; ADD r30 r{rs1}; [LDI r29 2; SHR r30 r29]; LD r{rd} r30` with NO rs1==30 guard. The sibling SW got the DEFECT-31 fix at `:913-928` (rs1==30 → PUSH r30, address in r28, shift in r26, POP r30). Asymmetric.
- Probe: `.builder_queue/dbg_d31g_lw_addr_alias_af3e.py` — reuses d31f's proven harness module (gcc -march=rv32i -mabi=ilp32 -nostdlib, transpiled through tree AND `git show HEAD` snapshot with per-pc op-stream equality, baked via libc_runtime_kernel_image, run on GlyphRunner, mem[768] vs golden). 6 hand-written asm legs, store convention base x18=0xC00.
- Tree==HEAD lowering identical per pc in all 6 legs → latent at HEAD, not a lane regression. Deterministic: 3 runs, identical output.

## Findings (structural asserts from GlyphRunner receipts; no rate/latency → rule-1 floors does not attach)

| Leg | Program | mem[768] | golden | Verdict |
|---|---|---|---|---|
| L01 | `lw x9, 0(x30)` base x30 | 0x0 | 0xabcd | **RED** |
| L02 | `lw x9, 8(x30)` base x30 | 0x0 | 0xabcd | **RED** |
| L03 | `lw x30, 0(x30)` dest=base | 0x300 | 0xabcd | **RED** (confounded, see below) |
| L04 | control: base x18 | 0xabcd | 0xabcd | PASS |
| L05 | control: SW base x30 (DEFECT-31 fix path) | 0xbeef | 0xbeef | PASS |
| L06 | control: lw/sw roundtrip x18 | 0xabcd | 0xabcd | PASS |

- All REDs halted=True faulted=False → **silent** misexecution.
- Mechanism, L01/L02: `LDI r30 0; ADD r30 r30` → r30=0 → `LD` reads word 0. Note imm=0 does NOT save the leg — the clobber happens before the ADD regardless of immediate.
- L05 PASS proves the asymmetry is real: the identical source-level shape (`li x30,0xC00; sw x9,0(x30)`) is guarded, the LW twin is not.
- L03 disclosure: dest==base x30 confounds TWO aliasings — after LW mis-loads, the final `sw x30, 0(x18)` hits SW's rs2==x30-vs-address-temp collision (glyph r30 holds the computed address 0x300 when ST reads the value). L03 is directional only; the load-bearing legs are L01/L02 (single-defect). A second candidate defect (SW rs2==x30 value-side) is implied but NOT separately measured this tick.

## Candidate backlog item (BK-31)

**LW lowering: add the rs1==x30/rs1==x29 address-temp guard (mirror the DEFECT-31 SW fix).**
Fix shape = the SW pattern at `tools/rv64i_to_glyph.py:913-928`: when rs1∈{29,30}, PUSH r30, compute the address in r28 (shift temp r26), POP r30. Zero-risk twin of a landed fix.
Gate: `tests/test_defect31g_lw_addr_alias.py` — L01/L02 probe programs as fixtures (RED-first at HEAD), L04/L05/L06 controls, plus L7: non-vacuity (neuter the new guard → RED). Worktree isolation per AGENTS.md (engine-core transpiler).
Follow-on candidate (unmeasured): SW rs2==x30 value-side collision observed in L03 — needs its own clean leg before filing as a defect.

## Honesty

- NOT verified: no WGSL twin leg (transpiler-side); no live xv6-nano repro (latent-only — no landed gate allocates x30 as an LW base; all landed gates stay GREEN, rule 2 not triggered); SW rs2==x30 class measured only via the confounded L03; fix proposed, not implemented.
- Numbers are structural asserts (mem words, halted/faulted booleans, per-pc lowering equality) from real runs this tick; 3-run determinism checked.
