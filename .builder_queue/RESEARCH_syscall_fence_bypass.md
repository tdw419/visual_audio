# RESEARCH — the SYSCALL layer is a fourth fence-bypass class: 0x02 READ,
# 0x04 FILE_READ, 0x13 FILE_LIST write any RAM word, 0x11 STORE_CODE writes
# any image pixel — all from a tiled USER task with a clean exit

**Tick:** 2026-09-27, Phase 1c research (builder af3e62239ce2)
**HEAD at measurement:** 802b6ac8 (tracked tree clean; probes untracked)
**Question:** BK-38 measured the LD read gap; BK-39 measured PARALLEL_LD/ST
+ PUSH/CALL and the BOX0 self-grant. That left one guest-reachable write
class unprobed: the syscall handlers, which copy host/kernel data into
`self.memory` with plain bounds checks. Can a confined task use them to
write outside its tile?

## Method

- Probe `.builder_queue/probe_syscall_fence_af3e.py` (untracked, landed
  modules only, zero tree mutation). Signal command:
  `GLYPH_FS_ALLOW=/tmp python3 .builder_queue/probe_syscall_fence_af3e.py`.
- Harness = the landed item-29 containment path itself:
  `GlyphProcessTable.spawn(tile=(5,0,8,8))` with the auto-armed reaper.
  Out-of-tile target = word 168 (row 5, col 8 — first word outside).
- Determinism: full stdout byte-identical across 3 external runs (md5
  cee48c7b5a5e328693361564b7b761f4, measured).
