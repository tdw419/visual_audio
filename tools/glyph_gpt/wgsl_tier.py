"""BK-12 — WGSL throughput tier, beside the pixel provenance tier.

Two tiers, one byte stream
--------------------------
  * **provenance tier** — every word of Glyph OS state is a pixel (GH-8b:
    the FS window [1024,1280) aliases image pixels, 2 px/word, "the image
    is the disk"). Replayable, hashable, visible. Cost structure: one
    engine LD/ST per word.
  * **throughput tier** — the same words in WGSL storage buffers on the
    GPU. Bulk movement (`memcpy`, FS block copy) happens there while the
    pixel tier keeps the provenance record.

The tier is *added beside* the engine: no engine, transpiler or ABI change.
What makes it safe is that equivalence is enforced, not assumed — every
word list moved on the GPU is checked against the CPU reference and against
a round trip through the engine's own pixel encoding (`fs_write_words` /
`fs_read_words` call `glyph_isa_v2._fs_pix_write` / `_fs_pix_read`, the
same functions the CPU dispatch uses for an LD/ST into the window).

Honest caveats (they live in the receipt too):
  * the pixel-tier measurement in the gate is the interpreter engine
    executing a real assembled program — that is the tier's actual cost,
    not a straw man;
  * the WGSL measurement is submits without host readback, with buffer
    setup timed separately and reported;
  * the tier does not make Glyph OS fast at *execution* — it moves bytes.
    Execution remains the provenance tier's job.

Gate: `tests/test_bk12_wgsl_tier.py` (roadmap row BK-12).
"""

from __future__ import annotations

import hashlib
import struct
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2  # noqa: E402

WORDS_PER_KB = 256           # 256 words x 4 bytes = 1024 bytes
WORKGROUP_SIZE = 64

#: The block-copy shader: one word per invocation, offsets from a uniform.
#: Read-only `src` + read-write `dst` so the tier cannot be mistaken for an
#: in-place mutation path (the copy is a real second memory region, which is
#: what an FS block copy between extents is).
BLOCK_COPY_WGSL = """
struct Params {
    count: u32,
    src_off: u32,
    dst_off: u32,
    _pad: u32,
};

@group(0) @binding(0) var<storage, read> src: array<u32>;
@group(0) @binding(1) var<storage, read_write> dst: array<u32>;
@group(0) @binding(2) var<uniform> params: Params;

@compute @workgroup_size(%d)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let i = gid.x;
    if (i >= params.count) { return; }
    dst[params.dst_off + i] = src[params.src_off + i];
}
""" % WORKGROUP_SIZE


# --------------------------------------------------------------------------
# word helpers
# --------------------------------------------------------------------------

def pack_words(words: Sequence[int]) -> bytes:
    """Little-endian 32-bit packing — the same layout the GPU buffers use."""
    return struct.pack("<%dI" % len(words), *[int(w) & 0xFFFFFFFF for w in words])


def words_md5(words: Sequence[int]) -> str:
    return hashlib.md5(pack_words(words)).hexdigest()


def _norm(words: Sequence[int]) -> List[int]:
    return [int(w) & 0xFFFFFFFF for w in words]


# --------------------------------------------------------------------------
# CPU reference tier (what the pixel tier's correctness is defined against)
# --------------------------------------------------------------------------

def cpu_block_copy(words: Sequence[int], count: Optional[int] = None,
                   src_off: int = 0, dst_off: int = 0,
                   dst_len: Optional[int] = None) -> List[int]:
    """Reference block copy: dst[dst_off + i] = src[src_off + i]."""
    src = _norm(words)
    count = len(src) if count is None else int(count)
    if dst_len is None:
        dst_len = dst_off + count
    dst = [0] * int(dst_len)
    for i in range(count):
        dst[dst_off + i] = src[src_off + i]
    return dst


# --------------------------------------------------------------------------
# WGSL throughput tier
# --------------------------------------------------------------------------

def _make_device():
    import wgpu
    import wgpu.utils
    return wgpu.utils.get_default_device()


