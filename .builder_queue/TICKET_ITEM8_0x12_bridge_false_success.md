# TICKET — ITEM8 follow-up: WGSL twin 0x12 RUN2 returns 0 (false spawn-success) via GeOS bridge exclusion

**Filed:** 2026-09-22, builder cron af3e62239ce2, product lane round-3 item 8
**Type:** twin (WGSL) defect, bounded fix, shader-side one-line exclusion
**Status:** CLOSED — landed 2026-09-22 15:47 CDT, commit `97b7732d`
(builder cron af3e62239ce2). Receipt:
`.builder_queue/RECEIPT_TICKET_ITEM8_bridge_fix.md`. Measured post-fix:
0x12 python=-1 twin=-1 (u32 4294967295) — PARITY.

## The measured defect

`SYSCALL 0x12 RUN2` (18 decimal) has no standalone branch in the WGSL twin
(`tools/wgsl_glyph_isa_v2.py`). It falls into the GeOS reserved-range bridge:

```
} else if (syscall_num >= 16u && syscall_num <= 255u) { // GeOS MMIO
    cpu.registers[rd] = 0u;
```

so the twin returns **0 — a false spawn-success** — where the Python reference
engine returns -1 (containment refusal on an empty path, and on every refusal
path). Measured 2026-09-22 on live hardware (Intel ARL iGPU via Vulkan,
`GlyphRunner.run_wgsl`), probe `.builder_queue/probe_item8_run_lane_twin_status.py`:

```
0x07 RUN         python=          -1 twin=          -1 (u32=4294967295)  PARITY
0x12 RUN2        python=          -1 twin=           0 (u32=0)  DIVERGENT
```

A caller that spawns a child via RUN2 on the twin and reads 0 concludes
"child exited 0" — the worst possible silent divergence class (false success).
0x07 RUN (7u) is OUTSIDE the bridge and correctly reaches the unknown-syscall
path (-1); 0x10 (16u) has its own IMPLEMENTED branch; 0x11 (17u) is BRIDGED
and the spec names that divergence (its Python arm copies pixel words; the
twin's 0 is a documented no-op, not a status signal any caller checks). 0x12
is the one syscall whose spec claim (-1) was factually wrong — fixed in the
spec this session; the SHADER is still wrong until this ticket lands.

## The fix (bounded, one line)

Exclude 18u from the bridge so it reaches the unknown-syscall path:

```
} else if (syscall_num >= 16u && syscall_num <= 255u && syscall_num != 18u) {
```

result: 0x12 falls through to `Unknown` → 4294967295u (-1), matching Python
and matching the normative twin contract recorded in the spec. Apply to BOTH
copies (tools/ + glyph_dispatch/ — md5-identical twins, keep them identical;
pre-commit cmp as usual).

## Gate (when picked up)

1. RED first: `tests/test_pillar21_abi_spec_rotguard.py::test_l3_run_lane_twin_contract_pinned`
   goes RED the moment the twin source excludes 18u — that failure is the
   signal to flip the spec's 0x12 `twin_contract: GAP` → `twin_contract: NEGATIVE`
   and `twin: BRIDGED` → `twin: UNIMPLEMENTED` in the same commit.
2. Behavioral: extend `.builder_queue/probe_item8_run_lane_twin_status.py`'s
   0x12 row to PARITY (twin now -1). Requires GPU (wgpu) — non-blocking smoke
   lane per the determinism clause; the structural legs (1) gate.
3. Regression: `tests/test_pillar23_parity_ci.py` corpus unchanged-green
   (no corpus case touches 18u today; the bridge change is provably
   non-impacting to the pinned corpus).
4. `docs/SYSCALL_ABI_SPEC.md` 0x12 block re-synced in the same commit
   (status + contract fields + divergence paragraph replaced with the
   normative NEGATIVE contract).

## What this ticket does NOT do

- Does not propose implementing RUN2 spawn semantics on the twin (process
  spawn is foreign to the shader threat model — see the spec's normative
  0x07 contract paragraph). The bounded form is exactly the -1 exclusion.
- Does not touch 0x03/0x04 stubs (sanctioned divergence, DIVERGENCE-SANCTIONED
  contract) or any Python engine code.
