# Autonomous loop: get Alpine to a shell on the GPU RV64 emulator

**Done =** a `boot_alpine_v618_gpu.py --offload` run (fresh) reaches an interactive
shell prompt or `login:` in its UART log. Stop the loop then.

## Standing facts
- 2 fixes landed: `2579bde` (SUM/MXR trap preservation), `bc4e316` (page-straddling fetch).
- Resuming `.ckpt/v618_preexec.rv64ckpt` runs real Alpine userspace init.
- Fresh boot breaks in `percpu:`->`SLUB:` window; batch-dependent:
  5M wedge (GPU hangcheck), 50k Oops in queued_spin_lock_slowpath
  (`ffffffff01c6b7a0` = valid `...81c6b7a0` w/ bit31 of low word cleared),
  2k stall right after `SLUB:`.
- From `v618_preexec`, Alpine init hangs at `nlplug-findfs` (netlink uevent).

## Iteration plan (work top-down; each wake: check running job, then next step)

### Phase 1 — fix fresh boot through percpu->SLUB
1. [in progress] Is the batch=50k Oops deterministic? Run `fresh_boot_ckpt.py
   --batch 50000` twice (`.work/fresh50k_run1.log`, `run2`). Same pc/backtrace
   at the STOP MARKER => real instruction bug, not jitter.
2. If deterministic: from `.ckpt/fresh_pre_percpu_50k.rv64ckpt` resume at
   batch=50000 (SAME batch, to keep jitter identical) and single-step /
   small-batch into the Oops. Capture the instruction that yields `0x01c6b7a0`
   instead of `0x81c6b7a0` (bit-31 low-word). Likely a sign-extension / RVC /
   shift bug in the shader decode. Fix, re-test.
3. If NOT deterministic (jitter-sensitive): make the mtime jitter batch-
   independent — persist `mtime_jitter_lcg`/`mtime_jitter_acc` in the `state`
   buffer instead of `var<private>` (needs struct + Python serializer bump;
   check rv64i_checkpoint FORMAT_VERSION). Then pick one batch (e.g. 200k) and
   verify fresh boot clears percpu->SLUB->Run /init.
4. Also try: batch 200k / 500k / 1M fresh — find any that clears the region
   AND stays under the GPU hangcheck. Quick wins before deep debugging.

### Phase 2 — Route B full boot
5. `boot_alpine_v618_gpu.py --offload --disk boot_images/alpine-standard-3.24.1-riscv64.iso`
   (fallback `/tmp/alpine_rootfs/alpine_disk.img`). Watch virtio_blk negotiate,
   root mount, switch_root, shell/login. Use the working batch from Phase 1
   (may need to thread it through `run_with_offload` slice_steps).

### Phase 3 — if nlplug-findfs still hangs with offload
6. Debug uevent/netlink delivery: likely kernel workqueue/softirq not scheduled
   due to tick timing. Check mtime rate vs real (Sstc stimecmp path), verify
   timer IRQ cadence in userspace. Or add `nlplug`-skipping bootarg if Alpine
   supports one.

## Log
- 2026-08-30: loop started. Phase 1 step 1 running.
- 2026-08-30 16:35: GPU env degraded — other non-mine python3 GPU procs (1327637,1330044) + ollama 5GB VRAM. Fresh boots crawling (~17k steps/s vs ~1M earlier). run1 killed (stuck at OpenSBI banner). run1b launched, monitoring. Loop backing off to 25min intervals until GPU clears.
- 16:40: contention source identified — peer running 'tools/boot_xv6_gpu.py' (pid 1330044) on same GPU. My run1b crawling at ~13.5k steps/s. Letting run1b grind toward the 'Ticket spinlock' checkpoint (~100M steps, ~2h at this rate); loop backing off to 40min. Rate should recover if the xv6 run finishes.

- 17:00: Oops did NOT reproduce from checkpoint (dispatch-phase realigns on resume)
  => root cause = var<private> mtime jitter resetting per dispatch. Fixed:
  persist mtime_jitter_lcg/acc in CSR slots 0x9C0/0x9C1 (commit). Fresh batch=200k
  boot test launched (.work/fresh200k_jitfix.log, stop at "Run /init"). If it
  reaches Run /init -> fresh boot fixed -> Phase 2 (Route B --offload + ISO).

- 17:15: jitter-persist fix did NOT cure fresh boot. batch=200k now DEADLOCKS
  in queued_spin_lock_slowpath at pc 0xffffffff808a4aa2 right after 'percpu:'
  (spins ~23M+ instrs then idles). Same pc across batches now => deterministic.
  Root cause is a real emulator bug: uncontended console_sem.lock enters the
  qspinlock slowpath at the setup_per_cpu_areas transition (lost cmpxchg /
  per-cpu ptr / lock-word corruption). QEMU is fine here.
  NEXT: capture .ckpt/fresh_pre_percpu_jit.rv64ckpt (new shader, jitter in CSR
  => resume is now deterministic), then single-step from it into pc 808a4aa2 to
  find which store/SC/AMO corrupts the lock word or which per-cpu ptr is wrong.

