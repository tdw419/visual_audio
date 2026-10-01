# RECEIPT — item-20 shell-native swap (builder af3e62239ce2, 2026-09-25 ~20:0x CDT)

## What landed

- `experiments/glyph_l1_shell.py`: dispatch arms route `grep` and `tr`
  through the transpiled glyph binaries (item-19 COREUTILS2 volume port:
  riscv64-unknown-elf-gcc -march=rv32i → `_load_posix_program` →
  `libc_runtime_kernel_image` → `GlyphRunner`, output decoded from the
  BK-24 stream ring [768, cursor)). The swap is DYNAMIC: the session
  file's bytes ride as a generated C literal in the seed .data, so any
  session file works — no runtime fixture table.
- Loud-refusal contract: missing cross-toolchain → `ERR:SHELLNATIVE:<verb>`
  (never a silent host-shim fallback); missing file → `ERR:NOENT` before
  any compile; engine halt/fault → `ERR:SHELLNATIVE:<verb>`.
- `wc`/`head` deliberately NOT swapped: their landed BK-11 binaries
  deliver through the fixed 16-byte window and both report shapes exceed
  it on real files (measured: wc report = 17+ bytes; head of 2 lines =
  24 bytes). Swapping would truncate. Disclosed in code + here.
- `tr` added to L1_VERBS (the `which` table) — the dispatch arm existed
  but the verb list didn't, so `which tr` ERR'd while `tr` executed;
  measured inconsistency, fixed.
- Pipe splice scoping: `_pipe` producers run the host shims (native arm
  OFF for the producer turn only, same L4b-tested branch point, loudly
  commented). See RED-3 below for the measured reason.

## Gate (tests/test_item20_shell_native_swap.py, 9 legs) — RED first, then GREEN

RED legs (pre-fix runs, pasted from this session's pytest output):

1. `test_l3_wc_head_stay_host_side`: `assert '4 7 41 fruits.txt' ==
   '4 8 45 fruits.txt'` — the test's authored pin was an author
   miscount. Measured with real `wc`: `printf 'apple pie\nbanana
   bread\napple tart\ncherry\n' | wc` → `4 7 41`. Fixed the PIN, not
   the shim (the shim matches POSIX).
2. `test_l4a_glyph_executor_runs_the_binary`: `assert 'banana bread' ==
   ' banana bread'` — the write arm prepends one space to the FIRST
   line only (measured raw bytes: `b' apple pie\nbanana bread\n...'`),
   so grep hits on line 2+ carry no leading space. Pin fixed to the
   measured bytes; the L1 host-reference parity leg (independent
   oracle) passed both before and after — executor was correct, the
   literal was wrong.
3. `test_l6_untouched_verbs_and_which` (two sub-failures):
   `assert ' hello' == 'hello'` — echo's leading-space convention is
   documented and pinned by pre-existing gates
   (test_glyph_app_shell_dispatch leg 1, test_l1_shell_personality:53);
   pin fixed. `assert 'ERR:UNKNOWN_CMD' == 'tr'` — the real
   L1_VERBS omission, fixed in the module.
4. Neighbor regression caught by the wide run:
   `test_p7_multiline_across_windows_head_tail`:
   `assert 'ERR:SHELLNATIVE:grep' == '100 100 2399'` — the swap broke
   the landed pipe gate. Root cause (measured,
   .builder_queue/dbg_item20_budget_af3e.py): the glyph-executed grep
   is clean through 24 lines (~576B output; steps scale ~2100/line) and
   FAULTS at 25+ lines (faulted=True mid-ring; fault_addr 0x256E696C).
   The BK-24 write tile appends 4 words per write() with NO saturation
   handling — ring overflow is a documented NON-GOAL
   (tools/glyph_gpt/libc_runtime.py:111-116: "every landed fixture
   flushes at most twice (32 words < 64)"). P7's producer streams 2399
   bytes — ~10x past the boundary. A saturated/paged write tile needs a
   branch in stamped tile text = the defect class BK-24 deliberately
   avoids = engine-side work, not item-20 scope. Scoping fix: pipe
   producers keep the host shims until that engine rung lands.

GREEN legs (final):

- `tests/test_item20_shell_native_swap.py`: 9 passed in 12.05s (exit 0).
- Full neighbor surface (blast-radius check):
  `tests/test_l2_files.py tests/test_l3_pipes.py
  tests/test_glyph_interactive_shell.py tests/test_coreutils_volume2.py
  tests/test_bk11_coreutils.py tests/test_gh23_libc_runtime.py
  tests/test_l1_shell_personality.py tests/test_l4_desktop.py
  tests/test_item20_shell_native_swap.py` → **111 passed in 80.36s**.
- RED discrimination for the swap itself (in-gate L4b): `_SHELL_NATIVE`
  flip proves the branch point is live — both executors answer, the
  glyph one runs the binary (L4a: different patterns → different,
  correct outputs).

## What the PASS does NOT prove

- No WGSL twin leg (foreign to this gate's threat model, per the
  0x07/0x12 precedent).
- Compile+transpile+bake runs PER TURN (~1.7s measured on 3-line
  files; 4.65s on the 100-line probe) — a caching layer is later
  optimization, not part of this item.
- wc/head swaps blocked on 16-byte window (backlog: volume-port them).
- Ring saturation/paging for the BK-24 tile is OPEN engine work — the
  pipe producer scoping is a documented boundary, not a fix.
- No in-guest execution (host engine runs the baked image, as every
  landed gate does).
- R1.4 WGSL convergence gate remains open and untouched.

## Files touched

- experiments/glyph_l1_shell.py (modified: dispatch arms + _shell_native
  + L1_VERBS + pipe-producer scoping; +230/-2 measured by git diff --stat)
- tests/test_item20_shell_native_swap.py (NEW, force-add past
  .gitignore's test_*.py rule)
- .builder_queue/dbg_item20_budget_af3e.py (NEW: budget/fault probe)
- .builder_queue/RECEIPT_item20_shell_native_swap.md (this file)
- .builder_queue/QUEUE_STATE.json + CURRENT_TICKET.json (item-20 landed)

No engine/codec/WGSL files touched. Protected assets untouched.
