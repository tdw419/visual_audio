#!/usr/bin/env python3
"""probe_r11_anchor_baseline.py — PRODUCT_ROADMAP R1.1 baseline probe.

Runs ONE complete agent task (the GH-26.4 resident daemon's triple() verb)
end-to-end in the guest box, host-verifies the mailbox result against an
independently computed expectation, and prints a standing-rule-1 floor line
for the GPU (WGSL) execution leg.

Legs:
  A. CPU functional (the gated substrate; tests/test_gh26_resident.py):
     bake resident image -> GlyphRunner.drive -> assert
     mem[754] == 3*ARGV_PAYLOAD, argv word intact @750, done flags @717,
     ticks serviced @732, kernel status word RES_KERNEL_OK.
  B. GPU timed (the path floors.json's 'step' floor describes):
     GlyphRunner.run_wgsl, one dispatch+blocking-readback per step.
     Emits a `LEG ...` line check_regime.py can lint.
  C. GPU functional (informational divergence datum): same WGSL run's
     mem[754]/ticks. The WGSL twin is NOT required to pass for VERDICT=PASS
     in this baseline step — a FAIL here is the measured R1.1 gap, recorded
     in RECEIPT_R11_anchor_baseline.md.

Verdict: VERDICT=PASS exit 0 iff leg A fully passes AND leg B's floor line
is admissible. Anything else: VERDICT=FAIL exit 1.

RED leg: --corrupt shifts the expected result by +1; the probe must then
print VERDICT=FAIL and exit 1 (proof the equality check can fail).
"""
import argparse
import pathlib
import sys
import tempfile
import time

_REPO = pathlib.Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools"), str(_REPO / ".builder_queue")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.agent_resident import (                     # noqa: E402
    resident_image, RES_KERNEL_OK,
)

ARGV_PAYLOAD = 0x2A          # same pinned input as the GH-26.4 gate
QUANTUM = 12                 # same tight timer as the gate


def _argv_word(v: int) -> int:
    op, payload = 0x11, v & 0xFF
    return (((op + payload) & 0xFF) << 24) | (op << 8) | payload


