# ENG-1 — WGSL unknown-opcode fallthrough (engine divergence)

**Found:** 2026-09-11, builder cron af3e62239ce2, during BK-4 WGSL parity probe
(see `systems/RECEIPT_BK4_JOIN.md`, finding ENG-1).
**Fixed:** 2026-09-11, same cron. Promotion: `6a66f6d` (roadmap row ENG-1 ⏳).
**Fix commit:** this run.

## Symptom → Claim

Python `GlyphCPUv2.step()` (tools/glyph_isa_v2.py:562) **halts** on an unknown
opcode pixel (`opcode is None → self.running = False; return False`).

The WGSL shader's `get_opcode_from_color()` (tools/wgsl_glyph_isa_v2.py:102)
returns `1000u` for an unrecognized color and `main()` had **no branch matching
1000u** — control fell to the shared `cpu.pc = next_pc` writeback, so the
unknown pixel executed as a silent no-op and execution continued.

**Consequence:** a single byte-corrupted opcode pixel diverged the engines —
Python halts, WGSL walks on. Any lockstep/parity claim over corrupted media
was unsound.

## RED (before fix)

`output/eng1_gate_run1_red.txt` — 3 passed, **1 failed**:

```
E           AssertionError: WGSL executed past corruption (fallthrough): r11=99
E           assert 99 == 0
```

Test design (`tests/test_eng1_unknown_opcode.py`):

- Program `LDI r10 7 / HALT / LDI r11 99 / HALT`, first HALT's opcode pixel
  overwritten with `(1,1,1)` (reserved palette, decodes to no opcode on both
  engines).
- Leg 1 control: clean image halts both engines, r10==7.
- Leg 2: CPU halts on the corrupted pixel (pins the oracle so Python can't
  silently soften to continue-noop later).
- Leg 3a liveness control: the exact `LDI r11 99` encoding executes on BOTH
  engines when not blocked by a halt — makes leg 3b's r11 assertion semantic.
- Leg 3b (the discriminator): clean path halts at the real HALT with r11==0 on
  both engines (first-halt semantics; the planted LDI is unreachable when the
  first HALT works). Corrupted: CPU halts, r11==0. Pre-fix WGSL walked past
  the corruption, **executed the planted instruction**, and halted at the
  second HALT with **r11==99** — engine divergence measured semantically, not
  just by halt flag.

Mid-build test correction (disclosed): the first draft asserted the clean path
reaches r11==99; the baker packs instructions contiguously in row 0, so the
clean program legitimately halts at the first HALT and r11==99 is only
reachable via the defect. No assertions weakened — the discriminator is
*r11's value after corruption*, backed by the leg-3a liveness control.

## Fix

`tools/wgsl_glyph_isa_v2.py` (+8 lines): one new branch mirroring Python:

```wgsl
} else if (opcode == 1000u) {
    // ENG-1: unknown opcode — mirror GlyphCPUv2.step()'s halt-on-unknown
    cpu.running = 0u;
    cpus[cpu_id] = cpu;
    return;
}
```

placed before the `cpu.pc = next_pc` writeback, immediately after the
`OPCODE_HALT` branch (same shape as HALT).

## GREEN (after fix)

`output/eng1_gate_run2_green.txt` — **4/4 passed** (0.73s).

## Regressions (all from working tree at fix)

| Suite | Result | Output |
|---|---|---|
| WGSL/parity: test_gh4_wgsl_parity + test_bk2_wgsl_syscall_parity + test_gh25_hilbert_paging + test_wgsl_validation | 13/13 ✅ | output/eng1_regress_wgsl.txt |
| Arc: GH-7/16/18/26-resident + BK-3 + BK-4 | 41/41 ✅ | output/eng1_regress_arc.txt |
| MCP (under /usr/bin/python3 — venv lacks `mcp`): GH-26 glass box + GH-24 S2 | 13/13 ✅ | output/eng1_regress_mcp.txt |
| GH-18 invariant script | 14/14 ✅ exit 0 | output/eng1_regress_gh18inv.txt |

Zero engine semantics changed for known opcodes; the only behavioral delta is
unknown-opcode pixels, which now halt identically on both engines.

## Scope note

ENG-2 (stale 8201/8205 in BK-3's `:__kdone`) remains queued in
`.builder_queue/` as hygiene-only — per its own status line it folds into the
next BK-3-touching ticket, not this engine fix.
