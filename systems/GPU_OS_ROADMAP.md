# GPU OS roadmap — a basic isolated cooperative kernel running on the GPU

Grow xv6-nano (a cooperative kernel *designed for* the spatial substrate,
K1–K5 done, isolation enforced in GlyphCPUv2 by E-K1/E-K2) into **a basic
working GPU OS**: isolated tasks + an interactive shell + framebuffer
output, executing on an actual GPU engine, not just the Python reference.

Follows `systems/XV6_NANO_ROADMAP.md` and
`systems/XV6_NANO_ISOLATION_ROADMAP.md`. Companion memory:
`~/.claude/.../memory/xv6-nano-isolation-roadmap.md`.

Same discipline as the prior roadmaps: **one falsifiable test + one commit
per increment**; GlyphCPUv2 (Python) stays the bit-exact reference; the GPU
engine must match it; parity twins byte-identical; human gate between
increments (the loop stops, surfaces the next fork, waits).

---

## What "basic working GPU OS" means here

**In scope:** the xv6-nano-class cooperative kernel, running on a GPU
engine, with (a) engine-enforced per-task spatial isolation, (b) a real
interactive shell reading host-fed input, (c) framebuffer output to a
designated rectangle of image memory, (d) 2–3 isolated tasks scheduled
cooperatively, one of them the shell.

**Explicitly NOT in scope:** real Linux, real device drivers, preemption,
an MMU / demand paging, virtual memory, networking, multi-core, filesystem
persistence. Those are the V1–V5 long game, not this roadmap.

**Done =** one end-to-end scenario, green on the chosen GPU engine and
bit-identical to GlyphCPUv2: isolated tasks + shell + a framebuffer draw,
an out-of-box store from a task traps and is reaped, the rest runs on.

---

## Substrate reality (why GO-0 is a real fork)

Three engines exist; isolation currently lives in only one of them:

| engine | file | maturity | isolation? |
|---|---|---|---|
| **GlyphCPUv2** | `glyph_isa_v2.py` (Python + twin) | mature; runs full xv6-nano; **has E-K1/E-K2** (mode, 3-range box, `KJMP`, `SYSCALL`/`SYSRET` trap) | ✅ yes — but it's the Python reference, not "on GPU" |
| **SpatialRV64ICore** | WGSL RV64 engine | mature; boots Alpine to a shell on real GPU; xv6-nano K1–K5 ground-truth | ❌ no — deliberately the flat-memory oracle (isolation roadmap non-goal E) |
| **WGSL glyph engine** | `wgsl_glyph_isa_v2.py` (+ drifted twin) | toy: 8-wide, ~300 lines, opcode set stops at `SYSCALL`, no `JMPR`/`CALLR`, no pointer table, tiny memory | ❌ no — and can't run xv6-nano at all yet |

There is a working WGSL execution + differential harness
(`tools/verify_wgsl_glyph_isa_v2.py`, uses `wgpu`, runs on the real GPU,
diffs against GlyphCPUv2) — but only for the toy glyph engine's opcode set.

---

## GO-0 — DECISION: which GPU engine is the OS target?  ✅ RULED: Option A

