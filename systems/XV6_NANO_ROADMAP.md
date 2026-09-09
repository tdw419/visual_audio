# xv6-nano kernel composition roadmap

Compose the verified RV32I→Glyph primitives (`tools/GLYPH_TRANSPILER_ROADMAP.md`,
G1–G12) into one coherent **cooperative kernel image** that boots, runs
multiple long-lived tasks, reaps them, and drives a tiny shell — running
**bit-identically on native x86, GPU `SpatialRV64ICore`, and `GlyphCPUv2`**.

This is the "human gate" the transpiler roadmap deferred: it is a design
project first (decisions that can't be tested into existence), then four
build increments that each still ship a three-way differential oracle.

Companion memory:
`~/.claude/projects/-home-jericho-projects-zion-projects-visual-audio/memory/rv64i-to-glyph-transpiler-verified.md`

---

## What xv6-nano is / is not

**Is:** xv6's cooperative skeleton — a `proc[]` table, a `scheduler()` loop
that resumes runnable procs via `swtch`-style `switch_to`, a `kalloc`
freelist, a console — with every hardware-dependent part replaced by a
convention. Real xv6 naming and structure are kept wherever they survive the
ISA cut, because real xv6 source has been this project's bug-finding engine.

**Is not** (settled non-goals, inherited from the transpiler roadmap):
- No MMU / Sv39 / page tables. No privilege levels, `mret`/`sret`. No
  traps, CSRs, timer interrupt. Scheduling is therefore **cooperative
  only** — tasks yield explicitly.
- Not a fork/exec/pipe shell. Not a filesystem (kalloc freelist only).
- Not `SpatialRV64ICore` changes (its QEMU lockstep boot validation is
  load-bearing). GlyphCPUv2 changes are allowed but avoided where a
  harness-side check suffices.

## Design decisions (ruled — rationale below)

| # | Decision | Ruling |
|---|----------|--------|
| D1 | Memory isolation | **Flat & trusted for K1–K2.** K3 *specifies* the spatial-box contract and adds a **harness-side** box checker + fixtures; GlyphCPUv2 enforcement is a documented follow-on. |
| D2 | Kernel-service ABI | **Plain C calls** (`sys_yield` / `sys_write` / `sys_exit` / `kalloc`). A real `SYSCALL`-op boundary is a documented future upgrade. |
| D3 | Process model | **Long-lived procs + run queue + exit/reap.** Cooperative round-robin (already proven in G3). |
| D4 | Shell scope | **Minimal REPL** over canned input: a 2–3 entry command table (`help`, `ps`, `echo`) dispatched through the proc-table `jalr` primitive. No stdin, fork, exec, pipes. |
| D5 | Fixture shape | **One kernel translation unit** `tests/fixtures/xv6_nano.c`, scenario-selected at compile time (`-DSCENARIO=N`). Keeps the composition coherent — K1's scenario must still pass after K4 lands. |

**D1 rationale.** Cooperative scheduling + no shared mutable kernel state
reachable except through the service calls means flat/trusted is already
*correctness*-safe. The 2D spatial box (task = tile = rectangular memory
region, `addr→(x,y)` per-task, faulting `_mem_write`) is the interesting
Geometry OS concept, but it is the only option that touches a GPU engine and
would push K1 back for a property the composition doesn't need to prove. K3
therefore delivers the *contract* precisely and a Python box checker that
watches a task's writes during the differential run — a real
box-violation oracle without an engine change. GlyphCPUv2 enforcement
follows once the contract has earned it.

**D2 rationale.** There is no privilege boundary to cross, so a "syscall"
is just a function call. This keeps the three-way discipline with zero
engine work. `sys_exit` still reaches a clean stop: it marks the proc
`ZOMBIE` and returns to `scheduler()`, which falls through to the image's
terminal `ecall` (→ `HALT`) once the run queue drains.

## Build increments

Same discipline as the transpiler roadmap: **oracle before feature**, verify
expected values against native x86 **first**, one commit per K item
(fixture scenario + kernel code + test), receipts are pasted pytest summary
lines, parity copies stay byte-identical.

Gate: `pytest tests/test_rv64i_to_glyph*.py tests/test_glyph_isa_v2.py
tests/test_spatial_rv64i_cpu.py` green + `cmp` parity.

### K1 — unified bootable image ✅ DONE (`7233b03`)

`_start` → `sp`/`gp` → `kmain` → `kinit()` freelist (G7) → `userinit()`
builds `proc[]` (G4) + kalloc's a stack per proc → `scheduler()` walks
`proc[]` with a running pointer (no runtime multiply) and round-robins 3
tasks via `switch_to` (G1/G3). Each task writes its marker to the shared
console (G12) per work unit and `sys_yield()`s; after `WORK_UNITS` it sets
`state=DONE` and the scheduler drops it; image halts via terminal `ecall`.

`tests/fixtures/xv6_nano.c` (`SCENARIO 1`), `test_rv64i_to_glyph_xv6_nano.py`.
**Two-way** (GPU `SpatialRV64ICore` = ground truth, `GlyphCPUv2` matches
bit-for-bit) — `switch_to` is RISC-V asm so there is no native-x86 leg,
same as `switch_round_robin`. Result: console `"ABCABCABC"`, 12 switches,
iters `[3,3,3]`. No transpiler change; codegen all already-lowered ops.

### K2 — service layer + exit/reap ✅ DONE (`dddf5dd`)

`SCENARIO 2`: `sys_yield` / `sys_write` / `sys_exit(code)` as C calls (D2).
`proc[1]` runs 2 units then `sys_exit(0x42)`; `scheduler()` sees
`state==ZOMBIE`, records `xcode` into `g_xcode[i]`, sets `g_reaped_mask`
bit `i`, drops it; `proc[0]`/`proc[2]` finish; image halts when no proc is
RUNNABLE. `struct proc` padded to 128 B; scheduler carries an index
alongside the running pointer (no multiply).

**Convention discovered:** `sys_yield`/`sys_exit` MUST be `always_inline` —
they wrap `switch_to`, whose data-sourced terminal `ret` jumps to the
scheduler rather than returning, so a non-inlined wrapper leaks a glyph
call-stack frame per yield (G3 Bug D territory; `switch_to`'s `POP r28`
balances only its own frame). Fixture-level fix, no transpiler change.

**Oracle** (GPU ground truth, GlyphCPUv2 matches): console `"ABCABCAC"`,
11 switches, iters `[3,2,3]`, `g_xcode [0,0x42,0]`, `g_reaped_mask 0b010`.

### K3 — spatial memory contract + box checker ✅ DONE (`29a8e40`)

**The spatial memory contract (D1).** There is no MMU, so this is a
*convention* checked at the harness, not hardware-enforced:

- A shared byte arena `g_arena[NPROC * ARENA_SLOT]` is carved into one
  fixed slot per proc. Proc `i`'s **box** is the half-open byte range
  `[g_arena + i*ARENA_SLOT, g_arena + (i+1)*ARENA_SLOT)`.
- **A task may only store into its own box.** Kernel code (scheduler,
  `switch_to`, `kalloc`, `userinit`, `sys_write`, `cons_putc`, …) is
  unconstrained — it owns `proc[]`, `ctx_sched`, the freelist, the console.
- 2D reading: `GlyphCPUv2` data memory (`self.memory`, word-indexed) viewed
  as a `W`-word-wide grid makes each box a contiguous `rows×cols` tile
  (`word = addr>>2`, `x = word % W`, `y = word // W`). The checker enforces
  the linear range; the tile is the same set of cells.
- **Enforcement is future work** (GlyphCPUv2 `_mem_write` faulting on a
  per-proc box — roadmap follow-on). K3 proves the contract is *observable*.

**The harness box checker.** `GlyphCPUv2.memory` is wrapped so every
`self.memory[word] = …` (every `ST`/`SB` RMW) is logged with the RV PC at
that moment (pixel PC → instruction index → the emitted `:pc_XXXXXXXX`
label). A store is a **task store** iff its PC lies in a task function's
address range (`box_fill` / `box_over`), from `nm`. No
GlyphCPUv2 change.

**Scenarios.** `SCENARIO 3` — all three procs run `box_fill(id)`,
each filling its own slot; the checker sees every task store land inside
the union of boxes. `SCENARIO 4` — `proc[2]` runs `box_over(2)`,
which fills its slot then writes **one word past the arena end**; the
checker's out-of-box set is exactly `{g_arena + NPROC*ARENA_SLOT}`.

**Oracle:** GPU `SpatialRV64ICore` and `GlyphCPUv2` agree on the in-box run
(console + a per-slot checksum); the box checker's flagged set matches the
expected OOB address exactly (empty for `SCENARIO 3`).

### K4 — nano-shell ✅ DONE (`982a55e`)

`SCENARIO 5`: `proc[0]` runs `shell_body` over canned input
`"help\necho hi there\nps\n"`. First-word tokenizer, `cmd_table[]` of
`{name, fn}` dispatched through a function pointer (G5 `jalr` primitive;
`_run_glyph` seeds `PTR_TABLE_BASE`). `help` → name list, `ps` → `proc[]`
state chars, `echo` → rest of line.

**Oracle** (GPU ground truth, GlyphCPUv2 matches): console
`"help ps echo\nhi there\nR--\n"` (26 bytes).

The K4 code briefly needed a `#if SCENARIO == 5` guard — compiled into
every scenario its globals pushed the kernel's writable segment past the
old `PTR_TABLE_BASE` (0xC00), which `switch_to`'s data-sourced `ret` reads
on every yield → hang. **Follow-up (`1137780`): `PTR_TABLE_BASE` raised
0xC00 → 0x2000** (above the linker's page-aligned `.data`+`.bss`, still
below every fixture's `sp`), so the guard is gone and the whole kernel —
scheduler, kalloc, all tasks, the shell — compiles into one image for
every scenario (D5). Same commit fixed the substring-label mangling in
`assemble_glyph_to_pixels` (now a token-boundary regex).

## Done ✅ (2026-09-05)

K1–K4 all green two-way (GPU `SpatialRV64ICore` = ground truth, `GlyphCPUv2`
bit-identical — no native leg because `switch_to` is asm). `xv6_nano.c` is
one coherent kernel, scenario-selected. The spatial memory contract is
written down with a working harness-side violation oracle. **"A cooperative
multitasking kernel, composed from independently verified primitives, runs
identically on pixels and on a GPU emulator" is now a checked claim** — the
bridge from "we can transpile C" to "we can run a system."

43 passed. K1–K4 needed no transpiler change; the follow-up `1137780`
(`PTR_TABLE_BASE` raise + token-boundary label resolution) is the only
transpiler work, and it's a hardening pass, not a fix for a K-item.
Fixture conventions surfaced: `sys_yield`/`sys_exit` must be `always_inline`
(K2); a switch/jump-table scenario needs the `build_pointer_table()` seed
(K4). The substring-label footgun is now removed at the source.

## Explicit follow-ons (not in K1–K4)

- ~~Raise `PTR_TABLE_BASE`~~ **DONE (`1137780`)** — 0xC00 → 0x2000; the
  substring-label mangling in `assemble_glyph_to_pixels` was fixed in the
  same commit. K4's guard is gone.
- GlyphCPUv2 `_mem_write` enforcement of the spatial box (D1 upgrade).
- A real `SYSCALL`-op privilege boundary (D2 upgrade) — needs a transpiler
  emission convention and a matching `SpatialRV64ICore` handler.
- The G10 `slli;srai` XLEN hazard (transpiler roadmap) — orthogonal.
- Connecting the shell's console to a real Geometry OS terminal tile.
