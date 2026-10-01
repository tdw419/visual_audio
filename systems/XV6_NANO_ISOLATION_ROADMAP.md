# xv6-nano isolation roadmap — enforce the K3 spatial box in GlyphCPUv2

Grow xv6-nano from a cooperative unikernel with a *convention* (K3's box is
checked by a Python harness) into a cooperative kernel with a **real
privilege boundary**: GlyphCPUv2 itself enforces each user task's memory
box and traps into the kernel on a violation or a syscall.

Follows `systems/XV6_NANO_ROADMAP.md` (K1–K4 done, `982a55e`). This is the
D1 follow-on ("GlyphCPUv2 `_mem_write` enforcement") bundled with the D2
follow-on ("real `SYSCALL`-op boundary") — they are one feature: you can't
bound *user* memory without a user/supervisor mode, and the way out of user
mode is a syscall or a fault.

Companion memory:
`~/.claude/projects/-home-jericho-projects-zion-projects-visual-audio/memory/xv6-nano-kernel-composition-roadmap.md`

---

## Why this is a new phase, not more K-items

1. **First GlyphCPUv2 engine change in the whole track.** G1–G12 and K1–K4
   were zero engine edits. GlyphCPUv2 has a parity twin
   (`glyph_dispatch/src/glyph/glyph_isa_v2.py`) and a pre-commit gate; a
   change to its `ST`/`SB`/`SYSCALL` path touches all 43 tests.
2. **The verification model changes.** Every test so far is "GPU
   `SpatialRV64ICore` = ground truth, GlyphCPUv2 matches." A
   memory-protection fault has **no RISC-V equivalent** — the GPU core has
   no MMU, it just performs the store. So "did the fault fire correctly"
   cannot be checked against the GPU. See E5.

## Design decisions

| # | Decision | Ruling |
|---|----------|--------|
| E1 | Fault semantics | **Trap to a kernel handler.** On an out-of-box user store: GlyphCPUv2 records `FAULT_ADDR` + `FAULT_PC` (packed), sets `mode=SUPER`, sets `pc=KFAULT_PC`, does **not** perform the store, keeps stepping. Kernel handler marks the proc `FAULTED` and returns to the scheduler; other procs run to completion. |
| E2 | How the kernel programs the box + mode | **Reserved data-memory words**, MMIO-style, written by the kernel from SUPER mode: `BOX_LO`, `BOX_HI` (byte range `[mem_base, mem_limit)`), `KFAULT_PC`, `KSYS_PC` (packed glyph PCs), and `MODE_LATCH`. No new glyph opcodes for the box. Word indices fixed in `glyph_isa_v2.py` and shared with the fixture as `#define`s. |
| E3 | User→kernel voluntary path | **Reuse the `SYSCALL` glyph op.** When `KSYS_PC != 0`, `SYSCALL` saves `SYSCALL_PC`, sets `mode=SUPER`, jumps to `KSYS_PC` (regardless of prior mode). When `KSYS_PC == 0`, the existing built-in WRITE/EXIT/DEBUG handlers still run (backward-compatible). The transpiler gains a tiny `__syscall(n, …)` intrinsic to emit `SYSCALL` from fixture C. |
| E4 | Enforcement scope (first cut) | **Stores only** (`ST`, `SB`-RMW write). User-mode loads outside the box are *not* trapped in E-K1/E-K2 — writes are the integrity/corruption concern and match K3's checker exactly. Read confinement is a noted follow-on. |
| E5 | Verification model | The fault/trap path is **GlyphCPUv2-only**. Its oracle is the contract + **native x86** (which computes the run "as if the faulting proc were stopped at that store") + the **K3 harness store-trace** as an independent cross-check. The in-box (no-fault) path keeps the two-way GPU/Glyph check — enforcement is transparent when nobody violates. |

