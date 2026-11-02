# Speed-Up Receipt — adapter gate, snapshot resume, timebase gate
Date: 2026-11-02. All numbers measured on this machine (iGPU: Intel "skylake
derivative / mesa i915"; discrete: RTX 5090). Emulator: `tools/spatial_rv64i_cpu.py`
(WGSL `SPATIAL_RV64I.wgsl`), shell blob `/tmp/h12/alpine_shell.lnx.bin` via
`tools/build_gpu_shell_blob.py`.

## Question
"how could we speed up the boot process and system? can the state be cached
since it is an image?"

## Finding 1 — the default adapter was the iGPU
- Root cause: `SpatialRV64ICore.__init__` used `wgpu.utils.get_default_device()`,
  which resolves to the iGPU (the boot banner's "Detected skylake derivative
  running on mesa i915" was this, not a guest problem).
- Fix: `GPU_POWER=high` env gate requests `power_preference="high-performance"`
  (the 5090). Default behavior unchanged; frozen paths never set the var.
- Measured: ~250k steps/s (iGPU) vs ~415k steps/s (5090) — only ~1.7x. The
  workload is dispatch-latency-bound (small per-hart work, launch+sync per
  slice), not throughput-bound. More GPU does NOT proportionally speed this up.

## Finding 2 — cross-adapter determinism (hash gate)
- `GPU_POWER=high ./hackathon/demo/freeze/E2E.sh` on the 5090:
  - decode md5 `3292333c9470c37fbf4960b07dbeea79` (identical)
  - serial sha256 `c94026581a174c3118df1ec65fec20fb7d289cfbd2f33d3d33f930c22c717219`
    (identical to iGPU freeze), 8,375 bytes, boot rc 0, 82.8s wall (iGPU run: 82.1s)
- The integer/fixed-point shader is bit-exact across adapters. Claim made only
  after the gate passed, not assumed.

## Finding 3 — the machine is an image, so it snapshots (the big win)
- The entire machine is six GPU buffers: 64MB memory surface, registers
  (256B), state (184B: PC/halted/UART cursors), CSRs, TLB, UART ring.
- `tools/gpu_shell_live.py` gained `--save-snapshot` (dumps all six to one
  compressed .npz when the prompt is first reached) and `--snapshot`
  (writes them back, rebuilds the linear shadow, marks all ranges dirty for
  re-decode, resyncs the UART cursor).
- Gotcha found by testing: a resumed guest is blocked in `read`; its prompt
  bytes were consumed *before* the snapshot. Fix: seed the parser buffer with
  the prompt on resume (`buf = PROMPT`).
- Measured: full boot 68 min -> snapshot 18,555,533 bytes -> resume + `ls /` +
  `cat note.txt` ("hello GPU") in 124s wall / 50.9M steps, rc 0.
- `hackathon/demo/BOOT_LINUX.sh` now: first run boots+saves; later runs resume.
- Poetry, but also literally true: the largest buffer is the Hilbert memory
  surface — the machine saved as a picture of itself.

## Finding 4 — guest-clock timebase (implemented; sweep in flight)
- Mechanism: mtime advances ~1 tick per retired instruction (shader, ±8 jitter,
  1:1 average); DTB declares `timebase-frequency`. Every guest busy-wait
  (mdelay, udev sleep, probe timeout) is instruction-burned: 1 guest-second
  = 10M instructions at the default 10MHz.
- Hazard (flagged by the auditor analysis, adopted): timer ISR duty cycle grows
  as timebase/HZ shrinks — a blind 1MHz cut risks scheduler starvation. Sweet
  spot ~2.5–3MHz.
- Fix: `RISCV_TIMEBASE_HZ` env in `boot_alpine_gpu_fixed.py:load()`, default
  10000000 — frozen E2E hash path untouched (verified above with the default).
- Measured 3MHz sweep (2026-11-02, blob identical, same 5090):
  - Boot-to-prompt: **1,185,000,000 steps** (snapshot
    `shell_prompt_snapshot_3mhz.npz`). 10MHz baseline: ~1.69B steps
    (68 min x ~415k steps/s — estimate; the 10MHz run had no step counter
    in its log).
  - Net: ~30% fewer instructions, NOT the naive 3.3x. The timer-ISR duty
    cycle dominates: at 3MHz the tick fires every ~3k instructions, and the
    kernel-time counter ran to 370 guest-seconds before `/init` (vs 94.5s at
    10MHz) — guest time inflated because ISRs and scheduler overhead consume
    real instructions. The auditor's ISR-hazard model was directionally right;
    the naive "10x overclock" was wrong.
  - Wall-time caveat: the 3MHz run (4,821s wall) shared the GPU with the
    resume test + E2E hash gate, so 246k steps/s here is contaminated; steps
    are the clean metric.
- Conclusion: timebase tuning is a ~30% first-boot lever with a real hazard
  floor (~2MHz risks scheduler starvation). Not worth further sweep points
  pre-deadline. The snapshot resume (68 min -> ~2 min) remains the headline.

## Honest limits
- The snapshot is per-blob-state: it resumes the exact machine that was saved
  (same kernel/init). A new blob invalidates it (delete the .npz).
- The 68-min first boot is not yet fixed by the adapter (1.7x only); the
  timebase gate is the intended first-boot lever. Longer term: raise
  MAX_STEPS_PER_DISPATCH, `quiet` bootargs, warm-boot entry past OpenSBI,
  and multicore shader with per-hart workgroups (which the multi-user goal
  needs anyway — same wall time for N users is the density argument).
