# RV64I → Glyph transpiler roadmap

Extend `tools/rv64i_to_glyph.py` (parity copy `glyph_dispatch/src/glyph/`) far
enough to transpile a real xv6-nano-shaped scheduler primitive — proving the
instruction-level coverage a spatial-OS kernel would actually need — while
never regressing the 5 primitives already verified.

Companion: `~/.claude/projects/-home-jericho-projects-zion-projects-visual-audio/memory/rv64i-to-glyph-transpiler-verified.md`
(Claude Code's own record, since the workflow skill landed in Hermes's store,
not this session's).

## How this roadmap is run

Same discipline as `glyph_dispatch/ROADMAP.md` / `FASTPATH_ROADMAP.md`:

1. **Oracle before feature.** Every item ships a fixture + a three-way
   differential test (native x86 ground truth, GPU `SpatialRV64ICore`,
   `GlyphCPUv2`) before any transpiler code changes. Verify expected constants
   against native x86 FIRST — this project's own history shows fixture
   address-math bugs are as common as transpiler bugs.
2. **The gate is the full differential suite**: `pytest tests/test_rv64i_to_glyph*.py
   tests/test_glyph_isa_v2.py tests/test_spatial_rv64i_cpu.py`. A change lands
   only if it stays green AND `cmp -s tools/glyph_isa_v2.py
   glyph_dispatch/src/glyph/glyph_isa_v2.py` (the parity copies must stay
   byte-identical — the pre-commit hook already enforces this).
3. **Receipts are command output.** Paste the pytest summary line, not a
   sentence describing it.
4. **Small commits.** Each primitive is one commit: fixture + transpiler fix
   (if any) + test.
5. **A fixture must prove it exercises the instruction class it claims to.**
   Sanity-assert via `objdump` (or equivalent) that the compiled binary
   actually contains the opcode under test — a fixture that doesn't exercise
   its own claim is worse than no fixture (see the negoffset primitive, where
   `bump_alloc`'s `-O1` codegen turned out to contain zero negative-offset ops).

## Known state (2026-09-04)

5 primitives landed on `fastpath-autoloop`, 24/24 tests green, independently
re-verified (not just taken on report):

| Commit | Primitive | Gap closed |
|---|---|---|
| `8897fd4`-adjacent | bump_alloc | globals, calls, ecall halt |
| `8897fd4` | negoffset | negative immediates; found RET-on-empty-stack looping forever |
| `a770017` | fifo | struct fields, pointer deref, power-of-two wraparound |
| `51fd7bc` | slab | free-list pointer chasing, LIFO reuse; wired pre-commit gate |
| `5692bd0` | proc-table | `jalr` through a fn pointer; found return-address-drop + the 1D-byte-address-vs-2D-pixel-PC address-space mismatch, fixed via `PTR_TABLE_BASE` lookup table |
| `85ffdce` | switch_to (Primitive 6) | swtch.S-style cooperative context switch; RET-vs-resume dataflow (see G1/G2 below) + CALL/CALLR now materialize `rd` as data, not just the internal stack |

**Landmine — RESOLVED in `85ffdce` (G1+G2 done together):** the transpiler's RET-detection rule was
**syntactic** — `rd==0 && rs1==ra && imm==0 → RET`. `swtch.S`-style context
switches produce exactly this instruction after *reloading* `ra` from saved
state (a resume, not a call-stack pop) — same bytes, opposite meaning. The
current rule cannot tell these apart by inspecting one instruction. This will
misclassified it, by construction, until fixed.

Fix landed as local (not global) dataflow on x1: `ra_source` = 'call' unless
the most recent write to x1 since the last label/branch-target was a load
with `rs1 != sp` — an ordinary epilogue's `lw ra,N(sp)` is RET-safe (rs1==sp);
a swtch-style `lw ra,0(a1)` is not. **First attempt over-fired** (flagged
`rs1==sp` loads too — i.e. every ordinary epilogue — as 'data', breaking
bump_alloc/fifo/slab; caught immediately by the full suite before commit, not
shipped). Separately, `CALL`/`CALLR` now also `LDI rd = return_byte_addr`
*before* the jump (Glyph's call stack alone never materializes a register the
way real `jal rd,` does; code treating `ra` as data needs the value
synchronously at callee entry).

## Status

| # | Item | Oracle | State |
|---|------|--------|-------|
| G1 | Primitive 6 — two-task `switch_to`/`swtch`-style cooperative context switch | fixture MUST contain both an ordinary call/return and a `lw ra,...; ret` resume in the same test, so the suite can't pass by only exercising one; three-way bit-identical | ✅ done — `85ffdce`, 25/25 |
| G2 | Fix RET/resume ambiguity properly | local dataflow on x1, `rs1==sp` distinguishes epilogue-restore from data-load; regression-tested by G1's fixture | ✅ done — `85ffdce` (landed together with G1 — diagnosing G1 directly produced the fix) |
| G3 | Scale test — few-hundred-instr program, real round-robin loop (3+ tasks, not 2 sequential yields) | glyph CPU step budget + label/pointer-table resolution hold at size; three-way bit-identical | ✅ done — `3d62e7e`, 26/26 (4 real bugs found & fixed: A/B/C/D below) |
| G4 | xv6 `fs.c`-shaped primitive — in-memory inode table lookup | array-of-structs indexing, not just single-struct pointer chasing (new gap vs. slab/fifo) | ✅ done — `c3d1c1b`, 27/27 — passed first try, no new bug (the G3 fixes were general, not narrow patches) |
| G5 | Document + lock the transpiler's known-op coverage | a table of every RV64I op the mapper handles vs. doesn't, generated from `rv64i_to_glyph.py`'s own switch, not hand-maintained prose | ✅ done — `3ee1536`, `tools/rv64i_to_glyph_coverage.py` + `GLYPH_TRANSPILER_OPCODE_COVERAGE.md`. 32/87 handled; real gaps surfaced: `SLTIU`, all sub-word memory ops (`LB/LBU/LH/LHU/SB/SH` — blocks any `char`/`short` C code), `AUIPC` |

## All items done — roadmap closed

G1–G5 complete: 8 primitives landed (bump_alloc, negoffset, fifo, slab,
proc-table, switch_to, round-robin scheduler, inode table), 27/27 tests,
9 real transpiler bugs found and fixed, opcode coverage generated and
documented. See `tools/GLYPH_TRANSPILER_OPCODE_COVERAGE.md` for what to
check before starting the next primitive.

**G6 (post-closure, `529ae69`): sub-word memory (LBU, SB).** The gap G5
flagged as the real next blocker, landed. `checksum_str`/`copy_str` over an
8-byte buffer spanning both words and all 4 lanes, passed on the first run.
Word-indexed memory means byte access needs `word_addr=addr>>2,
lane=addr&3, shift=lane*8`; `SB`'s read-modify-write clears the target lane
via the no-NOT-needed identity `(x|m)^m == x&~m`. Coverage now 34/87. Signed
`LB` and immediate-form `SLTIU` are the nearest remaining gaps — not yet
needed by any fixture, so not built ahead of a real need.

**G7 (post-closure): first run against REAL xv6 source.** All prior
primitives were hand-written C shaped like kernel code; this one lifts
`xv6-riscv/kernel/kalloc.c` (`freerange`/`kfree`/`kalloc`) and
`riscv.h`'s `PGROUNDUP` **verbatim**, plus `string.c`'s `memset` byte
loop. Mechanical shims only (PGSIZE 4096→32 to fit the core; lock/panic
stubs; `end`/`PHYSTOP` as fixture addresses; memset's `uint64` fast path
dropped — it needs libgcc under `-nostdlib`). Scenario: `freerange` fills
the freelist, `kalloc` drains it (5th → 0), verify `kalloc`'s
`memset(_,5,PGSIZE)` actually painted a handed-out page (`0x05050505`),
free two, confirm LIFO reuse, checksum. `tests/test_rv64i_to_glyph_kalloc.py`,
three-way bit-identical, **green first try — no transpiler change**. The G6
sub-word `sb` lowering held up under a real per-page store storm.
One transpiler-shape constraint surfaced (not a bug): a bare `_start` must
set `gp` with absolute `lui/addi %hi/%lo(__global_pointer$)` — GCC's
small-data refs are gp-relative, and `la`/`call`-pseudo/medany all emit
`auipc`, which the mapper has no lowering for. Documented in the fixture.

**G8 (post-closure, `a3a972e`): whole xv6 `kernel/string.c` verbatim +
first real transpiler gap since G3.** `memset`/`memcmp`/`memmove`/`memcpy`/
`strncmp`/`strncpy`/`safestrcpy`/`strlen` lifted byte-for-byte (only the
`#include` removed). Scenario: `strlen`, `strncpy`, `safestrcpy` truncation,
three `strncmp` orderings, a `memcmp`, an overlapping backward `memmove`
(`memmove(buf+2,buf,4)` on `"abcdefgh"` → `"ababcdgh"`), all folded into a
layout-independent checksum.
- **Gap found & fixed:** `parse_elf` only ever extracted `.text`. Every
  prior fixture's globals were zero-init BSS, so nobody noticed. This is
  the first fixture with non-zero initializers (string literals, `char
  buf[]="..."`), and on the glyph path every such read returned 0 (GPU
  was fine — `load_program` consumes the whole objcopy image). Fix: new
  `parse_elf_data_sections()` returns the `SHF_ALLOC` PROGBITS non-`.text`
  sections as `(vaddr, bytes)`; the test seeds `GlyphCPUv2.memory`
  word-packed little-endian before running. Additive, parity twin synced,
  no opcode-table change (still 34/87).
- **Recorded finding:** xv6 `string.c` at `-O1 -march=rv32i` emits **zero
  `lb`** — every char access is `lbu` (comparisons/nonzero tests need no
  sign extension; `(uchar)` casts on returns make widening unsigned). The
  "a `char*` routine forces signed LB" expectation does not hold for this
  actual source. The test asserts `lb` is *absent* so a toolchain change
  that introduces it trips a re-evaluation. Signed LB stays unimplemented,
  still not built ahead of a real need.

**G9-hygiene (post-closure, `e08020d`): executable tripwires for the open
opcodes.** `tests/test_rv64i_to_glyph_unimplemented_ops.py` -- for `SLTIU`,
`LHU`, `SH`, `AUIPC`: compile a snippet that provably emits the op
(objdump-checked), then assert `transpile_elf_to_glyph` still raises
`ValueError`. When one gets implemented its tripwire flips red -- that's the
cue to replace it with a real three-way fixture. Findings from writing them:
- **`LB`/`LH` are not reachable gaps.** GCC rv32i `-O1` lowers a `signed
  char` load to `lbu` + `slli` + `srai` (shift-pair sign extension), never
  `lb`. All three of those are already handled -- pinned by
  `test_signed_char_load_uses_shift_substitution`.
- **`LHU` is the real 16-bit blocker.** GCC uses `lhu` (+ shift pair when
  signed) for *both* `short` and `unsigned short` loads. So `LHU` + `SH`
  together mean no 16-bit C compiles today -- the honest "sub-word gap",
  narrower than the coverage table's `LB/LH/LHU/SH` list implies.
- `AUIPC` needs `-mcmodel=medany -msmall-data-limit=0` to be emitted from C
  at all (otherwise small globals stay gp-relative).

**G9 (post-closure, `2777396`): xv6 `bio.c` buffer-cache LRU list + real
transpiler bug.** `binit`/`bget`/`brelse` lifted verbatim -- circular
doubly-linked list, sentinel `head`, in-place recycle on a miss, full
unlink/relink move-to-front on the last `brelse`. First fixture with a
doubly-linked circular list (vs. singly-linked freelist or array of
structs). Scenario: miss/miss/hit + `brelse`x3, final order read out as
`b - bcache.buf` indices (layout-independent). Three-way bit-identical.
- **Bug found & fixed:** `OP_SUB` with `rs1==0` -- i.e. `neg rd, rs`
  (`sub rd, x0, rs`) -- emitted `LDI rd 0; SUB rd r{rs2}`, correct only
  when `rd != rs2`. GCC emits `neg a5, a5` routinely (here inside the
  `/28` pointer-difference exact-division chain); with `rd==rs2` that
  computed `0 - 0 = 0`. Fixed: route the source through `r29` scratch
  before clobbering `rd`. Nothing before bio.c did an in-place negate
  whose value reached an observable. Parity twin synced, 34/87 unchanged.
  `bio.c` is the regression guard (the negate is incidental-but-load-bearing
  in its readout).

**G10 (post-closure, `0f80e32`): 16-bit memory (LHU + SH).** Last operand
width. Mirrors G6's LBU/SB with 16-bit lanes: `lane = (addr >> 1) & 1`,
`shift = (addr & 2) << 3` (0 or 16); `LHU = (word >> shift) & 0xFFFF`;
`SH` = RMW clearing the lane via `(x | m) ^ m`, `m = 0xFFFF << shift`.
Byte/halfword/word all covered now. Coverage `34/87 -> 36/87`. Fixture
`test_rv64i_to_glyph_dinode.py` lifts `struct dinode`/`struct dirent`
layouts from `fs.h` (`short type/major/minor/nlink`, `ushort inum`), reads
every field back, three-way bit-identical. LHU/SH tripwires in
`test_rv64i_to_glyph_unimplemented_ops.py` removed (SLTIU/AUIPC remain).
- **RV32-on-RV64 hazard noted, not fixed (out of scope):** GCC's signed
  sub-word read-back is `lhu; slli 16; srai 16` -- an XLEN=32 idiom. On the
  64-bit `SpatialRV64ICore` bit 15 lands in bit 31, not the sign bit, so a
  *negative* halfword does not sign-extend there (GPU gave `0x0000fffd`
  where native gave `0xfffffffd`). The fixture keeps every field value
  >= 0 so signed == unsigned on any width; a real signed-16-bit fixture
  would need an rv64 `-mabi=lp64` build or a transpiler sign-fixup.

**G11 (post-closure, `b23e2bd`): SLTIU + AUIPC -- last two opcode tripwires
zeroed.** `SLTIU` = immediate `SLTU` (XOR-sign-bit, signed subtract,
sign-of-difference; `rs1` read before `r{rd}` written so `seqz rd,rd`
aliasing is safe). `AUIPC` = `pc + (imm20 << 12)`; `pc` is a compile-time
constant here so it folds to one `LDI`. Fixture
`test_rv64i_to_glyph_sltiu_auipc.py` (built `-mcmodel=medany
-msmall-data-limit=0` so every global address is an auipc/addi pair), green
first try, three-way bit-identical. `test_rv64i_to_glyph_unimplemented_ops.py`
parametrized tripwires removed -- **nothing armed remains**: every other
unhandled opcode is RV64-only (`*W`), a libgcc-call extension
(`MUL`/`DIV`/`REM`), or privileged/atomic/fence, none reachable from
portable rv32i `-O1` `-nostdlib` C. The signed-char `lbu+slli+srai`
substitution guard stays. **Coverage 36/87 -> 38/87 = 100% of the base
RV32I opcodes GCC emits from this input.**

## Where the transpiler stands after G11

Every base-RV32I opcode reachable from `-nostdlib -march=rv32i -O1` C now
lowers and is differential-verified. Byte/halfword/word memory all covered.
Four real xv6 files (`kalloc.c`, `string.c`, `bio.c`, `fs.h` structs) plus
the earlier hand-shaped primitives transpile bit-identically across native
x86 / GPU `SpatialRV64ICore` / `GlyphCPUv2`. 11 real bugs found and fixed
over G1-G11. Remaining work is all opt-in, none built ahead of need:

- ~~**`stack_addr` auto-sizing**~~ **DONE (`6c4cc06`).** `stack_addr`
  defaults to `None` = auto: `transpile_rv32i_to_glyph` counts its own
  emitted glyph instructions and places r31 one pixel inside a blank band
  `_STACK_GAP_ROWS` (16) rows below the last code row;
  `assemble_glyph_to_pixels` pads the image to match from its own count, so
  the two agree and the outermost RET still reads a zero pixel. `cols_instrs`
  is now a transpile param (default 64). All 15 fixtures dropped their
  hand-picked literal. An explicit int still overrides.
- ~~**Division** (`__udivsi3`/`__umodsi3`)~~ **UNSIGNED done (`bd0bfc5`).**
  `test_rv64i_to_glyph_softdiv.py` ships pure-C shift-and-subtract stand-ins;
  GCC resolves its own runtime `/` `%` to them; every op already lowered; no
  transpiler change; three-way bit-identical. **Scoped to unsigned:** signed
  `__divsi3`/`__modsi3` at `-O1` use the branchless abs idiom `srai rX,31;
  xor; sub`, and `srai` of a *negative* is not three-way consistent --
  **GlyphCPUv2's `SRA`/`SRAI` is LOGICAL (no sign-extend)** (real
  transpiler-stack bug, CMP-writes-r0 category; masked so far because landed
  fixtures only `srai` non-negative values or feed a branch), and
  `SpatialRV64ICore` is 64-bit (the G10 hazard). xv6 `printint` does
  signed->unsigned with an explicit `if (xx<0) x=-xx;` branch, so
  `__divsi3` is off the path to G12.
- ~~**Varargs** (`va_start`/`va_arg` register-spill area)~~ **DONE
  (`e87b325`).** `test_rv64i_to_glyph_varargs.py` exercises the ilp32
  variadic ABI end to end (named arg in a0, a1..a7 callee-spilled to the
  register-save area, args past a7 from the caller stack, `va_list` walked
  word by word). `<stdarg.h>` builtins only; codegen is all already-lowered
  ops; no transpiler change; three-way bit-identical, green first try.
- ~~**G12 -- xv6 `printf.c`**~~ **DONE (`144ad56` fixture, `594bd81`
  green).** Real xv6 `vprintf` + `printint` lifted verbatim (long long->int,
  putc->console buffer, ships `__udivsi3`/`__umodsi3`); renders
  `"-42 BEEF Z hi 7%\n"` byte-identical on native x86 / `SpatialRV64ICore` /
  `GlyphCPUv2`. Composes items 2 (divider) + 3 (varargs) + G6 (`lbu`/`sb`) +
  G11 (`auipc`) + auto-stack. **The "hang" was a test-harness omission, not
  an engine bug:** GCC compiles the `if(c0=='d')...else if...` char chain
  into a `.rodata` jump table + `jr`; the transpiler routes that through
  `PTR_TABLE_BASE` (like proc-table / round-robin), but the fixture didn't
  call `build_pointer_table()` to seed it, so `jr` read 0 and looped to
  pixel (0,0) forever. Seeding the table fixed it. New fixture-convention
  point: **any fixture whose `-O1` codegen contains a switch/jump table must
  seed `PTR_TABLE_BASE`.** `%p`/`printptr` stays dropped (its
  `for(...; x<<=4)` relies on 32-bit truncation the 64-bit GPU core skips).
- ~~**GlyphCPUv2 `SRA`/`SRAI` is logical**~~ **FIXED in the transpiler
  (`7e95e22`).** Glyph ISA v2 has only logical `SHR`; `SRAI`/`SRA` now emit
  a branchless sign-extend `((x ^ 0x80000000) >>u n) - (0x80000000 >>u n)`
  (no NOT opcode). `SRL`/`SRA` also mask the runtime count into `r26` first.
  Positive operands unaffected. `test_rv64i_to_glyph_arithshift.py` covers
  negative `srai 1/4/31` + `sra` reg form -- **native-vs-Glyph only**: the
  GPU leg is asserted STILL wrong (SpatialRV64ICore's `srai` of an rv32
  negative is a separate 64-bit bug, out of scope; the assert flips if it's
  fixed).
- **RV32-on-RV64 sign-extend hazard** (G10) -- GCC's `slli N; srai N`
  sub-word sign-extend idiom still isn't three-way consistent (the `slli`
  doesn't reach bit 63 on the 64-bit GPU core). Needs `-mabi=lp64` fixtures
  or a `SpatialRV64ICore` fix -- distinct from the transpiler `srai` fix
  above.
- **Human gate:** composing the primitives into an actual xv6-nano
  kernel with a spatial memory-isolation policy -- design work, Timothy's
  review first.

### Autoloop status (2026-09-05)

The "finish the roadmap" autoloop landed items 1-3 (stack_addr auto-size
`6c4cc06`, unsigned software divide `bd0bfc5`, varargs `e87b325`), then
stopped at G12 on a suspected engine hang. Follow-up (`you lead`): the hang
was a missing `build_pointer_table()` seed for GCC's switch-table `jr`, not
an engine bug -- **G12 landed green (`594bd81`)**. The `SRA`-is-logical
finding turned out to be a transpiler lowering gap too, **fixed (`7e95e22`)**.

**All planned roadmap work is now done.** Every base-RV32I opcode GCC emits
from `-nostdlib -O1` C lowers and differential-verifies; five real xv6
sources transpile bit-identically (`kalloc.c`, `string.c`, `bio.c`,
`fs.h` structs, `printf.c`); 12 real bugs found and fixed over G1-G12 + the
loop. Remaining items are all opt-in / gated:
- **G10 XLEN hazard** (`slli;srai` sub-word sign-extend on the 64-bit GPU
  core) -- needs `-mabi=lp64` fixtures or a `SpatialRV64ICore` fix.
- **Human gate** -- composing the primitives into an xv6-nano kernel with a
  spatial memory-isolation policy; design work, Timothy first.

### G3 status — two real bugs found, one fixed, one open

Fixture (`tests/fixtures/switch_round_robin.c`, uncommitted, deliberately —
it still fails, differently now): 3 tasks + a central `scheduler()` that
round-robins them via `switch_to`, each task running a real `for` loop of
work units. GPU ground truth is clean throughout (12 switches, exact
expected log, all 3 done) — every bug below is glyph-only.

**Bug A — fixed (`cce2680`): r0-as-zero corruption.** Glyph `CMP` writes its
equality flag into `r0`; RV `x0` (hardwired zero) maps straight through to
glyph `r0` everywhere else. `BLT`/`BLTU`, `BGE`/`BGEU`, and the SLTU added
this tick all read `r{rs1}`/`r{rs2}` unconditionally even when that register
is `x0` — a branch comparing against zero (`blez`/`bgez`, e.g.
`while(active>0)`) downstream of an equality-true `CMP` would read the stale
flag instead of true zero. `BEQ`/`BNE` already special-cased this; the other
comparison lowerings didn't. Fixed via `_emit_add_reg`/`_emit_sub_reg`
helpers that skip the op entirely when the RV register is x0. Real,
independently confirmed bug — but turned out NOT to be this test's actual
blocker (symptoms were identical with and without the fix), so it was caught
by inspection/general audit, not by this specific fixture's oracle.

**Bug B — found and its worst form fixed (test still not green): `stack_addr`
collides with the program's own instruction image.** `GlyphCPUv2._mem_write`/
`_mem_read` (what `CALL`/`RET`'s hardware stack, r31, uses) address the SAME
pixel array that holds the program's code — there is no separate stack
segment; `stack_addr` is a linear pixel index into it. The smaller primitives'
convention (`stack_addr=1500` or `2000`) was safe only because their code
never grew large enough to reach that linear offset. This fixture's ~560
glyph lines DO reach it (row 5, col ~216) — every CALL/RET push/pop was
silently overwriting live scheduler code, which is what produced the
"`s2` stuck 3 increments past reset" symptom chased at length before this
was found (that trail was a real dead end: the corruption source was a
pixel-level aliasing bug, not a control-flow/dataflow bug in the emitted
assembly, which is why direct inspection of `:pc_000001ec`/`:pc_000001f0`
found nothing wrong — there was nothing wrong there). Raising `stack_addr`
to a value safely past the program's instruction-pixel footprint (tried
7000–8100, all identical) makes the run **halt cleanly** instead of spinning
forever — confirms this class is fully fixed.

**Bug C — FIXED (`183d06d`).** GCC's `snez rd,rd` idiom (the scheduler's
`!(mask & bit)` "is this task done?" check) compiles to `sltu rd,zero,rd` —
`rd` and `rs2` are the SAME register. SLTU's lowering wrote `LDI r{rd} 0`
(zeroing the destination) before `rs2`'s value was fully consumed, so
whenever `rd` aliased `rs1` or `rs2` the source was clobbered before use.
Live effect: `active` decremented on every task yield instead of only when a
task genuinely finished all its work units — wrong scheduling, not a crash,
which is why it needed tracing rather than a failing assert to even notice.
Fixed by reading both operands into scratch (`r28`, `r30`) before ever
writing `r{rd}`. **Verified: with A, B, and C all fixed, the fixture's
LOGICAL state is now exactly correct** — `done_mask=7, switches=12,
log_idx=9, rounds=[3,3,3]`, log matches GPU ground truth exactly, checked
directly (not inferred from the halt flag).