- 17:35: trace_qspin_deadlock.py phase1 failed to see 'percpu: Embedded' in 30M
  steps from .ckpt/fresh_pre_percpu_jit.rv64ckpt, lock VA guess didn't translate.
  Fell back to: resume the checkpoint plainly (run_preexec_forward, batch=20k),
  see where UART stops + final pc. Need real lock addr from regs at the
  deadlock pc before watching memory.

- 17:50: BREAKTHROUGH on diagnosis. Resuming .ckpt/fresh_pre_percpu_jit.rv64ckpt
  does NOT deadlock — sails through percpu/SLUB/RCU/SMP to 'workingset:' (191M
  steps), then a benign UART stall. So the deadlock only occurs on a CONTINUOUS
  fresh boot => caused by un-checkpointed GPU state. The software TLB (binding 7)
  is NOT saved by save_checkpoint. Hypothesis: stale TLB entry during the
  setup_per_cpu_areas remap -> wrong PA for the lock word -> qspinlock slowpath.
  EXPERIMENT: TLB_LOOKUP_DISABLED=true in shader, fresh batch=200k boot
  (.work/fresh_notlb.log). If it reaches Run /init -> TLB is the bug.

- 18:05: TLB disabled did NOT fix the deadlock (reverted flag to false).
  Found MAX_STEPS_PER_DISPATCH=100k in step(). decoded_ops_epoch is var<private>
  (resets per dispatch, bumped by first sfence.vma/satp write) => whether an
  instr uses the pre-decoded fast path vs decode_and_execute() depends on host
  dispatch alignment. If execute_decoded() differs from decode_and_execute() for
  some op (AMO/LR-SC?), that's the fresh-vs-resume divergence.
  EXPERIMENT #2: DECODED_FASTPATH_DISABLED=true, fresh batch=100k boot
  (.work/fresh_nofast.log). Reaches Run /init => fast path has the bug.

- 18:12: DECODED_FASTPATH_DISABLED=true -> fresh batch=100k boot CLEARS the
  0x808a4aa2 deadlock, reaches workingset:/71M steps and climbing toward
  Run /init (.work/fresh_nofast.log). So execute_decoded() has an op bug
  (SLLW/SLLIW/AMO/LR-SC region suspected) vs decode_and_execute(). Accepting
  the fast-path disable as the fix (perf cost; TODO diff the two paths later).
  alpine_disk.img is a custom "ALPINE_DISK_V1" container, NOT a real fs.
  Phase 2 revised: skip Route B disk hunt — fresh boot with --initrd
  .ckpt/bbird.gz (static ET_EXEC busybox) -> /bin/sh on console = the shell.
  Do that once fresh_nofast confirms Run /init.

- 18:20: fresh_nofast cleared the deadlock but now sits at pc ~0xffffffff8006613e
  right AFTER 'workingset:' for 180M+ steps, no UART. The earlier resume_jit_ckpt
  run (also NEW shader) stalled at the SAME pc 0x8006613e. Runs that reached
  Alpine Init used the OLD shader (pre jitter-persist, pre fast-path-disable).
  => one of the two recent changes regressed the boot at the post-workingset
  point. Suspect jitter-persist (CSR 0x9C0/0x9C1) breaking mtime advance ->
  timer-dependent wait (crng/calibration/RCU) hangs.
  NEXT: if fresh_nofast still stuck after ~300M more steps, revert jitter-persist
  (keep fast-path-disable), retest fresh boot. If that regressed it, the fix for
  the deadlock is fast-path-disable ALONE.

- 18:30: reverted jitter-persist (commit) — it regressed the post-workingset
  wait. Kept DECODED_FASTPATH_DISABLED=true. Testing fresh batch=100k boot
  (.work/fresh_fpd_only.log). Expected: clears deadlock AND reaches Run /init.
  If it stalls post-workingset again -> fast-path-disable itself regressed the
  boot; need to find the actual execute_decoded op bug instead of disabling.

- 18:35: fast-path-disable + jitter-reverted: fresh boot clears deadlock,
  reaches workingset:, then 260M+ steps of silent execution (pc roaming many
  regions incl revisits — ambiguous slow-vs-hang). No fresh boot has EVER
  cleared percpu->workingset->RunInit this session.
  Running fresh_ws_ckpt: fresh boot (current shader) checkpointing at
  'workingset:' -> .ckpt/fresh_workingset_fpd.rv64ckpt, continues. Gives a
  clean post-danger-band checkpoint to resume-test fast, and shows if the
  fresh boot itself reaches Run /init given enough time.

- 18:45: resume of CLEAN workingset checkpoint (fast-path OFF) ALSO stalled
  silent post-workingset (uart=0B, 303M steps, pc 0x8033b848). So it's NOT
  fresh-boot state corruption. Testing: resume same checkpoint with fast-path
  RE-ENABLED (.work/resume_ws_fpon.log). If it clears post-workingset ->
  DECODED_FASTPATH_DISABLED regressed post-workingset (decode_and_execute has a
  latent bug the fast path was hiding) -> must fix the real execute_decoded op
  bug, not disable. If it also stalls -> the checkpoint or the shader state is
  bad; step back to old-shader baseline + re-derive.