**Mode-transition timing (E2 detail).** The kernel writes `MODE_LATCH=USER`
from SUPER; the latch takes effect on the **next indirect jump**
(`JMPR`/`CALLR`) — which is exactly `switch_to`'s terminal computed jump
into the task. So `switch_to`'s own context restore (`lw ra..s11` from the
task's context struct, which is *kernel* memory) still runs in SUPER; the
task starts in USER only once control actually reaches it. `SYSCALL` and a
fault both clear the latch and set `mode=SUPER` themselves.

## Build increments

Same discipline: oracle before feature; verify against native first; one
commit per item (engine + parity twin + fixture scenario + test);
`cmp -s tools/glyph_isa_v2.py glyph_dispatch/src/glyph/glyph_isa_v2.py`
byte-identical; gate = `pytest tests/test_rv64i_to_glyph*.py
tests/test_glyph_isa_v2.py tests/test_spatial_rv64i_cpu.py`.

### E-K1 — bounded user store + trap-to-fault-handler  ✅ DONE

GlyphCPUv2: `mode` field; the E2 reserved words; on a user-mode store check
`BOX_LO <= addr < BOX_HI`, else trap per E1. `MODE_LATCH` applied on the
next `JMPR`/`CALLR`.

**As built** (commit pending; gate = 44 tests green,
`test_ek1_bounded_user_store`):

- **Reserved block at byte `0x8000`** (`BOX_MMIO_BASE` in `glyph_isa_v2.py`),
  not `0xF000` — it has to sit inside the GPU oracle's 36864-byte space so
  the no-fault leg's identical MMIO stores land harmlessly, and above the
  kernel stack top `0x4000`. Layout: `MODE_LATCH, KFAULT_PC, KSYS_PC,
  BOX0_LO/HI, BOX1_LO/HI, FAULT_ADDR, FAULT_PC, SYSCALL_PC, BOX2_LO/HI`.
- **Three box ranges, not one.** A task that yields is a non-leaf: its
  `switch_to` prologue spills `ra`/`s0` to its kalloc'd kernel stack. So the
  box is `BOX0` (arena slot) ∪ `BOX1` (own `proc[]` entry, covers the
  context struct saved on yield) ∪ `BOX2` (own stack page) — exactly the
  K3 harness whitelist set. `proc.kstack` field carries the page base.
- **Privilege boundary is a new `KJMP` glyph op**, not plain `JMPR`. The
  transpiler lowers *only* `switch_to`'s data-sourced terminal `ret` to
  `KJMP` (every other computed jump stays `JMPR` and never touches
  privilege). `KJMP` = `JMPR` + `mode=SUPER` + (if `MODE_LATCH` armed)
  `mode=USER`. This is what lets a clean cooperative yield drop USER→SUPER
  without a fault or syscall.
- **`KFAULT_PC` is loader-seeded** (packed pixel PC), like `PTR_TABLE_BASE`
  — the C kernel writes the box ranges + `MODE_LATCH` itself but cannot
  name a pixel coordinate. A `&sym`→pixel-PC path is E-K2/E-K3 work.
- **WGSL twin (`wgsl_glyph_isa_v2.py`) NOT updated** — no `KJMP`, no box
  check on the GPU-side WGSL engine yet. Out of scope for the E-K1 gate;
  it's the SpatialRV64ICore-class port and tracked separately.