class WgslBlockCopier:
    """Resident-buffer block copier: buffers and pipeline created once.

    Buffer creation is host-side setup (timed separately by the gate); the
    per-call cost measured is the compute submit itself.
    """

    def __init__(self, dst_len: int, src_len: Optional[int] = None,
                 device=None):
        import wgpu
        self.wgpu = wgpu
        self.device = device if device is not None else _make_device()
        self.queue = self.device.queue
        self.src_len = int(src_len if src_len is not None else dst_len)
        self.dst_len = int(dst_len)
        usage = (wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
                 | wgpu.BufferUsage.COPY_SRC)
        self.src_buf = self.device.create_buffer(size=self.src_len * 4, usage=usage)
        self.dst_buf = self.device.create_buffer(size=self.dst_len * 4, usage=usage)
        self.params_buf = self.device.create_buffer(
            size=16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        bgl = self.device.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE,
             "buffer": {"type": "read-only-storage"}},
            {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE,
             "buffer": {"type": "storage"}},
            {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE,
             "buffer": {"type": "uniform"}},
        ])
        self.bind_group = self.device.create_bind_group(layout=bgl, entries=[
            {"binding": 0, "resource": {"buffer": self.src_buf, "offset": 0,
                                        "size": self.src_len * 4}},
            {"binding": 1, "resource": {"buffer": self.dst_buf, "offset": 0,
                                        "size": self.dst_len * 4}},
            {"binding": 2, "resource": {"buffer": self.params_buf, "offset": 0,
                                        "size": 16}},
        ])
        module = self.device.create_shader_module(code=BLOCK_COPY_WGSL)
        self.pipeline = self.device.create_compute_pipeline(
            layout=self.device.create_pipeline_layout(bind_group_layouts=[bgl]),
            compute={"module": module, "entry_point": "main"})

    def copy(self, words: Sequence[int], count: Optional[int] = None,
             src_off: int = 0, dst_off: int = 0) -> None:
        """Upload `words` and submit one copy dispatch (no readback)."""
        src = _norm(words)
        count = len(src) if count is None else int(count)
        assert count <= self.src_len, "source block exceeds the resident buffer"
        assert dst_off + count <= self.dst_len, "destination overflows the buffer"
        self.queue.write_buffer(self.src_buf, 0, pack_words(src))
        params = np.array([count, src_off, dst_off, 0], dtype=np.uint32)
        self.queue.write_buffer(self.params_buf, 0, params.tobytes())
        enc = self.device.create_command_encoder()
        p = enc.begin_compute_pass()
        p.set_pipeline(self.pipeline)
        p.set_bind_group(0, self.bind_group)
        p.dispatch_workgroups((count + WORKGROUP_SIZE - 1) // WORKGROUP_SIZE)
        p.end()
        self.queue.submit([enc.finish()])

    def read_dst(self, n: Optional[int] = None) -> List[int]:
        n = self.dst_len if n is None else int(n)
        raw = self.queue.read_buffer(self.dst_buf, size=n * 4)
        return [int(w) for w in np.frombuffer(raw, dtype=np.uint32)[:n]]

    def copy_and_read(self, words: Sequence[int], count: Optional[int] = None,
                      src_off: int = 0, dst_off: int = 0) -> List[int]:
        self.copy(words, count=count, src_off=src_off, dst_off=dst_off)
        return self.read_dst(self.dst_len)


def wgsl_block_copy(words: Sequence[int], count: Optional[int] = None,
                    src_off: int = 0, dst_off: int = 0,
                    dst_len: Optional[int] = None,
                    device=None) -> List[int]:
    """One-shot block copy on WGSL compute buffers; returns the whole dst."""
    src = _norm(words)
    count = len(src) if count is None else int(count)
    if dst_len is None:
        dst_len = dst_off + count
    copier = WgslBlockCopier(dst_len=int(dst_len), src_len=max(len(src), count),
                             device=device)
    return copier.copy_and_read(src, count=count, src_off=src_off, dst_off=dst_off)


# --------------------------------------------------------------------------
# provenance bridge — the engine's own pixel-FS window encoding
# --------------------------------------------------------------------------

def fs_write_words(cpu: "GlyphCPUv2", image: np.ndarray, base: int,
                   words: Sequence[int]) -> None:
    """Write words into the GH-8b pixel-FS window via the ENGINE's writer.

    Uses `GlyphCPUv2._fs_pix_write` (2 px/word: lo24 in pixel RGB, hi8 in
    the BLUE channel of the odd pixel) so the bridge cannot drift from the
    encoding the CPU dispatch itself uses on an LD/ST into the window.
    """
    for i, w in enumerate(_norm(words)):
        cpu._fs_pix_write(image, base + i, w)


def fs_read_words(cpu: "GlyphCPUv2", image: np.ndarray, base: int,
                  n: int) -> List[int]:
    """Read words back out of the pixel-FS window via the ENGINE's reader."""
    return [cpu._fs_pix_read(image, base + i) & 0xFFFFFFFF for i in range(int(n))]


# --------------------------------------------------------------------------
# pixel-tier copy program (a real engine LD/ST loop, storage in pixels)
# --------------------------------------------------------------------------

def build_pixel_copy_program(n_words: int, src_base: int, dst_base: int,
                             width_instrs: int = 8) -> List[str]:
    """Assemble-ready lines for a word-copy loop over the pixel-FS window.

    Layout (width 8 instrs/row):
        0 LDI r1 src_base     1 LDI r2 dst_base    2 LDI r3 n_words
        3 LDI r4 1            4 LDI r7 0           5 LD  r6 r1   <- loop
        6 ST  r2 r6           7 ADD r1 r4          8 ADD r2 r4
        9 SUB r3 r4          10 CMP r3 r7         11 JZ  done
       12 JMP loop            13 HALT               14 HALT       <- done

    JMP/JZ carry absolute packed (col,row) instruction targets — the ISA
    has no memory-indirect jump — so the targets are derived from the
    instruction index and the row width rather than written by hand.
    """
    def coord(idx: int) -> str:
        return "%d,%d" % (idx % width_instrs, idx // width_instrs)

    loop_idx, done_idx = 5, 14
    return [
        "LDI r1 %d" % int(src_base),
        "LDI r2 %d" % int(dst_base),
        "LDI r3 %d" % int(n_words),
        "LDI r4 1",
        "LDI r7 0",
        "LD r6 r1",
        "ST r2 r6",
        "ADD r1 r4",
        "ADD r2 r4",
        "SUB r3 r4",
        "CMP r3 r7",
        "JZ %s" % coord(done_idx),
        "JMP %s" % coord(loop_idx),
        "HALT",
        "HALT",
    ]


def run_pixel_copy(words: Sequence[int], n_words: int, src_base: int,
                   dst_base: int, program: Optional[Sequence[str]] = None,
                   width_instrs: int = 8, pad_rows: int = 80,
                   max_instructions: int = 20000,
                   opcode_map: Optional["OpcodeMapV2"] = None) -> Dict:
    """Execute the pixel-tier copy loop; returns copied words + timing.

    The storage the loop copies IS the pixel-FS window: with
    `fs_pix_enabled=True` the engine's LD/ST on words [1024,1280) read and
    write image pixels (GH-8b), so the copied bytes are persisted pixels,
    not host RAM. `pad_rows` must be large enough that both pixel halves of
    window word 1279 land inside the image (32 px/row here -> 80 rows).
    """
    program = list(program) if program is not None else build_pixel_copy_program(
        n_words, src_base, dst_base, width_instrs=width_instrs)
    op = opcode_map if opcode_map is not None else OpcodeMapV2()
    try:
        asm = GlyphAssemblerV2(op)
        image = asm.assemble(program, width_instrs=width_instrs)
        if pad_rows > image.shape[0]:
            image = np.vstack([image, np.zeros((pad_rows - image.shape[0],
                                                image.shape[1], 3), dtype=np.uint8)])
        cpu = GlyphCPUv2(op, width_instrs, fs_pix_enabled=True)
        cpu.memory.extend([0] * 512)          # room for the write-through mirror
        fs_write_words(cpu, image, src_base, words)
        t0 = time.perf_counter()
        steps = cpu.run(image, max_instructions=max_instructions)
        seconds = time.perf_counter() - t0
        copied = fs_read_words(cpu, image, dst_base, n_words)
        return {
            "copied": copied,
            "image": image,
            "steps": int(steps),
            "seconds": seconds,
            "halted": int(steps) < max_instructions,
            "faulted": bool(getattr(cpu, "faulted", False)),
            "md5": words_md5(copied),
        }
    finally:
        op.close()