- Probe-hygiene disclosure — TWO draft defects caught on read-back before
  any finding was recorded:
  1. Draft 1 staged FILE_READ path bytes at word 300 via in-tile
     PARALLEL_ST. PARALLEL_ST's write-through pixel mirror
     (`glyph_isa_v2.py:1292-1295`) wrote image pixel 300 = instruction 75,
     corrupting the probe's own instruction stream mid-run — FILE_READ and
     STORE_CODE silently never executed, and the "not landed" results were
     meaningless. Fixed by staging at word 160 (mirror -> pixel 160 =
     instruction 40, past this <=30-instruction program).
  2. Draft 2's in-tile controls asserted "landed" via
     `''.strip()`-truthiness on a two-NUL byte string, which is truthy —
     the control could not fail. Replaced with hex != '0000' checks.
  3. Draft 3's out-of-tile target was 160+64=224 = row 7 col 0, INSIDE the
     (5,0,8,8) tile; the plain-ST control correctly landed there and so
     exposed the geometry error (the control MUST trap; it didn't).
  Draft-3's correction is itself a measured confirmation of the E-K1
  baseline: the same ST that trapped at word 164 in the BK-39 probe traps
  at word 168 here (fault_addr=672=168*4, mode->SUPER).

## Findings (measured, deterministic across 3 runs)

1. **0x02 READ — silent cross-fence write.** Tiled USER task: dest in
   r1=168, want=2 -> rc=EXIT_OK, faulted=False, mode stays USER,
   `memory[168] == 0x4B` ('K', first ring byte). Handler
   (`glyph_isa_v2.py:1426-1460`) writes `self.memory[addr + i]` with a
   bounds check only (`:1451`) — no mode check, no `_addr_in_box`.
   In-tile control lands normally ('K' at word 160).
2. **0x04 FILE_READ — silent cross-fence write + host-file read.** The
   confined task read `/tmp/b40` (6 bytes 'KFENCE') into word 168 —
   clean exit, `memory[168] == 0x4B`, in_hex at the staged-path word
   confirms the path staged correctly. Handler loop `:1544-1547` (and the
   VFS twin `:1526-1529`): bounds check only. Note this ALSO re-measures
   the host read surface: a task that cannot ST outside its tile can
   still exfiltrate any GLYPH_FS_ALLOW file byte into out-of-tile RAM.
3. **0x13 FILE_LIST — silent cross-fence write.** Listing of `/tmp`
   landed at word 168 (first entry byte '.'): clean exit,
   `memory[168] == 0x2E`. Handler loops `:1796-1800` (host) and
   `:1770-1774` (VFS): bounds check only.
4. **0x11 STORE_CODE — silent image-plane write.** The task copied image
   pixel 200 -> pixel 168 (out-of-tile): clean exit, pixel at linear 168
   changed from (0,0,0) to (65,66,67) ('ABC'). Handler `:1689-1701` does
   `_mem_read`/`_mem_write` pairs — `_mem_write` (`:702-708`) has no box
   consult (same root as BK-39's PUSH/CALL legs). Blast radius:
   instruction-stream corruption class (pixels are the fetch truth,
   GH-8b), same caveat as BK-39 leg 4.
5. **Controls all green:** plain ST to word 168 traps (rc=EXIT_FAULT,
   fault_addr=672, mode->SUPER — the E-K1 baseline); 0x02 in-tile lands
   ('K' at 160); 0x04 in-tile lands (dest word 176 non-zero). The fence
   itself works; the syscall arms simply never ask it.
6. **Structural root cause (read, path:line):** `_addr_in_box`
   (`glyph_isa_v2.py:720-747`) is consulted at exactly ONE execute site —
   the ST arm (`:1041`) — unchanged since BK-38/39 measured it. The
   syscall DATA handlers (`:1426-1460` READ, `:1506-1552` FILE_READ,
   `:1770-1800` FILE_LIST) and STORE_CODE (`:1689-1701`) are four more
   unguarded write arms on the same executable path, reachable from USER
   mode whenever `KSYS_PC == 0` (the default for item-26/29 spawns —
   `spawn()` never arms KSYS_PC, so `ksys` is 0 and the direct
   `_handle_syscall` branch at `:1157-1158` runs).
7. **Why it matters:** with BK-38/39 this closes the write-arm map. Every
   guest-reachable path that lands data in RAM/image is now measured as
   fence-blind except ST: LD (read), PARALLEL_LD (read), PARALLEL_ST
   (write + self-grant), PUSH/CALL (image), READ/FILE_READ/FILE_LIST
   (write), STORE_CODE (image). The containment story at
   `tools/glyph_process.py:122-123` ("the engine's existing box check
   then traps any out-of-tile user store") is accurate ONLY for the ST
   opcode. Combined with BK-39's BOX0 self-grant, a confined task's
   effective capability set is: read all RAM, write all RAM, rewrite its
   own fence, and patch the instruction stream.
8. **Prior art:** BK-38/39 receipts named the opcode arms; none probed
   the syscall layer. XV6_NANO's E-K2 (KSYS_PC armed) redirects syscalls
   to a kernel dispatcher — the mitigation exists but is NOT armed on the
   process-table path this lane's containment is built on. WGSL twin NOT
   probed on-device (no wgpu leg); by source read the syscall handlers
   are Python-only (no `_OPCODE_ORDER` surface), so the twin is not
   exposed by this class.

## Numbers policy (rule 6)

All cited numbers are structural (word values, byte values, exit codes,
fault_addr, line numbers, pixel tuples, an md5 of probe stdout) — no
rates, latencies, or ratios, so rule-1 floors do not attach. Re-derive in
one command each:
`GLYPH_FS_ALLOW=/tmp python3 .builder_queue/probe_syscall_fence_af3e.py`;
`grep -n "_addr_in_box" tools/glyph_isa_v2.py` -> 2 hits (:720 def,
:1041 sole call site); `grep -n "self.memory\[addr + i\] = byte_val"
tools/glyph_isa_v2.py` -> the handler copy loops.

## Candidate backlog item (BK-40, filed to systems/GLYPH_BACKLOG.md)

Fence the syscall DATA write arms: route the four handler copy loops
(0x02/0x04/0x13 RAM, 0x11 image) through the same USER+tile consult as
ST — out-of-tile dest bytes are dropped (or the syscall faults; one
posture, documented) — OR, cheaper and stronger: arm KSYS_PC by default
on tiled spawns so syscalls vector to a kernel dispatcher (E-K2) instead
of executing user-selected handlers. Gate `tests/test_bk40_syscall_fence.py`
with RED-first legs per the backlog row. NOT landed by this receipt —
research proposes, never lands engine code.

## What this receipt does NOT prove

- No WGSL on-device run (twin claims are source-read only).
- No claim about 0x03 FILE_WRITE's EXFILTRATION side (guest RAM -> host
  file) — a confined task writing out-of-VFS files is a different
  surface, unprobed this tick.
- No claim that STORE_CODE's RAM-grid blast radius extends beyond the
  image plane (same caveat as BK-39 leg 4).
- The 0x04 leg ran under GLYPH_FS_ALLOW=/tmp with the probe (host) writing
  the fixture file; the guest only read it.
- KSYS_PC-armed posture NOT probed (would require a kernel dispatcher
  image; the mitigation's existence is cited from the XV6_NANO roadmap
  path, its efficacy on this exact spawn path is unmeasured).
