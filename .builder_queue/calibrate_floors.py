"""R0 — real floor calibration for rate-regime validity (Jericho's
directive, 2026-09-21: "go build and run the real R0 verification").

This is the artifact RULING_ps009_fork_cleared_ps010_go CITED but which
never existed on disk. It exists now, and this commit carries it.

What it measures: the per-call round-trip FLOOR of each code path the
PS009b probe times, in a SEPARATE process, with NOTHING else in the
timed region. The floor of a path = the cost of its unavoidable
blocking round trips with zero work between them.

  floor(step):       one dispatch_workgroups + one blocking readback
                     (the adapter's own no-op work), measured as
                     median over many iterations
  floor(get_state):  one blocking readback only (map + read + unmap)
  floor(GEN dispatch+readback): identical to floor(step) — one submit,
                     one readback

Why: a timed leg whose implied per-round-trip cost is BELOW its own
path's floor is not reporting throughput — it is reporting an artifact
(timed region too small, timers misbracketed, caching across reps).
That is the exact defect the filed 6.15x carried (its host legs implied
285us/451us per blocking call; the true floor is ~3.5-4.2ms on this
host's adapter).

Output: floors.json (this directory) — {floor_us: {step, get_state},
adapter, device, measured_at, python}. The regime check (check #8)
validates receipts against THIS file, in a separate process, before
any ratio in a receipt is admissible.
"""
import json
import statistics
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, "/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, "/home/jericho/projects/zion/projects/visual_audio/tools")

REPS = 30
OUT = "/home/jericho/projects/zion/projects/visual_audio/.builder_queue/floors.json"


def measure(reps: int = REPS) -> dict:
    import struct

    import wgpu

    device_adapter = {}

    adapter = wgpu.gpu.request_adapter_sync()
    device = adapter.request_device_sync()
    device_adapter["adapter_summary"] = getattr(adapter, "summary",
                                                "unknown")

    # minimal pipeline: one workgroup that writes a constant
    wgsl = """
    @group(0) @binding(0) var<storage, read_write> buf: array<u32>;
    @compute @workgroup_size(1, 1, 1)
    fn main() { buf[0] = 42u; }
    """
    n = 4
    shader = device.create_shader_module(code=wgsl, label="floor-probe")
    gpu_buf = device.create_buffer(
        size=n * 4,
        usage=(wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC
               | wgpu.BufferUsage.COPY_DST))
    readback = device.create_buffer(
        size=n * 4,
        usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ)
    pipe = device.create_compute_pipeline(
        layout="auto", compute={"module": shader, "entry_point": "main"})
    bg = device.create_bind_group(
        layout=pipe.get_bind_group_layout(0),
        entries=[{"binding": 0,
                  "resource": {"buffer": gpu_buf, "offset": 0, "size": n * 4}}])

    # warm
    for _ in range(3):
        enc = device.create_command_encoder()
        cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe)
        cp.set_bind_group(0, bg)
        cp.dispatch_workgroups(1, 1, 1)
        cp.end()
        enc.copy_buffer_to_buffer(gpu_buf, 0, readback, 0, n * 4)
        device.queue.submit([enc.finish()])
        readback.map_sync(mode=wgpu.MapMode.READ)
        readback.read_mapped()
        readback.unmap()

    # floor(step): dispatch + blocking readback (one full round trip)
    step_floor = []
    for _ in range(reps):
        t0 = time.perf_counter()
        enc = device.create_command_encoder()
        cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe)
        cp.set_bind_group(0, bg)
        cp.dispatch_workgroups(1, 1, 1)
        cp.end()
        enc.copy_buffer_to_buffer(gpu_buf, 0, readback, 0, n * 4)
        device.queue.submit([enc.finish()])
        readback.map_sync(mode=wgpu.MapMode.READ)
        struct.unpack(f"<{n}I", bytes(readback.read_mapped()))
        readback.unmap()
        step_floor.append((time.perf_counter() - t0) * 1e6)

    # floor(get_state): blocking readback only
    gs_floor = []
    for _ in range(reps):
        t0 = time.perf_counter()
        readback.map_sync(mode=wgpu.MapMode.READ)
        struct.unpack(f"<{n}I", bytes(readback.read_mapped()))
        readback.unmap()
        gs_floor.append((time.perf_counter() - t0) * 1e6)

    return {
        "floor_us": {
            "step": round(statistics.median(step_floor), 1),
            "get_state": round(statistics.median(gs_floor), 1),
            "step_p10": round(sorted(step_floor)[reps // 10], 1),
            "step_p90": round(sorted(step_floor)[(9 * reps) // 10], 1),
        },
        "reps": reps,
        "adapter_summary": device_adapter["adapter_summary"],
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    result = measure()
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)
    print(f"floors written to {OUT}")
    print(f"  adapter: {result['adapter_summary']}")
    print(f"  step      floor: {result['floor_us']['step']:,.1f} us "
          f"(p10 {result['floor_us']['step_p10']:,.1f} / "
          f"p90 {result['floor_us']['step_p90']:,.1f})")
    print(f"  get_state floor: {result['floor_us']['get_state']:,.1f} us")