**Ruled 2026-09-05: Option A** — add a minimal spatial-isolation layer to
**SpatialRV64ICore**. This deliberately **reverses isolation-roadmap
non-goal E**: SpatialRV64ICore stops being a pure flat-memory oracle and
gains a `mode` bit + box check + trap + `ebreak`/`mret` syscall path. The
E-K1/E-K2 *design* is ported (not the glyph ops — those stay GlyphCPUv2's).
GlyphCPUv2 remains the bit-exact reference the GPU engine is diffed against.
Increments GO-1…GO-5 below are active; the Option B/C sketches are dead.

- **Option A — teach SpatialRV64ICore a minimal spatial-isolation layer.**
  Port just the box check + trap-to-handler + `mret`/`ebreak` syscall path
  (the *design* from E-K1/E-K2, not the glyph ops) into the mature WGSL
  RV64 engine. xv6-nano's SCENARIO 6/7/… then run on the actual GPU RV64
  core. **Cost:** ~1 engine increment; **reverses isolation-roadmap
  non-goal E** (SpatialRV64ICore stops being a pure flat oracle) — that's
  the thing needing your sign-off. **Payoff:** shortest path to "OS on
  GPU"; reuses the Alpine-grade engine.

- **Option B — grow the WGSL glyph engine to run xv6-nano, then add
  isolation.** Bring `wgsl_glyph_isa_v2.py` up to 64-wide, `JMPR`/`CALLR`/
  `KJMP`, the pointer table, 16384-word memory, then port the box. **Cost:**
  3–4 engine increments before the first OS scenario; large. **Payoff:**
  keeps SpatialRV64ICore pure; isolation runs in a genuinely *glyph* GPU
  engine (spatial-native, the long-term substrate).

- **Option C — GlyphCPUv2 stays the only isolation engine; "GPU" means the
  shell + framebuffer scenario runs on SpatialRV64ICore WITHOUT the box,
  and the box is checked two-way GlyphCPUv2 vs a Python trace.** Weakest
  claim ("GPU OS" minus GPU-side enforcement) but zero engine risk.

**Recommendation: A.** The project vision is "Linux executing on GPU," and
the credible near-term "GPU OS" is the mature RV64 GPU engine gaining the
one capability it lacks. B is a research roadmap in its own right; C
undersells the claim. The non-goal-E reversal is deliberate and worth it —
note it in that roadmap when you rule.

---

## Increments (assuming GO-0 = A)

### GO-1 — spatial box + trap on SpatialRV64ICore  ✅ DONE

**As built** (this commit; gate = 66 passed,
`test_go1_isolation_on_gpu[6]` + `[7]`):

- **All isolation state lives in guest RAM** — a reserved MMIO-style word
  block whose byte layout matches `BOX_MMIO_BASE` in `tools/glyph_isa_v2.py`
  (`0x8000` MODE_LATCH … `0x8038` SYS_A1), plus GPU-only words above
  GlyphCPUv2's block: `0x8040/0x8044` = `switch_to`'s RV byte range,
  `0x8048` = "syscall trap outstanding", `0x8050…0x8150` = a 32×(lo,hi) GPR
  snapshot. **No `CPUState` struct field added** → the Python host
  serializer/`get_state()` are untouched, and every non-xv6 image is
  unaffected. `SpatialRV64ICore(36864)` is unchanged (0x8150 < 36864 —
  verified, no bump).
- **Privilege = the engine's existing `state.mode`.** GlyphCPUv2 `MODE_SUPER`
  ≡ RV **M-mode (3)** here, `MODE_USER` ≡ RV **U-mode (0)**. `iso_eligible()`
  gates the whole layer on `arrayLength(&memory) < 0x10000u` (mirrors
  GlyphCPUv2's "small data memory = the box harness" gate); `iso_active()`
  additionally requires a nonzero `KFAULT_PC`/`KSYS_PC` — so Alpine and the
  unit fixtures never see a box check (confirmed: 1 MiB core still compiles
  + runs, `ebreak` still `raise_trap(3,…)`).
- **KFAULT_PC / KSYS_PC / switch_to range are real RV byte addresses**
  (this engine runs a flat binary — no pixel PCs), seeded by the test
  harness from ELF symbols after `load_program`. `switch_to` has no `.size`
  directive → its range is derived from the disassembly.
- **Store box check added to BOTH paths:** the plain interpreter
  (`opcode == 0x23u`) and `execute_decoded` store cases 22–25, via one
  `iso_check_store(addr, pc, &next_pc)` helper. A user-mode store outside
  BOX0∪BOX1∪BOX2 records `FAULT_ADDR`, does not land, sets `mode = 3`, and
  vectors `pc = KFAULT_PC`. Stores already end a decoded basic block.
- **Trap/return path: bespoke `ebreak`/`mret` handlers, NOT `do_mret`.** The
  recon's "reuse `mepc`/`do_mret`" idea was rejected — the C
  `syscall_dispatch` clobbers caller-saved regs the task expects to survive
  the inlined `ebreak` (a real `mret` does not restore GPRs), so the engine
  must snapshot/restore the register file exactly as GlyphCPUv2 does.
  `ebreak` with `KSYS_PC != 0` → `iso_syscall_trap`: snapshot 32 GPRs to the
  RAM scratch block, marshal a7/a0/a1 → `SYS_N/A0/A1`, save resume PC →
  `SYSCALL_PC`, `mode = 3`, `pc = KSYS_PC`. `mret` while a trap is
  outstanding → `iso_sysret`: restore the GPRs, deliver `SYS_A0` → a0,
  `mode = 0`, `pc = SYSCALL_PC`. Both paths (interpreter SYSTEM branch +
  decoded cases 75/76) call the same helpers; a non-syscall `mret` still
  falls through to `do_mret()`.
- **The USER latch = `switch_to`'s terminal `ret`, identified by PC range**
  (GlyphCPUv2 uses a dedicated `KJMP` op the transpiler emits only there;
  this engine has no transpiler, so `iso_on_ret(rd, pc)` fires on a `ret`
  (`rd == x0`) whose address is inside the seeded `switch_to` range).
  Semantics match `KJMP` exactly: unconditionally `mode = 3`, then re-enter
  `mode = 0` and clear the latch if the scheduler armed `MODE_LATCH`. Every
  other computed `ret` (e.g. a resumed task returning out of `sys_yield`)
  keeps normal semantics.
- **The fixture `tests/fixtures/xv6_nano.c` needed no change** — its
  `#if SCENARIO==6||7` code already programs the MMIO block and works on
  both engines. `tools/glyph_isa_v2.py` / `tools/rv64i_to_glyph.py` and
  their twins are untouched.
- **Verification:** SCENARIO 6 (an out-of-box user store traps, offender
  reaped, survivors finish) and SCENARIO 7 (`__syscall` write succeeds, a
  direct kernel-memory write faults) run on `SpatialRV64ICore` and are
  asserted **bit-identical to GlyphCPUv2** (`_run_glyph`) on `g_fault_pid`,
  `g_fault_addr`, `proc[]` states, `g_console`, `g_clen`. Per roadmap E5
  GlyphCPUv2 stays the oracle; GO-1 makes the GPU engine match it.
- **GO-2 implication:** the box is three flat `[lo,hi)` byte ranges read
  from RAM (`iso_addr_in_box`). GO-2's `(row,col,h,w)` tile form just adds
  an alternative predicate inside that one helper on both engines; the
  trap/latch/syscall machinery is done and reusable.

Port to the WGSL RV64 engine: a `mode` bit, the reserved MMIO word block
(same byte layout as `BOX_MMIO_BASE` in `glyph_isa_v2.py`), the 3-range
box check on stores in user mode, trap-to-`KFAULT_PC`, and `ebreak`/`mret`
→ syscall dispatch / return with a register-file save.
**Test:** run `xv6_nano.c` SCENARIO 6 + 7 on SpatialRV64ICore and assert
bit-identical to GlyphCPUv2 (`g_fault_pid`, `g_fault_addr`, `proc` states,
`g_console`, `g_clen`). **Gate.**

**Recon (2026-09-05, done in the loop-setup session — start here):**
- Engine = `tools/SPATIAL_RV64I.wgsl` (**3252 lines**), driven by
  `tools/spatial_rv64i_cpu.py` (`SpatialRV64ICore`). Real Sv39 MMU, S/M
  mode, CSRs, `raise_trap(cause, tval, epc)` (~L789), `do_mret()` (~L856)
  **already exist** — the box trap can likely reuse `raise_trap` +
  a fresh cause code rather than inventing a vector mechanism.
- **Two execution paths, both must get the store check:** the plain
  interpreter (store at `opcode == 0x23u`, ~L1888) **and** the decoded
  basic-block fast path (`execute_decoded`, store case ~L2513; SYSTEM
  ~L2791, EBREAK case 75 ~L2822, MRET case 76 ~L2825). Stores already end a
  basic block (~L3128), which helps.
- `ebreak` currently `raise_trap(3,…)`; `ecall` is SBI-serviced inline. The
  E-K2 design wants `ebreak`→dispatch-at-`KSYS_PC`, `mret`→return. Decide:
  reuse M-mode `mepc`/`mstatus.MPP` + `do_mret()` (RISC-V-faithful, the
  engine already has it) **instead of** GlyphCPUv2's `SYSCALL_PC` word +
  bespoke `SYSRET`. If `do_mret` + a trap vector CSR can carry it, GO-1 is
  much smaller — the reg-file save is then just not-clobbering (the C
  dispatcher runs in the same reg context; a real `mret` doesn't
  auto-restore, so the dispatcher must be leaf-ish or the harness/E-K2
  scenario adapted).
- MMIO block byte base `0x8000` fits (`SpatialRV64ICore` default memory is
  1 MiB; `_run_gpu` in the xv6-nano test uses 36864 B — **GO-1's test may
  need a bigger core or a lower MMIO base**; check `_run_gpu`).
- Needs a working `wgpu` device (this env has one — the existing
  `_run_gpu` leg proves it). No naga-only shortcut; must actually execute.
- **This is a large dual-path shader change — do it in a fresh session.**

### GO-2 — box as a 2D tile (folds in isolation-roadmap E-K3)  ✅ DONE

**As built** (gate = 67 passed, `test_go2_tile_box_on_gpu[8]`). The six
GO-2 files (`SPATIAL_RV64I.wgsl`, `glyph_isa_v2.py` + twin, `xv6_nano.c`,
`test_rv64i_to_glyph_xv6_nano.py`, this file) were swept into commit
`5aa83f8` by a concurrent `glyph_gpt` session's `git add -A` while the
GO-2 pre-commit hook was running (the hook had already passed all three
regression legs; the standalone commit then lost the HEAD-ref race). The
GO-2 changeset is intact and green at that commit; history was not
rewritten because other sessions were writing the branch concurrently.

- **`W_MEM = 32`** (32-bit words per grid row = 128 bytes/row) is a fixed
  constant defined once in `tools/glyph_isa_v2.py`, mirrored as `const
  W_MEM: u32 = 32u` in `tools/SPATIAL_RV64I.wgsl`, and `#define W_MEM 32`
  in `tests/fixtures/xv6_nano.c`. **Grid mapping:** a byte address `a` →
  word `w = a >> 2` → `(row, col) = (w // W_MEM, w % W_MEM)`.
- **Four new reserved MMIO words** `TILE_ROW/COL/H/W` at
  `BOX_MMIO_BASE + 0x160..0x16C` (`0x8160..0x816C`). Chosen **above** the
  GPU engine's GPR-snapshot block (which ends at `0x8150`) so the two
  engines never collide; `0x816C >> 2 = 8283 < 16384` (Glyph harness) and
  `< 36864` (`SpatialRV64ICore` GO test core), so both fit with no core
  bump. Python `_ISO_TOP_WORD` moved to `TILE_W_ADDR >> 2`.
- **The predicate** is one addition inside the *existing* `_addr_in_box`
  (Python) / `iso_addr_in_box` (WGSL) helper, after the 3 range checks: if
  `TILE_H != 0`, map the byte addr to `(row, col)` and return true iff
  `TILE_ROW <= row < TILE_ROW+TILE_H && TILE_COL <= col < TILE_COL+TILE_W`.
  An unset tile (`TILE_H == 0`) is inert — SCENARIO 6/7 and every non-xv6
  image are byte-for-byte unaffected. All of GO-1's trap / latch / syscall
  machinery is reused unchanged.
- **SCENARIO 8**: `#if SCENARIO == 6 || 7` guards widened to include `8`
  for the shared MMIO `#define`s + `fault_handler` + `kstack` init. A
  128-byte-aligned `unsigned g_grid[W_MEM * 16]`; the scheduler arms
  `TILE_ROW = (&g_grid >> 2) / W_MEM + 4, TILE_COL = 8, TILE_H = 4,
  TILE_W = 8` (plus `BOX1`/`BOX2` for the proc entry + stack a yielding
  task needs) **instead of** `BOX0`. `g_grid`'s W_MEM-word alignment puts
  its base at grid col 0 of some row, so the armed tile is that row + 4.
  `s8_tile` does strided in-tile writes (`g_grid[(4+r)*W_MEM+(8+c)] =
  0x41`, all in-bounds, no trap), then `g_grid[(4+4)*W_MEM+8] = 0x7F` —
  the first cell of the row just below the tile — which **traps** into
  `fault_handler` (proc[0] `FAULTED`, `g_fault_pid = 1`,
  `g_fault_addr = &g_grid[8*W_MEM+8]`). proc[1]/proc[2] `UNUSED`.
- **Verification:** SCENARIO 8 runs on **both** GlyphCPUv2 (`_run_glyph`,
  the bit-exact reference) and `SpatialRV64ICore` (`_run_gpu_iso`, no
  `ksys`) and is asserted **bit-identical** on `g_fault_pid`,
  `g_fault_addr`, `proc[]` states, `g_console`, `g_clen`, **and** on the
  `g_grid` tile contents (all `H*W = 32` in-tile cells `== 0x41`, the OOB
  cell stayed `0`).
- **Gate:** `pytest tests/test_rv64i_to_glyph.py
  tests/test_rv64i_to_glyph_*.py tests/test_glyph_isa_v2.py
  tests/test_spatial_rv64i_cpu.py tests/test_spatial_rv32i_cpu.py` = **67
  passed**. `regression_gate.py` legs **bbird** (quick, shell 6.2s),
  **lockstep** (fast path clean), **sha256** each **PASS** on the modified
  shader. `glyph_isa_v2.py` twin byte-identical; `rv64i_to_glyph.py`
  untouched (no transpiler change — the tile is pure engine + MMIO).
- **GO-3 implication:** none blocking. The tile predicate is additive and
  the trap machinery is shared; GO-3's `SYS_read` MMIO input-ring is
  independent of it.

**Test:** `xv6_nano.c` SCENARIO 8 — a task confined to a tile; an
out-of-tile store traps; in-tile path two-way GPU/Glyph clean. **Gate.**

### GO-3 — real interactive shell input  ✅ DONE

**As built** (gate = 68 passed, `test_go3_shell_input_on_gpu[9]`; twins
byte-identical; regression legs bbird/lockstep/sha256 all PASS on the
modified tree). **Fixture + test only — zero engine change.** The syscall
dispatcher runs C at `KSYS_PC` in SUPER mode and reads/writes guest RAM
freely, so `SYS_read` is just another `case` in `syscall_dispatch`; GO-1's
`ebreak`/`mret` trap path and GO-2's box predicate are reused untouched, on
both `GlyphCPUv2` and `SpatialRV64ICore`.

- **`SYS_read` = syscall #2.** `__syscall(SYS_read, buf, cap)` → the SUPER
  dispatcher copies up to `cap-1` bytes from the MMIO input ring into `buf`,
  NUL-terminates, advances the ring cursor, returns the byte count (0 = the
  cursor already sits at `INPUT_LEN`, i.e. input exhausted). `SYS_write`
  (#1) is unchanged.
- **MMIO input ring** — four `const`s added to `tools/glyph_isa_v2.py` + twin
  only (the WGSL engine needs no knowledge of them — the dispatcher's ring
  loads and buffer stores run in SUPER and are never box-checked):
  `INPUT_LEN_ADDR = BOX_MMIO_BASE + 0x170` (0x8170, total bytes loaded),
  `INPUT_CURSOR_ADDR = BOX_MMIO_BASE + 0x174` (0x8174, bytes consumed; the
  dispatcher advances it), `INPUT_DATA_ADDR = BOX_MMIO_BASE + 0x180` (0x8180,
  the byte stream), `INPUT_DATA_CAP = 64` (stream ends 0x81C0 = word 8304,
  inside both the 16384-word Glyph memory and the 36864-byte GPU test core;
  no core bump). Sits above GO-2's tile words (end 0x816C) and the GPU
  engine's GPR snapshot (end 0x8150). `#define`d as `ISO_INPUT_*` in the
  fixture's `#if SCENARIO == 9` block. The **test harness** writes
  `INPUT_LEN` + the packed bytes at `INPUT_DATA` before the run (same way it
  seeds `KFAULT_PC`), via a new `input_bytes=` arg threaded through
  `_run_glyph` and `_run_gpu_iso`.
- **Fixture SCENARIO 9**: the `#if SCENARIO == 6 || 7 || 8` guards widened to
  include `9` (shared MMIO block + `fault_handler` + `kstack` init +
  scheduler `BOX1/BOX2/MODE_LATCH` arming — no `BOX0`, no tile: the shell's
  buffers live on its kstack page = BOX2, its `state=DONE` write hits its
  proc entry = BOX1). The `#if SCENARIO == 7` `__syscall`/`__sysret`/
  `syscall_dispatch` region became `#if SCENARIO == 7 || 9` with a nested
  `#if SCENARIO == 9` adding the `SYS_read` case. `s9_shell(id)`: loop
  `n = __syscall(SYS_read, g_s9_input, sizeof g_s9_input)`; `n == 0` →
  break; then K4's exact first-word tokenizer over the NUL-terminated
  `g_s9_input` (a `static char[64]` global, **not** the 128-byte kstack — so
  the SUPER dispatcher's fill never crowds the shell's frame), dispatching
  `cmd9_table[i].fn(rest)` through the G5 `jalr` fn-pointer (`_run_glyph`
  seeds `build_pointer_table`; the GPU engine needs no seeding). The
  `cmd9_help/ps/echo` handlers can't touch `g_console` directly (E-K2), so
  each routes output through `__syscall(SYS_write, msg, len)`. `userinit`
  `#elif SCENARIO == 9`: `proc[0].context.ra = &s9e` (`j s9_shell`
  trampoline), `proc[1]/[2] = UNUSED`.
- **Transpiler-collision fix (test harness, not engine):** `rv64i_to_glyph`
  maps RV `xN` → glyph `rN` 1:1, but glyph `r27..r31` are the transpiler's
  scratch + hardware call-stack pointer. Small scenarios never make GCC
  reach for `x27..x31`; GO-3's `SYS_read` branch has enough register
  pressure that `-O1` put `dst` in `x28` = glyph's call-stack pointer →
  silent guest-RAM corruption + runaway. `_build` now passes
  `-ffixed-x27..x31` **for SCENARIO 9 only**, keeping codegen inside the
  glyph-safe register file. (A latent transpiler constraint worth hardening
  engine-side later; out of scope for GO-3.)
- **Scripted input** `b"echo hi\nhelp\nps\n"` → console
  `b"hi\nhelp ps echo\nR--\n"` (`echo hi` → `hi\n`; `help` → `help ps echo\n`;
  `ps` → proc[0] RUNNING + proc[1]/[2] UNUSED → `R--\n`). Asserted
  **bit-identical** `g_console`/`g_clen` between `GlyphCPUv2` (`_run_glyph`
  with `ksys_rv_addr`) and `SpatialRV64ICore` (`_run_gpu_iso` also seeding
  `INPUT_LEN` + the bytes), and equal to that expected transcript.
- **GO-4 implication:** none blocking. `SYS_draw`/blit is the same pattern —
  another SUPER-mode `case` in `syscall_dispatch` writing a designated
  rectangle of image memory; no engine change anticipated. If GO-4's draw
  target is kernel/image memory the shell reaches only via syscall (as here),
  the E-K2 routing already covers it. Watch the same `x27..x31` register-
  pressure footgun if the draw dispatcher branch grows.

**Test:** `xv6_nano.c` SCENARIO 9 — the harness feeds a scripted command
sequence; the shell reads it via `SYS_read`, runs commands, console output
bit-identical on both engines. **Gate.**

### GO-4 — framebuffer output  ✅ DONE

**As built** (gate = 69 passed, `test_go4_framebuffer_on_gpu[10]`; twins
byte-identical — `glyph_isa_v2.py` untouched, no new MMIO word;
regression legs bbird/lockstep/sha256 all PASS). **Fixture + test only —
zero engine change**, exactly like GO-3: `SYS_draw` is another `case` in
the SUPER-mode C `syscall_dispatch`, which already has full guest-RAM
access; GO-1's `ebreak`/`mret` trap path and GO-2's box predicate are
reused untouched on both `GlyphCPUv2` and `SpatialRV64ICore`.

- **The "screen" = a `W_MEM`-aligned fixture global**
  `unsigned g_fb[W_MEM * FB_H] __attribute__((aligned(128)))` with
  `FB_W = 8`, `FB_H = 6`. FB row `y` is grid row `base+y`, using the first
  `FB_W` words of each `W_MEM`-wide grid row — a genuine rectangle on the
  GO-2 pixel grid (`768` bytes, well inside both the 16384-word Glyph
  memory and the 36864-byte GPU test core). **No `FB_BASE_ADDR` MMIO word
  was added** — the dispatcher names `g_fb` directly as a C global and the
  harness reads it back by ELF symbol; nothing in GO-4 earned a generic
  "where is the screen" pointer. GO-5 may add one if compose needs it.
- **`SYS_draw` = syscall #3.** `__syscall(SYS_draw, idx, val)` where
  `idx = y*FB_W + x` is a **linear cell index** (a1 carries `val`). The
  SUPER dispatcher recovers `x = idx % FB_W`, `y = idx / FB_W` (`FB_W = 8`
  is a power of two → GCC lowers to `& 7` / `>> 3`, no `div`/`rem` — which
  the build's `_FORBIDDEN` set rejects), writes `g_fb[y*W_MEM + x] = val`
  and returns 0 iff `x < FB_W && y < FB_H`, else returns `(uint)-1`.
  **A packed `(y<<16)|x` arg was tried first and diverged on the RV64 GPU
  core** — only FB row 0 (where the packed value stays small) got written;
  rows `y ≥ 1` (arg `≥ 0x10000`) silently dropped. The small linear index
  is bit-identical on both engines. `SYS_write`/`SYS_read` unchanged.
- **`cmd9_plot`** (the `plot` shell command; `cmd9_table` widened to 4
  entries under `#if SCENARIO == 10`, loop bound `NCMD`): draws the whole
  rect — `for y in 0..FB_H: for x in 0..FB_W: __syscall(SYS_draw,
  y*FB_W+x, 0x40 + ((x+y)&0x0F))`. Exercises every cell.
- **Fixture SCENARIO 10** reuses GO-3's SCENARIO 9 shell wholesale: the
  `#if SCENARIO == 6||7||8||9`, `== 7||9`, and the `SCENARIO == 9` shell /
  input-ring / `SYS_read` guards were all widened to include `10`; the
  shell (`s9_shell`, `s9e`, `g_s9_input`, tokenizer, fn-pointer dispatch)
  is shared. The GO-4-only additions are the `#if SCENARIO == 10` blocks:
  `SYS_draw`/`FB_*` defines + `g_fb`, the `SYS_draw` dispatcher `case`,
  `cmd9_plot` + its table entry. `userinit` `#elif SCENARIO == 10`:
  `proc[0].context.ra = &s9e`, `proc[1]/[2] = UNUSED`. Scheduler arms
  `BOX1/BOX2/MODE_LATCH` (no `BOX0`, no tile) as for SCENARIO 9.
- **Carried GO-3's transpiler-collision guard**: `_build` passes
  `-ffixed-x27..x31` for SCENARIO 10 as well as 9 — the `SYS_draw`
  dispatcher branch adds the same register pressure. No glyph runaway
  observed with the fence in place.
- **Scripted input** `b"plot\n"`. `test_go4_framebuffer_on_gpu[10]` builds
  SCENARIO 10, seeds the input ring on both engines, runs `_run_glyph`
  (reference, `ksys_rv_addr`) and `_run_gpu_iso` (GPU), reads back all
  `FB_W*FB_H` cells of `g_fb` by symbol, and asserts (a) `GlyphCPUv2` ≡
  `SpatialRV64ICore` cell-for-cell, (b) each cell `== 0x40 + ((x+y)&0x0F)`,
  (c) two words just right of the rect (`g_fb[FB_W]`, `g_fb[W_MEM+FB_W]`)
  stayed `0` on both engines (bounds held, no row spillover).
- **GO-5 implication:** none blocking. GO-4's `SYS_draw` + `g_fb` compose
  with GO-2's tile box and GO-3's shell input unchanged. SCENARIO 11 =
  3 tiled isolated procs + `s9_shell` over scripted input + a `plot` draw
  into `g_fb` + one out-of-tile store from proc[2] that traps and is
  reaped, proc[0]/proc[1] finish, image halts — all machinery now exists;
  GO-5 is composition + one differential test, likely zero engine change.
  If GO-5 wants the shell to hand the draw target around generically,
  add the single `FB_BASE_ADDR` MMIO word (scheduler seeds `(uint)&g_fb`)
  then.

**Test:** `xv6_nano.c` SCENARIO 10 — run `plot`, read back the framebuffer
region, assert the pattern; both engines bit-identical. **Gate.**

### GO-5 — the end-to-end GPU OS scenario
Compose GO-1…GO-4: 3 procs, each a tile, isolation enforced; proc[0] runs
the shell over scripted input; a shell command spawns a framebuffer draw;
an out-of-tile store from proc[2] traps and is reaped; proc[0]/proc[1]
finish; image halts. **Test:** `xv6_nano.c` SCENARIO 11 green on
SpatialRV64ICore and bit-identical to GlyphCPUv2. **This is "Done =".**
**Gate → roadmap closed.**

---

## Increments if GO-0 = B (sketch, not detailed until chosen)

B-1 widen WGSL glyph engine to 64-wide + fix fall-through/row-wrap · B-2
`JMPR`/`CALLR` + pointer-table indirection + 16384-word memory · B-3
`KJMP` + `SYSCALL`/`SYSRET` + box (the E-K1/E-K2 port) · B-4 first
xv6-nano scenario on the WGSL glyph engine, two-way vs GlyphCPUv2 · then
rejoin at GO-2.

---

## Loop protocol

Self-paced `/loop`. Each iteration: pick the current increment, implement
engine + twin + fixture scenario + differential test, run the gate
(`pytest tests/test_rv64i_to_glyph*.py tests/test_glyph_isa_v2.py
tests/test_spatial_rv64i_cpu.py` + the WGSL differential harness), keep
twins byte-identical, **commit only on green**, then **stop** and surface
the next increment's design forks. The loop never starts a new increment
without a human gate. Stop conditions: GO-5 green + committed, or any
increment that needs a decision the roadmap didn't anticipate.
