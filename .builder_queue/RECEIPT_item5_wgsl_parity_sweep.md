# RECEIPT — Item 5: WGSL parity sweep of 2026-09-22 engine deltas

**Lane:** Glyph GPU OS product lane (builder cron af3e62239ce2)
**Commit at tick start:** 08d0293f (supply round 2, Jericho-directed 12:1x)
**Scope:** one WGSL dispatch-branch fix + its mirrors + one parity test +
one probe. No oracle (tools/glyph_isa_v2.py) changes. No floors touched
(item 6 remains open).

## Sweep disposition (the four 09-22 deltas)

| Delta | Commit | WGSL twin status | Disposition |
|---|---|---|---|
| JALR imm-fold → CALLR | 2f619963 | **DIVERGED — fixed this tick** | real gap, closed with RED→GREEN |
| 0x10 BOOT_LINUX RAM read | 481ec735 | landed same-commit | covered: test_defect_d_ram_scoped_handlers.py:1123 (both seeds, real GPU) |
| CMP3/JLT/JGT | 0292a40d | landed same-commit | covered: test_se025_cmp_tristate.py:322 (3 parametrized legs) |
| _read_path single-view | 4e8a2c94 | no WGSL-visible surface | legitimate omission, documented below |

## The defect (JALR/CALLR)

The 2f619963 JALR fix emits `CALLR r30` for rustc's computed-call idiom
(`auipc ra,0x0; jalr -N(ra)`). The CPU oracle executes CALLR at
glyph_isa_v2.py:1279 (push packed return pc on r31, jump tx*INSTR_WIDTH,ty).
tools/wgsl_glyph_isa_v2.py carried OPCODE_CALLR in _OPCODE_ORDER (:37) — so
it had a const and a color-table check — but the shader body had **no
`opcode == OPCODE_CALLR` branch**: a computed call fell through the entire
else-if chain as a silent no-op. Kernel text that computes a call would
halt having never executed the callee, on the shader path only.

Found by dispatch-coverage probe (output/probe_callr_coverage.py): 31
opcode consts, 2 initially flagged (JNZ false positive — compound
`OPCODE_JNZ || OPCODE_JNE` branch at :680; CALLR real).

## Evidence

RED (fix stashed, HEAD 08d0293f tree) — probe + gate, both discriminating:

```
$ python3 output/probe_callr_parity.py
CPU   : halted=True r10=0x2a
WGSL  : halted=True r10=0x0 steps=4
PARITY: FAIL
FAILED tests/test_gh4_wgsl_parity.py::test_gh4_computed_call_callr_parity
1 failed in 1.42s
```

(WGSL steps=4 is itself the tell: LDI, LDI, CALLR-as-noop, HALT — the
callee never ran.)

GREEN (fix in tree):

```
$ python3 output/probe_callr_parity.py
CPU   : halted=True r10=0x2a
WGSL  : halted=True r10=0x2a steps=6
PARITY: PASS
$ python3 -m pytest tests/test_gh4_wgsl_parity.py -q
4 passed in 2.30s
```

Regression sweep, post-fix: test_bk2_wgsl_syscall_parity +
test_se022a_read_parity + test_se024_wgsl_parity +
test_se025_cmp_tristate + test_wgsl_triple_sync → 34 passed;
test_defect_d_ram_scoped_handlers + gh4 + bk12_wgsl_tier +
wgsl_validation → 41 passed; test_glyph_cc → 9 passed;
test_rv64i_to_glyph_{proc,arithshift} → 2 passed;
test_read_path_single_view + test_pillar21_abi_spec_rotguard → 23 passed.

## What the PASS does NOT prove

- The new leg exercises one CALLR shape (register-held instruction index,
  callee-returns). It does not exercise KJMP-routed switch_to returns,
  CALLR into paged/tick-preempted regions, or nested computed calls.
- The probe first ran a non-discriminating version (r10 written on the
  fallthrough path too — it "passed" at HEAD). It was rewritten so the
  callee is the ONLY r10 writer before its RED was trusted. The landed
  test inherits the discriminating shape.
- _read_path has no WGSL parity leg BY DESIGN: WGSL's FILE_READ/FILE_WRITE
  arms are pinned honest no-op stubs (test_defect_d:327,:524) that never
  read path strings; a single-view read change cannot touch them. This is
  a named gap ticket in prose, not code: if WGSL file I/O ever gains a
  real twin, the single-view rule must be ported with it.
- No floors/rate claims made (item 6 territory; check_regime not run).

## Files

- tools/wgsl_glyph_isa_v2.py — OPCODE_CALLR dispatch branch (twin of
  glyph_isa_v2.py:1279), +17 lines
- glyph_dispatch/src/glyph/wgsl_glyph_isa_v2.py, glyph_dispatch/src/wgsl_glyph_isa_v2.py — md5-identical mirrors
- tests/test_gh4_wgsl_parity.py — test_gh4_computed_call_callr_parity
- output/probe_callr_parity.py, output/probe_callr_coverage.py — probes