- 19:05: resume with fast-path RE-ENABLED ALSO stalled post-workingset (uart=0B).
  So NEITHER flag caused it. git diff vs bc4e316 (SUM+cross-page) = only dead
  if(false) blocks + unused consts => current shader ≡ bc4e316 functionally.
  Yet bc4e316 reached Alpine Init from v618_preexec earlier today.
  => .ckpt/fresh_workingset_fpd.rv64ckpt has CORRUPT state: the percpu-band bug
  (0x808a4aa2) still corrupts guest RAM even with fast-path off (bug is in a
  shared path / decode_and_execute, not just execute_decoded).
  TEST: resume known-good .ckpt/v618_preexec.rv64ckpt with CURRENT shader
  (.work/preexec_curshader.log). Reaches Alpine Init => current shader is fine
  post-percpu; fresh boots just can't be trusted through the percpu band ->
  must find the real bug. Stalls => SUM or cross-page regressed something ->
  bisect those two.

- 19:20: CONFIRMED current shader is FINE post-percpu — resuming known-good
  v618_preexec reaches Alpine Init -> Mounting boot media -> nlplug-findfs hang
  (the pre-existing netlink/musl blocker). So post-workingset stalls come from
  CORRUPT state that fresh boots bake in crossing the percpu band.
  Two blockers now: (1) fresh-boot percpu-band corruption [jitter-timing,
  shared code path], (2) nlplug-findfs hang from any full Alpine userspace.
  bbird.gz sidesteps (2): static busybox /init -> 'exec /bin/busybox sh',
  no musl/nlplug/netlink. Trying fresh boot --initrd .ckpt/bbird.gz batch=100k
  fast-path-off (.work/bbird_fresh.log), stop at "BUSYBOX SHELL RUNNING".
  Tiny initrd may shift timing past the percpu bug; if it reaches Run /init
  the shell comes within ~20-50M steps (no big unpack/squashfs/alpine-init).

- 19:40: bbird fresh boot (fast-path off) hit the SAME post-workingset stall
  (pc cycling 0x80054/0x80086/0x8033b, silent) — tiny initrd did NOT dodge it.
  No System.map for 6.18.35-lts to name 0x8033b. Retest: BOTH TLB_LOOKUP_DISABLED
  and DECODED_FASTPATH_DISABLED true, bbird fresh (.work/bbird_notlb_nofast.log).
  If it reaches the shell -> TLB+fastpath together. If still stalls -> genuine
  shared-path bug; next: single-step the 0x8033b loop from a fresh workingset
  ckpt to see what it polls, or accept fresh-boot as unsolved this session and
  document (checkpoint path DOES reach userspace; nlplug hang is the userspace
  blocker).

- 19:46: trace_ws_stall "never settled into stall band" in 400M steps — pc NOT
  tightly looping in a small set; executing broadly with no UART. Reconsidering:
  maybe it's NOT a stall, just a very long silent stretch (crypto selftests)
  that the 500s-no-UART detector cut short. GPU now uncontended => test with
  patience: run_preexec_forward from fresh_workingset_fpd, 4B steps, 1200s stall
  window (.work/ws_patient.log). If it eventually prints Run /init / more lines
  => fresh boot just needs time+free GPU, no corruption bug. If truly stuck at
  ~300-600M steps with 0 new UART => real hang, characterise differently.

- 19:55: *** post-workingset "stall" was a MISDIAGNOSIS ***. Patient run on free
  GPU produced: PF_ALG, x509, bsg driver, riscv-plic — it was just a long silent
  stretch, cut short by the 500s-no-UART detector while the peer xv6 job slowed
  the GPU 50-100x. NO percpu-band corruption bug. Fresh boot post-workingset is
  fine, just slow.
  => Only real fresh-boot fix needed = DECODED_FASTPATH_DISABLED (0x808a4aa2).
  Launched fresh bbird.gz boot batch=200k on the free GPU (.work/bbird_freegpu.log),
  stop at "BUSYBOX SHELL RUNNING". Expect: shell. If reached -> STOP LOOP, document.
  TODO after: re-enable fast path + find the real execute_decoded op bug (perf),
  and the nlplug-findfs hang for full Alpine (separate).

- 20:12: bbird_freegpu progressing (reached "Freeing initrd memory: 864K" guest
  19.4s) but throughput COLLAPSED to ~45k steps/s in the 0x8033b region (13x
  slower than 615k baseline). Likely genuine crypto-selftest density (AES/SHA
  S-box loads) through decode_and_execute (fast path off). Not deadlocked -
  UART advancing, guest time moving. Letting it grind to Run /init + the
  busybox banner. AMO paths decode_and_execute vs amo_common look equivalent;
  possible rv64i_decode.py op.aux .w/.d bug but that only matters with fast
  path ON (deferred).
