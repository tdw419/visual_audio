#!/usr/bin/env python3
"""runner.py — standalone spatial image launcher (GH-5 final form; GH-11
adds the generic end-to-end drive() session). Pure launcher, zero dev
imports. Loads a spatial image container (.png/.npy/.npz), executes on
GlyphCPUv2 or WGSL, and returns receipts bit-exact to run_generated.
"""
from __future__ import annotations
import contextlib, hashlib, io, sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from PIL import Image

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE.parent), str(_HERE.parent.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2  # noqa: E402


class GlyphRunner:
    """Minimal standalone launcher for baked Geometry OS spatial images."""

    def __init__(
        self,
        image_or_path: Union[str, Path, np.ndarray],
        cols_instrs: Optional[int] = None,
        ram_words: Optional[int] = None,
    ) -> None:
        if isinstance(image_or_path, np.ndarray):
            self.image = image_or_path.copy()
        else:
            p = Path(image_or_path)
            if p.suffix == ".npy":
                self.image = np.load(p)
            elif p.suffix == ".npz":
                with np.load(p) as data:
                    self.image = data["image"] if "image" in data else data[list(data.keys())[0]]
            else:
                self.image = np.array(Image.open(p).convert("RGB"))
        # Every instruction is 4 horizontal pixels wide
        self.cols_instrs = cols_instrs or (self.image.shape[1] // 4)
        # ram_words opt-in: images using the isolation MMIO block (8192+)
        # need len(memory) > TILE_W_ADDR>>2 to arm the box check + trap;
        # None keeps the 1024-word default (GH-1 parity).
        self.ram_words = ram_words

    @classmethod
    def launcher_info(cls) -> Dict[str, Any]:
        n = len(Path(__file__).resolve().read_text().splitlines())
        return {"version": "gh11", "backends": ["cpu", "wgsl"], "max_lines": 200, "lines": n}

    def get_cpu(self) -> GlyphCPUv2:
        """Fresh GlyphCPUv2 (ram_words opt-in arms _iso_enabled)."""
        cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=self.cols_instrs, fs_pix_enabled=True)
        if self.ram_words is not None:
            cpu.memory = [0] * self.ram_words
        return cpu

    def md5(self) -> str:
        """MD5 of the resident image container bytes."""
        return hashlib.md5(self.image.tobytes()).hexdigest()

    def run(self, max_instructions: int = 5000, trace: bool = False) -> Dict[str, Any]:
        """Execute the image until HALT or fault, emitting a receipt.

        trace=True records (row-major instruction index, mode) per step
        in receipt["step_trace"] (default fast path bit-exact, GH-1)."""
        receipt: Dict[str, Any] = {"assembled": True, "executed": False, "halted": False, "faulted": False}
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cpu = self.get_cpu()
                if trace:
                    steps = 0
                    step_trace: List[Tuple[int, str]] = []
                    cpu.running = True   # run() sets this; the step loop mirrors it
                    while cpu.running and steps < max_instructions:
                        step_trace.append((cpu.pc[1] * cpu.cols_instrs + cpu.pc[0] // 4,
                                           "USER" if cpu.mode else "SUPER"))
                        cpu.step(self.image)   # LIVE image: pixel stores persist (GH-8b)
                        steps += 1
                    receipt["step_trace"] = step_trace
                else:
                    steps = cpu.run(self.image, max_instructions=max_instructions)
            self._fill_receipt(receipt, cpu, steps)
        except Exception as e:
            receipt["error"] = f"{type(e).__name__}: {e}"
        return receipt

    def drive(
        self,
        seeds: Optional[Dict[int, int]] = None,
        max_instructions: int = 60000,
    ) -> Dict[str, Any]:
        """GH-11: generic end-to-end session through this launcher. The
        host seeds exec-state words (argv, mailbox payloads, cmd buffers —
        the loader role), the resident kernel runs to HALT or fault on the
        LIVE image; the receipt carries memory, status and fault."""
        receipt: Dict[str, Any] = {"assembled": True, "executed": False, "halted": False, "faulted": False}
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cpu = self.get_cpu()
                for w, v in (seeds or {}).items():
                    cpu.memory[int(w)] = int(v) & 0xFFFFFFFF
                steps = cpu.run(self.image, max_instructions=max_instructions)
            self._fill_receipt(receipt, cpu, steps)
        except Exception as e:
            receipt["error"] = f"{type(e).__name__}: {e}"
        return receipt

    def _fill_receipt(self, receipt: Dict[str, Any], cpu: GlyphCPUv2, steps: int) -> None:
        receipt["executed"] = True
        receipt["faulted"] = bool(getattr(cpu, "faulted", False))
        if receipt["faulted"]:
            receipt["fault_addr"] = int(getattr(cpu, "fault_addr", 0)) & 0xFFFFFFFF
        receipt["halted"] = not cpu.running
        receipt["steps"] = int(steps)
        nreg = len(cpu.registers)
        receipt["registers_full"] = [int(cpu.registers[i]) & 0xFFFFFFFF for i in range(nreg)]
        receipt["registers"] = receipt["registers_full"][:8]
        receipt["memory"] = [int(m) & 0xFFFFFFFF for m in cpu.memory]
        # GH-8b: status word 950 is ordinary RAM, kept coherent by the
        # engine's write-through mirror.
        receipt["status_word_value"] = receipt["memory"][950]

    def run_wgsl(self, max_steps: int = 5000) -> Dict[str, Any]:
        """Execute the image on GPU via the WGPU compute pipeline."""
        import wgpu
        import wgpu.utils
        from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
        receipt: Dict[str, Any] = {"assembled": True, "executed": False, "halted": False, "faulted": False}
        try:
            device = wgpu.utils.get_default_device()
            queue = device.queue
            n_pixels = self.image.shape[0] * self.image.shape[1]
            rgba = np.zeros((n_pixels, 4), dtype=np.uint32)
            rgba[:, 0:3] = self.image.reshape(n_pixels, 3)
            usage = wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
            img_buf = device.create_buffer(size=rgba.nbytes, usage=usage)
            queue.write_buffer(img_buf, 0, rgba.tobytes())
            cpu_state, cpu_dtype = make_cpu_state_array(1)
            cpu_buf = device.create_buffer(size=cpu_state.nbytes, usage=usage)
            queue.write_buffer(cpu_buf, 0, cpu_state.tobytes())
            out_buf = device.create_buffer(size=256, usage=usage)
            dt = np.dtype([('image_width', np.uint32), ('image_height', np.uint32), ('output_buffer_size', np.uint32)])
            uniforms = np.array([(self.image.shape[1], self.image.shape[0], 64)], dtype=dt)
            u_buf = device.create_buffer(size=uniforms.nbytes, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
            queue.write_buffer(u_buf, 0, uniforms.tobytes())
            bgl = device.create_bind_group_layout(entries=[
                {'binding': i, 'visibility': wgpu.ShaderStage.COMPUTE,
                 'buffer': {'type': 'storage' if i < 3 else 'uniform'}} for i in range(4)])
            bg = device.create_bind_group(layout=bgl, entries=[                {'binding': 0, 'resource': {'buffer': img_buf, 'offset': 0, 'size': rgba.nbytes}},
                {'binding': 1, 'resource': {'buffer': cpu_buf, 'offset': 0, 'size': cpu_state.nbytes}},
                {'binding': 2, 'resource': {'buffer': out_buf, 'offset': 0, 'size': 256}},
                {'binding': 3, 'resource': {'buffer': u_buf, 'offset': 0, 'size': uniforms.nbytes}},
            ])
            sh = device.create_shader_module(code=build_shader(OpcodeMapV2()))
            pipe = device.create_compute_pipeline(layout=device.create_pipeline_layout(bind_group_layouts=[bgl]),
                                                  compute={'module': sh, 'entry_point': 'main'})
            steps = 0
            for _ in range(max_steps):
                enc = device.create_command_encoder()
                p = enc.begin_compute_pass()
                p.set_pipeline(pipe)
                p.set_bind_group(0, bg)
                p.dispatch_workgroups(1)
                p.end()
                queue.submit([enc.finish()])
                steps += 1
                rb = np.frombuffer(queue.read_buffer(cpu_buf), dtype=cpu_dtype)[0]
                if rb['running'] == 0:
                    break
            receipt["executed"] = True
            receipt["halted"] = bool(rb['running'] == 0)
            receipt["steps"] = steps
            receipt["registers_full"] = [int(r) for r in rb['registers']]
            receipt["registers"] = receipt["registers_full"][:8]
        except Exception as e:
            receipt["error"] = f"{type(e).__name__}: {e}"
        return receipt

    def __call__(self, max_instructions: int = 5000, backend: str = "cpu") -> Dict[str, Any]:
        if backend == "wgsl":
            return self.run_wgsl(max_steps=max_instructions)
        return self.run(max_instructions=max_instructions)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: python3 runner.py <img> [--backend=cpu|wgsl]")
    backend = "cpu"
    for arg in sys.argv[2:]:
        if arg.startswith("--backend="):
            backend = arg.split("=")[1]
    r = GlyphRunner(sys.argv[1])(backend=backend)
    print(f"Executed: halted={r.get('halted')} steps={r.get('steps')}")
if __name__ == "__main__":
    main()