BK-6 RED RECEIPT — engine LD out-of-RAM silent no-op (ENG-3)
=============================================================
Date: 2026-09-11 (builder cron af3e62239ce2, BK-6 gate bring-up)

SYMPTOM
tests/test_bk6_integrity.py clean-image leg: verdict word 901 stays 0;
kernel reaches :__kbad (r14 = 0xbad006 at step 537) even though the
host-measured window sum EQUALS the baked constant (0x1a1f9ee6 == 0x1a1f9ee6).

TRACE (output/bk6_trace90.py, ram_words=8448, image 26x32=832 px words)
  step 11  pc (16,1) r5=8448 r7=0x0   <- LD r7 r5, addr 8448 >= 8448 RAM
  step 15  pc (0,2)  r5=8449 r7=0x0
  ...every wrapped LD leaves r7 == 0; r6 never accumulates (r6 nonzero count: 0)

ISOLATION (output/bk6_ldprobe.py)
  Manually set cpu.pc to the loop's `LD r7 r5`, r5 = 8448, single step:
    r7 after = 0x0
  Image pixel word at linear (8448 % 832) = 128 = 0xffa500.
  An out-of-RAM LD MUST read 0xffa500; it reads nothing (rd unchanged).

ROOT CAUSE
tools/glyph_isa_v2.py step() LD branch, unpaged path:
    elif 0 <= addr < len(self.memory):
        self.registers[rd] = self.memory[addr] & 0xFFFFFFFF
There is NO else. addr >= len(self.memory) falls through and rd silently
keeps its stale value — the exact ENG-1 silent-no-op class.

DIVERGENCE vs the engine's own read semantics:
  _addr_to_xy()   : "Linear-wrap: scalar address -> pixel coordinate"
  _mem_read()     : wraps EVERY addr onto image pixels (used by the paged
                    PTE_PIX fallback at line 670: self._mem_read(image, pix_word))
  walk_ld (WGSL twin context): BK-2 receipt already fixed walk_ld's unpaged
  branch for MMIO; the wrap-read path exists for paged reads but NOT for the
  unpaged out-of-RAM LD.

FIX (applied after this receipt)
Unpaged LD with addr >= len(self.memory) reads the linear-wrapped image
pixel word via _mem_read — matching _addr_to_xy's documented semantics and
the paged fallback — instead of silently dropping.

POST-FIX VERIFICATION (filled in after runs)
[gate + arc regression results appended below]
=============================================================
POST-FIX VERIFICATION (appended 2026-09-11, this run)
=============================================================

RED (pre-fix, output/bk6_gate_run1.txt):
  FAILED test_bk6_clean_image_verifies_and_dispatches  (verdict 0x0 — the
    silent out-of-RAM LD left r6 == 0, mismatch, kernel never verified)
  FAILED test_bk6_single_pixel_flip_faults_integrity_fail
  4 passed (nonvacuity legs — those check host-side sums, not the engine).

GREEN (post-fix, output/bk6_gate_run2_green.txt):
  6 passed in 0.09s — all gate legs incl. clean-image dispatch (work 903
  = 77) and single-pixel-flip INTEGRITY_FAIL (902 = 0xBAD006, task never
  ran).

FIX 1 — engine LD wrap (tools/glyph_isa_v2.py, ENG-3):
  Unpaged LD with addr >= len(memory) now reads the linear-wrapped image
  pixel word via _mem_read instead of silently keeping rd's stale value.
  Matches _addr_to_xy's documented linear-wrap semantics and the paged
  PTE_PIX fallback (line 670). Zero known-opcode semantics touched.

FIX 2 — kernel dispatch jump (tools/glyph_gpt/integrity.py, BUG-12):
  _jump_r30(a, 0) → _jump_r30(a, _BK6_TASK_PC). The literal 0 made the
  post-verdict KJMP reboot the kernel at :__entry WITH the latch already
  USER; re-entry's BOX0 arming store to MMIO word 8195 (byte 32780)
  faulted E-K1 on the CLEAN leg (receipt['fault_addr'] == 32780).

FIX 3 — tamper-pixel choice (tests/test_bk6_integrity.py, BUG-13):
  _tamper_in_window picked the FIRST nonzero window word = linear 128 =
  (0,4) = the :__kbad leg's OWN OR opcode pixel. Killing kbad means the
  INTEGRITY_FAIL store never executes; the engine died as opcode=None
  (silent, receipt['halted']=True, fault word 0). Now picks the LAST
  nonzero window word (linear 190 = instr 47, :__kgood const-block
  tail) — still inside the hashed window (sum moves) but the kbad leg
  at instrs 50+ survives to post the fault.

REGRESSIONS (post-fix):
  BK arc + paging/parity/FS core (bk1, bk2, bk3, bk4, bk6, gh4, gh7,
  gh8_fs, gh8c, gh15_step4, gh16, gh17, gh18, gh20, gh25):
    85 passed in 54.25s
  Shell/launcher/agents/stdlib/posix/driver/libc/bridge/resident
  (gh10, gh11, gh13, gh19, gh21, gh22, gh23, gh24, gh26_resident):
    77 passed in 8.18s
  Total arc: 162 passed, 0 failed.

NOTE (test collection): tests/test_gh26_glass_box.py errors at import
(mcp.server.fastmcp missing in this venv) — pre-existing environment
gap, unrelated to BK-6 (matches the MCP-suite py3.12 split noted in
ENG-1's receipt row).
