# GPU Adapter Hang — Root Cause and Fix (2026-08-16)

## Symptom

Any wgpu-python script (`tools/wgsl_glyph_*.py`, `tools/hilbert_gpu_bench_full.py`,
`pyshaderos/verify.py`) would print:

```
Unable to find extension: VK_EXT_physical_device_drm
```

and then hang indefinitely with no further output. Previously assumed to be a hard
sandbox limitation ("no GPU-native boot possible here").

## Actual root cause

`VK_EXT_physical_device_drm` is a harmless warning — wgpu falls back fine. The real
hang is that this machine has **two GPUs** (Intel iGPU + NVIDIA discrete):

```
/dev/dri/renderD128 -> Intel  (pci 0000:00:02.0, vendor 0x8086)
/dev/dri/renderD129 -> NVIDIA (pci 0000:02:00.0, vendor 0x10de)
```

Default Vulkan/mesa device selection picks the NVIDIA node. In this environment the
NVIDIA node's fence-wait never signals, so `request_adapter_sync()` spins forever in
a busy ioctl loop (confirmed via `strace -f -e trace=ioctl`, saw an identical
`ioctl(4, ...)` repeated thousands of times with no progress).

## Fix

Force GL backend + Intel iris driver before importing `wgpu`:

```python
import os
os.environ.setdefault("WGPU_BACKEND", "gl")
os.environ.setdefault("MESA_LOADER_DRIVER_OVERRIDE", "iris")
import wgpu
```

Applied (as `os.environ.setdefault`, so callers can still override) to:
- `tools/hilbert_gpu_bench_full.py`
- `tools/wgsl_glyph_minimal.py`
- `tools/wgsl_glyph_full_execute.py`
- `pyshaderos/verify.py`

With this fix, `request_adapter_sync()` / `request_device_sync()` now return
immediately instead of hanging. Verified live via `pyshaderos/verify.py`, which now
reaches `✅ GPU adapter found` and proceeds to runtime creation.

## What is NOT fixed

Real GPU **compute submission** still hangs in this agent sandbox — confirmed it
stalls before `create_buffer_with_data()` even returns (no "buf created" print),
i.e. before any shader runs. strace shows the same busy-ioctl pattern, now against
the Intel node instead of NVIDIA.

This looks like a container/sandbox restriction: `/dev/dri/render*` can be opened
(device nodes are accessible), but real DRM command submission never completes —
consistent with a sandbox that grants device-node access without full GPU
scheduling/DRM-master privileges.

This is **not** fixable with an env var. It needs to be tested outside the agent
sandbox (real host shell, real desktop session) to know whether GPU compute
actually works once you're off the constrained execution path.

## How to re-test outside the sandbox

Run:

```bash
python3 tools/gpu_compute_repro.py
```

- If it prints through `[5] read_buffer()` and `PASS: GPU compute executed
  correctly.`, GPU compute is fully working — go ahead and re-attempt the
  GPU-native OS boot (`boot_xv6_gpu.py` / WGSL glyph engine execution).
- If it hangs at step `[3] create_buffer_with_data()...` with no further output,
  the same submission-level restriction as the agent sandbox is present in that
  environment too, and the blocker is elsewhere (driver/container config, not this
  fix).
