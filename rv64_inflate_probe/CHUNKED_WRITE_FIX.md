# Chunked write sync fence — hypothesis RULED OUT (2026-08-26)

This document previously claimed the initrd/kernel corruption was caused by a
missing synchronization fence after the chunked compute-shader write path in
`write_mem_bytes()`. That hypothesis is **wrong**.

## Evidence against it

1. The 40M-step dump (pre-fix layout) showed the chunked-written initrd 99.97%
   correct (only the OpenSBI FDT copy footprint at +0x200000 differed). A
   load-time write race would corrupt from the start and stay constant; the
   corruption actually grew during boot.
2. `queue.read_buffer()` is a queue operation, ordered after previously submitted
   commands on the same queue — no fence is needed for the dump to see completed
   compute work.
3. The real cause is OpenSBI relocating its FDT copy to 0x82200000, inside the
   initrd range (see CORRUPTION_FIX_SPEC.md). The 0xCC was `POISON_FREE_INITMEM`
   from `free_initrd_mem()` after the resulting "broken padding" failure.

## Actions taken

- Reverted the `len(words) < 0xFFFFFFFF` force-small-write workaround in
  `tools/spatial_rv64i_cpu.py` (back to `16384` / 64KB threshold).
- The chunked path still has no explicit fence after `queue.submit([...])`; this
  is fine for queue-ordered readbacks and was never the bug. If it is ever
  touched again, prefer an explicit `queue.on_submitted_work_done()` only if a
  cross-queue or map_async readback path is introduced.
