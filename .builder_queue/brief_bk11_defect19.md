TASK — DEFECT-19: bound the GH-9 loader's patch-window copy span so an injected program can never reach the loader kernel's own in-box ABI words. Roadmap row: BK-11 (systems/GLYPH_SELF_HOSTING_ROADMAP.md). Authority: .builder_queue/RULING_20260912_defect19_bk13_worktree.md section 1.

WHERE YOU ARE: cwd is the isolated worktree
  /home/jericho/projects/zion/projects/visual_audio/.worktrees/bk11-defect19
(branch bk11-defect19, based on d6ff321). Work ONLY here. Do not touch the main
checkout at ../.. (a parallel session is editing it).

ALREADY DONE — do not revert, do not re-create:
- tools/rv64i_to_glyph.py already carries the held DEFECT-16c LBU/LHU PUSH/POP
  patch (applied from .builder_queue/held_patches/defect16c_lbu_lhu.patch).
- tests/test_gh9_window_span.py was written by the orchestrator and encodes the
  invariant below. Two of its legs are RED right now, by design.

MEASURED STATE (orchestrator's runs, this worktree; do not re-derive):
  /usr/bin/python3 -m pytest tests/test_bk11_coreutils.py -q   -> 6 passed
  /usr/bin/python3 -m pytest tests/test_bk1_argv.py -q         -> 1 failed, 4 passed
      leg 2 red: `preemption corrupted result: 0x00000000 != 0x3b00112a`
  /usr/bin/python3 -m pytest tests/test_gh9_window_span.py -q  -> 2 failed, 5 passed

MEASURED GEOMETRY (GH-9 loader, tools/glyph_gpt/baker.py):
- `_gh9_kernel_program_text()` (line ~2045) emits: kmain prologue, launch leg,
  fault task, fault handler, [tick handler if timer_quantum > 0], done tail,
  then `:__g9window` + n_instrs HALT fillers.
- pre-window instruction count: 76 at quantum 0, 99 at quantum 12. The tick
  machinery adds exactly 23: the 11-instruction `:__g9tick` handler, the
  9-instruction KTICK_PC/TIMER_COUNT/TIMER_RELOAD arming in the prologue, and
  the 3-instruction zero of GH9_TICKS_COUNT.
- `_GH9_WINDOW_DST = wrow * (cols_instrs * 4) + wcol * 4` = 4 x (pre-window
  instructions). Measured: 304 at quantum 0, 396 at quantum 12.
- the loader PARALLEL_ST copy loop writes the injected program's pixel words to
  `[dst, dst + 4*N)` where N = the injected program's instruction count.
- the BK-1 injected program is 84 instructions without the held patch and 96
  with it (4 words per instruction).
- ABI words: GH9_EXIT_WORD 703, GH9_TICKS_COUNT 732, GH9_ARGV_WORD 750 (argc,
  argvp 751, envp 752), GH9_ARGV_RESULT 754, argv data 760-766.
- measured spans: quantum 0 -> [304, 640) landed / [304, 688) capacity(96);
  quantum 12 -> [396, 732) landed(84) / [396, 780) capacity(96).
- so at quantum 12 the landed program has exactly ZERO words of margin against
  GH9_TICKS_COUNT, and the 96-instruction variant overwrites 732 plus the whole
  argv block — that is BK-1 leg 2's red.

REQUIRED INVARIANT (must hold at timer_quantum 0 AND 12, with n_instrs = 96 as
the BK-1 harness bakes it):
    dst + 4 * n_instrs  <=  GH9_TICKS_COUNT    (= 732)
i.e. the window's capacity span [dst, dst + 4*n_instrs) must not touch 732 or
the argv/result words 750-752 / 754 / 760-766. With dst = 4 x pre-window
instructions and 4*96 = 384, that needs pre-window <= 87 instructions at
quantum 12 (currently 99).
GH9_EXIT_WORD (703) may stay inside the program's span — that is measured-benign
(the kernel zeroes it at boot, before the copy, and the injected program writes
it last). Do not move it.

RECOMMENDED MECHANISM (the only one the orchestrator found that needs no ABI
change; use it unless you have a measured better one):
1. Move the `:__g9tick` handler block out of the pre-window text — emit the
   reserved window first, then the handler. That removes 11 pre-window
   instructions (99 -> 88).
2. Recover >= 1 further instruction in the quantum>0 arming block, e.g. arm
   TIMER_COUNT_WORD and TIMER_RELOAD_WORD from one value register:
   LDI r15 w1 / LDI r14 q / ST r15 r14 / LDI r15 w2 / ST r15 r14 = 5 instead of 6.
   Pre-window then = 87 -> dst = 348 at quantum 12 -> capacity span [348, 732).
3. The relocated handler's own code must land on words nothing writes. Pad after
   the window with filler instructions so the handler starts at a fixed free
   word: use 968. (Free by measurement: past BOX0's end 768, past the GH-9
   default mailbox [800,896), the GH-10 shell words 903-912, status 950, flag
   960 / n_px 961, legacy 964, and below the GH-8b FS alias [1024,1280); the
   BK-1 harness's mailbox is at 2000.) Compute the pad from the pre-window body
   length you already know inside the text generator, so the pad is identical in
   the baker's two passes and the label coordinates agree between pass 1 and
   pass 2. Word 968 + 44 = 1012 < 36 rows x 32 words, so the image stays within
   the existing IMAGE_MIN_ROWS=36 — do not raise any test constant.
4. Fail loudly at bake time, host-side (this costs zero in-image instructions):
   add a module-level helper, e.g.
     gh9_window_span_conflict(dst_word: int, n_words: int) -> dict
   returning {word: name} for every loader ABI word a span would overwrite, and
   in `loader_kernel_image()` raise ValueError with the measured numbers when
   the requested window capacity span conflicts, and likewise when the relocated
   handler's code span would land on a written word. Keep it a pure helper plus
   one raise — no behaviour change for a non-conflicting bake.
   The assertion must NOT fire for any landed configuration: BK-1 (n_instrs=96,
   mailbox_data=2000, q0 and q12) and the GH-9 default (n_instrs=24,
   mailbox_data=800, q0 and q12).
5. Only if an in-image copy bound or refusal verdict can be added at ZERO extra
   pre-window instructions, add it and record the refusal word; otherwise say
   explicitly in your report that the loudness is bake-time only. Do not spend
   pre-window instructions on it — the margin is exactly zero.

FILES IN SCOPE (nothing else):
- tools/glyph_gpt/baker.py — GH-9 section only (`_gh9_kernel_program_text`,
  `loader_kernel_image`, plus the new module-level helper/constants).
Do NOT edit tools/rv64i_to_glyph.py (the held patch is already applied and
verified), tests/test_bk1_argv.py, tests/test_bk11_coreutils.py, or
tests/test_gh9_window_span.py (that file is the gate you must satisfy).
No drive-by edits anywhere else: no glyph_dispatch/**, no WGSL shaders, no other
kernel section in baker.py.

GATES — run each and paste the literal last lines:
  /usr/bin/python3 -m pytest tests/test_gh9_window_span.py -q
  /usr/bin/python3 -m pytest tests/test_bk1_argv.py -q
  /usr/bin/python3 -m pytest tests/test_bk11_coreutils.py -q
  /usr/bin/python3 -m pytest tests/test_gh9_loader.py -q
Success = the first three fully green (7/7, 5/5, 6/6) and no regression in the
fourth. Use /usr/bin/python3 (the system 3.12), NOT bare python3.

STOP AND REPORT (do not improvise, do not guess) if:
- the invariant cannot be met without moving BOX0 or the loader ABI words
  (703 / 732 / 750-766) — that is a design call for Jericho;
- meeting it would require editing a test's bake constants;
- a landed gate outside the four named above goes red and you cannot attribute
  it to this change.

DO NOT COMMIT. Leave the changes in the working tree and end with a DIFF SUMMARY
(files changed, exact commands, literal tail of each output, and anything you
could not verify).