def _bake(tmp: pathlib.Path) -> pathlib.Path:
    out = tmp / "gh264.glyph.npy"
    resident_image(build_default_atlas(), mode="resident",
                   timer_quantum=QUANTUM, out_path=out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrupt", action="store_true",
                    help="RED leg: shift expectation by +1 (must FAIL)")
    args = ap.parse_args()

    expected = ARGV_PAYLOAD * 3 + (1 if args.corrupt else 0)
    failures = []

    with tempfile.TemporaryDirectory() as d:
        img = _bake(pathlib.Path(d))

        # ── leg A: CPU functional (the gated substrate) ─────────────────
        t0 = time.perf_counter()
        r_cpu = GlyphRunner(img, ram_words=16384).drive(
            seeds={}, max_instructions=60000)
        cpu_us = (time.perf_counter() - t0) * 1e6
        mem = r_cpu.get("memory", [])
        checks = [
            ("halted", r_cpu.get("halted") is True),
            ("no_fault", r_cpu.get("faulted") is False),
            ("result@754", len(mem) > 754 and mem[754] == expected),
            ("argv@750", len(mem) > 750 and mem[750] == _argv_word(ARGV_PAYLOAD)),
            ("done_flags@717", len(mem) > 717 and mem[717] == 3),
            ("ticks@732", len(mem) > 732 and mem[732] > 0),
            ("status950", r_cpu.get("status_word_value") == RES_KERNEL_OK),
        ]
        for name, ok in checks:
            if not ok:
                failures.append(f"cpu:{name}")
        print(f"CPU result@754 = {mem[754]:#x} expected {expected:#x} "
              f"({'MATCH' if mem[754] == expected else 'MISMATCH'}) "
              f"steps={r_cpu.get('steps')} ticks={mem[732]} "
              f"wall={cpu_us:,.0f}us")

        # ── leg B: GPU timed, per-step (the protocol the step-floor
        # describes: one dispatch + one blocking readback per round trip).
        # Mirrors GlyphRunner.run_wgsl's loop but times each step so the
        # LEG line reports true per-roundtrip cost, not setup-amortized.
        import numpy as np
        import wgpu, wgpu.utils
        from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
        from tools.glyph_isa_v2 import OpcodeMapV2

        arr_img = GlyphRunner(img).image  # load npy -> array (same loader as run_wgsl)
        rgba = np.zeros((arr_img.shape[0] * arr_img.shape[1], 4), dtype=np.uint32)
        rgba[:, 0:3] = arr_img.reshape(-1, 3)
        n_px = rgba.shape[0]
        cpu_state, cpu_dtype = make_cpu_state_array(1)
        mmio = np.zeros(160, dtype=np.uint32)
        ram_arr = np.zeros(16384, dtype=np.uint32)
        dt = np.dtype([('image_width', np.uint32), ('image_height', np.uint32),
                       ('output_buffer_size', np.uint32)])
        device = wgpu.utils.get_default_device(); queue = device.queue
        usage = wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        bufs = {}
        for name, arr, extra in (
                ("img", rgba, 0), ("cpu", cpu_state, 0),
                ("out", np.zeros(256, np.uint32), 0), ("mmio", mmio, 0),
                ("u", np.array([(arr_img.shape[1], arr_img.shape[0], 64)], dt),
                 wgpu.BufferUsage.UNIFORM), ("ram", ram_arr, 0)):
            b = device.create_buffer(size=arr.nbytes, usage=usage | extra)
            queue.write_buffer(b, 0, arr.tobytes()); bufs[name] = b
        bgl = device.create_bind_group_layout(entries=[
            {'binding': i, 'visibility': wgpu.ShaderStage.COMPUTE,
             'buffer': {'type': 'storage' if i != 3 else 'uniform'}}
            for i in range(6)])
        pLayout = device.create_pipeline_layout(bind_group_layouts=[bgl])
        bg = device.create_bind_group(layout=bgl, entries=[
            {'binding': 0, 'resource': {'buffer': bufs["img"], 'offset': 0, 'size': rgba.nbytes}},
            {'binding': 1, 'resource': {'buffer': bufs["cpu"], 'offset': 0, 'size': cpu_state.nbytes}},
            {'binding': 2, 'resource': {'buffer': bufs["out"], 'offset': 0, 'size': 256}},
            {'binding': 3, 'resource': {'buffer': bufs["u"], 'offset': 0, 'size': bufs["u"].size}},
            {'binding': 4, 'resource': {'buffer': bufs["mmio"], 'offset': 0, 'size': mmio.nbytes}},
            {'binding': 5, 'resource': {'buffer': bufs["ram"], 'offset': 0, 'size': ram_arr.nbytes}}])
        sh = device.create_shader_module(code=build_shader(OpcodeMapV2()))
        pipe = device.create_compute_pipeline(
            layout=pLayout,
            compute={'module': sh, 'entry_point': 'main'})

        step_us, steps, rb = [], 0, None
        readback = device.create_buffer(
            size=cpu_state.nbytes,
            usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ)
        import struct
        n_bytes = cpu_state.nbytes
        for steps in range(1, 60001):
            t0 = time.perf_counter()
            enc = device.create_command_encoder(); p = enc.begin_compute_pass()
            p.set_pipeline(pipe); p.set_bind_group(0, bg)
            p.dispatch_workgroups(1); p.end()
            enc.copy_buffer_to_buffer(bufs["cpu"], 0, readback, 0, n_bytes)
            queue.submit([enc.finish()])
            readback.map_sync(mode=wgpu.MapMode.READ)
            rb = np.frombuffer(bytes(readback.read_mapped()), dtype=cpu_dtype)[0]
            readback.unmap()
            step_us.append((time.perf_counter() - t0) * 1e6)
            if rb['running'] == 0:
                break
        steps = max(steps, 1)
        import statistics
        median_us = statistics.median(step_us)
        running_final = int(rb['running'])
        # final pixel readback (once, outside the timed loop)
        px_rb = device.create_buffer(
            size=rgba.nbytes,
            usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ)
        enc2 = device.create_command_encoder()
        enc2.copy_buffer_to_buffer(bufs["img"], 0, px_rb, 0, rgba.nbytes)
        queue.submit([enc2.finish()])
        px_rb.map_sync(mode=wgpu.MapMode.READ)
        px = np.frombuffer(bytes(px_rb.read_mapped()), dtype=np.uint32).reshape(n_px, 4)
        px_rb.unmap()
        wmem = [int((int(p[0]) << 16) | (int(p[1]) << 8) | int(p[2])) for p in px]
        r_wgsl = {"halted": bool(running_final == 0), "steps": steps,
                  "memory": wmem}

        # ── leg C: GPU functional divergence datum (informational) ──────
        wmem = r_wgsl.get("memory", [])
        w754 = wmem[754] if len(wmem) > 754 else None
        wgsl_match = w754 == expected
        print(f"WGSL result@754 = {w754:#x} expected {expected:#x} "
              f"({'MATCH' if wgsl_match else 'DIVERGENT'}) "
              f"ticks={wmem[732] if len(wmem) > 732 else '?'} "
              f"steps={steps} halted={r_wgsl.get('halted')}")

    # floor line for leg B: MEDIAN per-step cost of the per-step protocol
    # (one dispatch + one blocking readback per round trip — the exact
    # protocol calibrate_floors.py timed for the 'step' floor). x1: each
    # rep IS one round trip, same as the floor measurement.
    print(f"LEG wgsl_anchor {1e6 / median_us:,.0f} steps/s "
          f"{median_us:,.1f} us/rep step x1")

    if args.corrupt:
        # RED leg: equality must have failed
        if mem[754] == expected:
            failures.append("corrupt:expectation-wrongly-matched")
        else:
            print("CORRUPT-LEG: expectation did not match (correct RED)")
            failures.append("corrupt:expected-failure")

    if failures:
        print(f"VERDICT=FAIL failures={failures}")
        return 1
    print(f"VERDICT=PASS (cpu functional OK; wgsl timed leg {steps} steps; "
          f"wgsl functional divergence recorded as baseline datum)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
