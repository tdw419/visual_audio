ROADMAP ROW: BK-13 — "Mailbox net stack skeleton: SYS 18 = net_send / SYS 19 = net_recv frames
between two Glyph OS instances, BOTH KERNELS INSIDE ONE IMAGE."

RULING ALREADY MADE (do not re-litigate; `.builder_queue/RULING_20260912_defect19_bk13_worktree.md` §2):
  - Q1 syscall numbers: SYS 18 = net_send, SYS 19 = net_recv. SYS 6/7/8 = GH-22, 9/10/11 = BK-3,
    12/13 = BK-4, 14 = BK-9, 16/17 = BK-10. 18/19 are free and MUST be used.
  - Q2 instance boundary: TWO KERNELS INSIDE ONE IMAGE exchanging frames through the REAL mailbox
    windows, with every frame crossing the admission oracle IN-SUBSTRATE. The host is the
    runner/observer, never the transport. Two GlyphRunner processes joined by a host pipe is the
    REJECTED design — do not implement it.

FILES IN SCOPE (this is the entire scope):
  - tools/glyph_gpt/net_stack.py   (NEW file — public entry point `net_stack_kernel_image()`)
  - tests/test_bk13_net.py         (NEW file — the gate)
Do NOT modify any other file. Specifically do NOT edit tools/glyph_gpt/baker.py (adding a re-export
would make this a core-file change and force worktree isolation — import the new module directly in
the test instead), do NOT edit tools/glyph_gpt/autoatlas.py, tools/glyph_gpt/gh22_driver_abi.py,
tools/glyph_gpt/fs_v2.py, or any existing test. If you conclude the gate cannot be met without
editing one of those, STOP and report the blocker with evidence.

MECHANISM TO REUSE (already landed — read these before writing code):
  - tools/glyph_gpt/gh22_driver_abi.py — the two-pass round-robin two-box bake, GH-22 word map:
    BOX0 [700..717), BOX1 [718..735), kernel-mediated mailbox word 754, read-outs 714/720,
    exit words 703/723, GH-22 framing `cksum = (op + payload) & 0xFF`. WIRING IS KERNEL-MEDIATED:
    a USER task never writes into another box (that trips E-K1 by design).
  - tools/glyph_gpt/autoatlas.py — `admit_syscall(runner, sys_n, contract=..., argv=...,
    expected=..., abi="gh18")` (proof = admission; a rejected tile returns `.table_word == 0` and
    leaves the table untouched, `E_ATLAS_UNVERIFIED`).
  - tools/glyph_gpt/baker.py `loader_kernel_image()` / `gh9_window_span_conflict` — the DEFECT-19
    lesson: any RAM span you copy into must be asserted NOT to overlap the box ABI words.

FRAME FORMAT (fix it in the module docstring; the gate asserts against it):
  64 bytes = 16 words. word 0 = header (low byte op, high byte len; len == 16 for a well-formed
  frame), words 1..15 = payload. The frame is copied word-by-word through the kernel-mediated
  mailbox (16 send/recv pairs) into a 16-word frame buffer at the LOW end of the receiving box's
  arena. Document the exact word indices you chose for both frame buffers in the module docstring.

GATE COMMAND (must be green from a clean run, CPU only, no network):
  cd /home/jericho/projects/zion/projects/visual_audio
  python3 -m pytest tests/test_bk13_net.py -q
Write it RED-first discipline style like the repo's other gates (tests/test_bk12_wgsl_tier.py,
tests/test_gh22_device_driver_abi.py): module docstring naming BK-13 + each leg's intent.

LEGS THE GATE MUST CONTAIN (all real assertions; no tautologies, no skips):

L1 — Bakes: `net_stack_kernel_image()` returns an image; assert shape/dtype and that BOTH instances'
     arenas and the mailbox window exist in the baked image; assert the chosen frame-buffer words
     do NOT overlap the box ABI words (positive no-overlap assertion, the DEFECT-19 lesson).

L2 — Byte-exact 64B frame transfer: ONE GlyphRunner instance drives ONE image (no second runner, no
     subprocess). Instance A fills a 16-word frame, sends it (SYS 18), instance B receives it
     (SYS 19); assert the 16 words read back from the RUNNER'S OWN MEMORY at B's frame buffer are
     byte-exact vs the source list, and that the run reaches a clean halt (no engine fault).

L3 — Admission-oracle leg: the SYS 18/19 tiles enter the image ONLY via `admit_syscall` (proof =
     admission) and their table words are lit; assert a tile whose proof fails is refused
     (`.table_word == 0`) and the table stays untouched, i.e. the same E_ATLAS_UNVERIFIED path
     the landed GH-18 machinery already enforces. Assert the refusal is receipted (a record
     written under tmp_path or output/ naming the frame/verdict/reason) and that the in-image
     table shows no slot for the refused tile.

L4 — Malformed frame rejected with a receipt: send a frame with a bad checksum / bad length; assert
     the frame is NOT delivered into B's frame buffer (buffer unchanged from its pre-send words)
     AND an in-image rejection verdict is observable (marker word) AND a receipt artifact exists
     recording the rejection reason. A malformed frame must be a clean rejection, never a fault
     that destabilises the kernel (mirror GH-22's `test_gh22_corrupted_packet_clean_fail`).

L5 — No host I/O path in the data movement: AST-scan tools/glyph_gpt/net_stack.py and assert it
     imports none of {socket, ssl, http, urllib, requests, subprocess, multiprocessing, threading,
     asyncio}. Assert the L2 transfer is driven through a single runner on a single image, so the
     frame provably moves in-substrate. (Parse with `ast`, not string grepping — see the
     zero-dev-import AST pattern already used in tests/test_gh1_standalone_image.py.)

HARD CONSTRAINTS:
  - Python 3.12, pytest, CPU only (no WGSL/GPU import in this gate).
  - No network, no writes outside tmp_path.
  - Reuse landed machinery; do not invent a new engine opcode or change the glyph ISA.
  - Keep it a SKELETON: 64B frames, two instances, one image. No retransmit, no windowing,
    no TCP-likeness beyond the four legs above.
  - Do NOT commit anything. Leave the changes in the working tree.

REPORT BACK (DIFF SUMMARY): the files you created, the exact command(s) you ran, and the literal
last lines of their output (pass/fail counts). If any leg needed an assumption, state it explicitly
rather than implying success. Also report the word indices you used for both frame buffers.