`xv6_nano.c` SCENARIO 6: `userinit` writes each proc's `[mem_base,
mem_limit)` and registers `KFAULT_PC`. The scheduler sets `MODE_LATCH=USER`
before `switch_to`-ing a task. Two sub-scenarios — an in-box task
(`box_fill`) runs clean; an out-of-box task (`box_over`) triggers the trap,
the kernel `fault_handler` sets `proc[cur].state = FAULTED`, records
`g_fault_pid`, and `switch_to`s back to the scheduler; the other procs
finish; the image halts.

**Oracle:** `FAULT_ADDR == &g_arena[ARENA_BYTES]` (the OOB store);
`g_fault_pid` == the offender; console from the surviving procs matches
native "as if that proc stopped at the store". In-box sub-scenario stays
two-way GPU/Glyph clean. K3 harness store-trace agrees.

### E-K2 — `SYSCALL` trap + `__syscall` intrinsic  ✅ DONE

GlyphCPUv2: `SYSCALL` traps to `KSYS_PC` per E3, saving `SYSCALL_PC`.
Transpiler: `__syscall(n, a, b)` → `SYSCALL` with `n/a/b` in fixed glyph
regs; parity twin synced.

**As built** (commit pending; gate = 64 tests green,
`test_ek2_syscall_boundary`):

- **Syscall-return mechanism = a `SYSRET` glyph op**, lowered from RV `mret`
  (the decoder already yields `OP_MRET`; `ebreak`→`OP_EBREAK`→`SYSCALL`).
  `__syscall` / `__sysret` are `always_inline` shims: `__syscall` loads
  a7/a0/a1 and emits `ebreak`; `__sysret` emits `mret`.
- **Args cross the C boundary via memory, not glyph regs.** `SYSCALL` (when
  `KSYS_PC != 0`) copies `r17/r10/r11` (a7/a0/a1) into reserved words
  `SYS_N/SYS_A0/SYS_A1` at `BOX_MMIO_BASE+0x30..0x38`; the SUPER-mode C
  `syscall_dispatch` reads those and writes its result back into `SYS_A0`;
  `SYSRET` delivers `SYS_A0` into `r10`.
- **`SYSCALL` snapshots the whole register file; `SYSRET` restores it**
  (then overwrites `r10` with the result). `syscall_dispatch` is a plain C
  function that clobbers caller-saved regs the task expects to survive the
  inlined `ebreak` — a real trap saves the file, so the engine does too.
- `KSYS_PC` loader-seeded (packed pixel PC of `syscall_dispatch`), like
  `KFAULT_PC`. `SYSCALL_PC` is stored as `(row<<16)|col` so `SYSRET`
  recovers it with `col * INSTR_WIDTH` (same packing as `JMPR`).
- **No GPU leg for SCENARIO 7** — SpatialRV64ICore models neither
  `ebreak`-as-syscall nor `mret` nor the box. Per E5 this scenario is
  GlyphCPUv2-vs-contract only.

`xv6_nano.c` SCENARIO 7: `s7_task` writes its arena slot (in-box), then
`__syscall(SYS_write, "hi\n", 3)` — dispatcher writes to `g_console` and
`mret`s back — then a **direct** `g_console[0] = '!'` (kernel memory,
outside its box) **faults** into `fault_handler`. Oracle held: console ==
`b"hi\n"` (nothing from the blocked `!`), `g_fault_pid == 1`,
`g_fault_addr == &g_console`, `proc[0]` FAULTED, engine ends in SUPER.

### E-K3 — box as a 2D tile (stretch / endpoint)

Express `BOX_LO`/`BOX_HI` — or an additional `(row, col, h, w)` — so the
check runs in image coordinates and a task's memory **is** a rectangle on
the pixel grid. This is the "tasks are tiles" payoff and the point where
xv6-nano stops being "xv6 with conventions" and becomes a Geometry-OS-shaped
kernel. Optional; may be where this roadmap ends.

## Done =  ✅ REACHED (E-K1 `13cc7e6`, E-K2 commit pending)

E-K1 + E-K2 green: an out-of-box user store traps into the kernel, which
reaps just that proc while the rest of the system runs; a user task reaches
the kernel only through `SYSCALL`; a user task cannot touch kernel memory.
"xv6-nano enforces spatial memory isolation" is now a checked claim, not a
convention — and it's enforced by the pixel machine itself, not a Python
watcher.

**E-K3 (box as a 2D tile) is the optional stretch endpoint — not started,
not required for "done". Open the go/no-go separately.**

## Non-goals / follow-ons

- User-mode **read** confinement (E4 is stores-only).
- Per-proc boxes as first-class GPU-side state on `SpatialRV64ICore` — it
  stays the flat-memory oracle; the enforced behavior is GlyphCPUv2's.
- Nested/recursive fault handling, signals, `fork`.
- Connecting a faulted-proc report to a Geometry OS terminal tile.
