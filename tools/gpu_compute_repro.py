#!/usr/bin/env python3
"""
Standalone repro for GPU compute submission hang in sandboxed agent environments.

Run this outside the Claude Code sandbox (real host shell, real desktop session)
to confirm whether GPU compute actually works once the dual-GPU adapter-selection
hang (see GPU_CPU_BENCHMARK_RESULTS.md / session notes) is fixed.

What this script does, in order, printing after each step so a hang is easy to
localize:
  1. request_adapter_sync()   -- previously hung forever picking NVIDIA node
  2. request_device_sync()
  3. create_buffer_with_data() -- currently hangs here in the agent sandbox
  4. create_shader_module() / pipeline / dispatch / read_buffer()

If step 1-2 print but step 3 never does, you've reproduced the same
DRM-ioctl-submission stall found in the agent sandbox (fd stuck in a spinning
ioctl loop per strace, likely a cgroup/container device-access restriction
that allows opening /dev/dri/render* but not real command submission).
If step 3 onward print and RESULT shows [0. 2. 4. 6. 8. 10. 12. 14.], GPU
compute is fully working in that environment.
"""

import os

# Dual-GPU (Intel + NVIDIA) sandboxes: Vulkan mesa device-select can pick the
# NVIDIA render node and spin forever waiting on a fence that never signals.
# Forcing GL + the Intel iris driver avoids that hang.
os.environ.setdefault("WGPU_BACKEND", "gl")
os.environ.setdefault("MESA_LOADER_DRIVER_OVERRIDE", "iris")

import numpy as np
import wgpu


def main():
    print("[1] request_adapter_sync()...", flush=True)
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    print("    OK:", adapter, flush=True)

    print("[2] request_device_sync()...", flush=True)
    device = adapter.request_device_sync()
    print("    OK:", device, flush=True)

    print("[3] create_buffer_with_data()...", flush=True)
    n = 8
    data = np.arange(n, dtype=np.float32)
    buf = device.create_buffer_with_data(
        data=data.tobytes(),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST,
    )
    print("    OK:", buf, flush=True)

    print("[4] shader + pipeline + dispatch...", flush=True)
    shader = device.create_shader_module(code="""
        @group(0) @binding(0) var<storage, read_write> data: array<f32>;
        @compute @workgroup_size(1)
        fn main(@builtin(global_invocation_id) id: vec3<u32>) {
            data[id.x] = data[id.x] * 2.0;
        }
    """)
    bgl = device.create_bind_group_layout(entries=[{
        "binding": 0,
        "visibility": wgpu.ShaderStage.COMPUTE,
        "buffer": {"type": wgpu.BufferBindingType.storage},
    }])
    bg = device.create_bind_group(layout=bgl, entries=[{
        "binding": 0,
        "resource": {"buffer": buf, "offset": 0, "size": buf.size},
    }])
    pl = device.create_pipeline_layout(bind_group_layouts=[bgl])
    pipeline = device.create_compute_pipeline(layout=pl, compute={"module": shader, "entry_point": "main"})

    enc = device.create_command_encoder()
    pass_ = enc.begin_compute_pass()
    pass_.set_pipeline(pipeline)
    pass_.set_bind_group(0, bg, [], 0, 0)
    pass_.dispatch_workgroups(n)
    pass_.end()
    device.queue.submit([enc.finish()])
    print("    submitted", flush=True)

    print("[5] read_buffer()...", flush=True)
    out = device.queue.read_buffer(buf)
    result = np.frombuffer(out, dtype=np.float32)
    print("    RESULT:", result, flush=True)

    expected = data * 2.0
    if np.allclose(result, expected):
        print("\nPASS: GPU compute executed correctly.")
    else:
        print(f"\nFAIL: expected {expected}, got {result}")


if __name__ == "__main__":
    main()