**Bug D — FIXED (`3d62e7e`). Glyph call-stack (r31) imbalance, two sources.**

1. switch_to's own terminal `ret` always routes through the computed-jump
   path (`ra_source=='data'`, correctly, per G1/G2 — it's a resume, not a
   return). But the `CALL` that invoked *this activation* of switch_to
   already pushed a frame that a real `RET` would have popped; routing
   around `RET` silently leaked it. After 24 accumulated switch_to calls (12
   scheduler-initiated + 12 task-side yields) in this fixture, an unrelated
   *later* function's genuine `ret` — scheduler's own — popped a stale
   leaked entry instead of its true return address, landing inside a task's
   dead-end `for(;;)` placeholder instead of back in `run_all`. Fixed: emit
   `POP r28` (discard) immediately before the computed jump whenever a
   ret-shaped JALR is `ra_source=='data'`, to balance the stack the way a
   real `RET` consumption would have.
2. `tests/fixtures/switch_round_robin.c`'s `task0/1/2_entry` trampolines
   used an ordinary C call into `task_body`, which by design never returns
   (always exits via switch_to's non-returning jump or spins in `for(;;)`).
   GCC compiles that as a genuine `jal ra,task_body`, pushing a frame
   nothing will ever pop — a permanent, structural leak distinct from (1)
   and not inferable by the transpiler (it doesn't know `task_body` never
   returns). Fixed at the fixture level: raw asm `j task_body` (a true
   RV jump, `rd=zero`, never pushes) instead of a C call.

Diagnosis: instrumented CALL/CALLR/RET/POP/JMPR execution counts over the
whole run (29 `CALL` vs 25 pop-family before the fixture fix pinned the
remaining 4-push gap to exactly the 3 orphaned `task_body` entries), and
traced `r31`'s value trajectory directly to confirm it returns to baseline
after the fix rather than merely "halting less wrong". `tests/test_rv64i_to_glyph_round_robin.py`
now passes outright: `done_mask=7, switches=12, log_idx=9, rounds=[3,3,3]`,
log matches GPU ground truth exactly, and the program reaches `ecall` and
halts cleanly on both engines. **G3 is closed.**

**General fix worth doing before more scale tests:** the transpiler (or the
test harness convention) should pick `stack_addr` automatically, safely past
`len(instructions) * INSTR_WIDTH`, instead of a hand-picked literal — this
exact class of bug will recur on every future larger primitive otherwise.

## Human gate (not autoloop material)

Composing multiple primitives into an actual xv6-nano scheduler/kernel — real
task tables, real cooperative dispatch loop, real spatial memory-isolation
policy — is a design project, not a falsifiable-oracle item. It belongs after
G1–G4, reviewed by Timothy before any code, same as the fast-path F4/F5 gate.

## Non-goals

- Full Linux or unmodified xv6 kernel to Glyph (needs MMU/CSRs/privilege
  levels the ISA doesn't have — settled, don't re-litigate).
- RV64M/RVC/floating point in the mapper unless a real primitive needs it.
- Touching `RISCV_CPU_MMU.wgsl` or the fast-path files (`FASTPATH_ROADMAP.md`'s
  territory, separate roadmap).
- Any change to `SpatialRV64ICore` itself — this roadmap only extends the
  Python-side transpiler and `GlyphCPUv2`.
