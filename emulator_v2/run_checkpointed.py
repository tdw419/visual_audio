#!/usr/bin/env python3
"""Checkpointed xv6 boot from the PIXEL-SOURCED emulator shader.

This sandbox reaps long processes (~1h) and has intermittent GPU-dispatch
hangs, so a single ~1.5B-instruction run can't finish unattended. This runner
snapshots the full emulator state (18MB guest RAM + 528B CPU struct + 64KB
UART ring) to /home every CKPT_EVERY instructions and resumes from it on the
next invocation. Run it repeatedly (or under a watchdog); each invocation
makes forward progress.

State is fully contained in 3 GPU buffers - this shader has no TLB/decoded-op
caches (that was the SPATIAL_RV64I emulator). So snapshot+restore is exact.

Exit codes: 0 = shell reached ("init: starting sh"), 2 = instruction cap hit,
3 = GPU dispatch made no progress this invocation (caller should retry).
"""
import sys, time, os
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from boot_xv6_gpu_v2_simple import (
    ELF64Loader, make_cpu_state, create_gpu_hardware_v2, CPU_DTYPE,
)

SHADER_FRAME = Path("emulator_v2/emulator_frame.png")
KERNEL_FRAME = Path("emulator_v2/kernel_frame.png")
FS_FRAME     = Path("emulator_v2/fs_frame.png")
CKPT         = Path(os.path.expanduser("~/xv6_pixel_boot.ckpt.npz"))
UART_LOG     = Path("emulator_v2/v2_pixel_uart.log")
PHYS         = 0x80000000
MEM_MB       = 18
BATCH        = 2_000_000        # instructions per dispatch
CKPT_EVERY   = 40_000_000       # snapshot cadence (instructions)
INSTR_CAP    = 2_000_000_000    # give up past here
WALL_BUDGET  = 2700             # seconds per invocation, then checkpoint & exit


def _unpack_frame(path: Path, want_fmt: int) -> bytes:
    import struct, hashlib
    from PIL import Image
    raw = Image.open(path).convert("RGBA").tobytes()
    magic, ver, fmt, ln, dg = struct.unpack("<4sHHI32s", raw[:44])
    assert magic == b"EMV2", f"{path}: bad magic {magic!r}"
    assert fmt == want_fmt, f"{path}: fmt {fmt} != {want_fmt}"
    pl = raw[44:44 + ln]
    assert hashlib.sha256(pl).digest() == dg, f"{path}: sha256 mismatch"
    return pl


def build_initial_mem():
    """Zero-disk: kernel ELF and fs.img both come from pixel frames."""
    import io
    kbytes = _unpack_frame(KERNEL_FRAME, 2)
    fsb    = _unpack_frame(FS_FRAME, 3)
    ktmp = Path("/tmp/xv6_pixel_kernel.elf"); ktmp.write_bytes(kbytes)
    loader = ELF64Loader(str(ktmp))
    mem = np.zeros((MEM_MB * 1024 * 1024 // 4, 4), dtype=np.uint32)
    for seg in loader.get_loadable_segments():
        data = loader.get_segment_data(seg); base = seg['p_vaddr'] - PHYS
        for i, b in enumerate(data):
            mem[(base + i) // 4, (base + i) % 4] = b
    fo = 0x81000000 - PHYS
    bd = np.frombuffer(fsb, np.uint8); pad = (-len(bd)) % 4
    if pad:
        bd = np.concatenate([bd, np.zeros(pad, np.uint8)])
    mem[fo // 4: fo // 4 + len(bd) // 4] = bd.reshape(-1, 4)
    return loader, mem


def main():
    resuming = CKPT.exists()
    loader, mem = build_initial_mem()
    if resuming:
        z = np.load(CKPT)
        mem = z["mem"]; cpu = z["cpu"].view(CPU_DTYPE).copy()
        out_seed = z["out"]; total = int(z["total"])
        print(f"[resume] from checkpoint at {total:,} instructions", flush=True)
    else:
        cpu = make_cpu_state(loader.entry_point, priv_mode=3)
        out_seed = None; total = 0
        UART_LOG.write_text("")
        print("[start] fresh boot from pixel-sourced shader", flush=True)

    h = create_gpu_hardware_v2(SHADER_FRAME, mem, cpu, BATCH)
    dev, q, pipe, bg = h['device'], h['queue'], h['pipeline'], h['bind_group']
    cpu_buf, out_buf, mem_buf = h['cpu_buffer'], h['output_buffer'], h['memory_buffer']
    if out_seed is not None and out_seed.nbytes == 65536:
        q.write_buffer(out_buf, 0, out_seed.tobytes())

    def snapshot():
        m = np.frombuffer(q.read_buffer(mem_buf), dtype=np.uint32).reshape(-1, 4).copy()
        c = np.frombuffer(q.read_buffer(cpu_buf), dtype=np.uint8).copy()
        o = np.frombuffer(q.read_buffer(out_buf), dtype=np.uint8).copy()
        tmp = CKPT.with_suffix(".tmp.npz")
        np.savez(tmp, mem=m, cpu=c, out=o, total=np.int64(total))
        tmp.replace(CKPT)

    def uart_text():
        o = np.frombuffer(q.read_buffer(out_buf), dtype=np.uint8)
        nz = np.nonzero(o)[0]
        end = int(nz[-1]) + 1 if len(nz) else 0
        return bytes(o[:end]).decode("latin-1")

    start = time.time()
    _seen_init = [False]
    last_ckpt = total
    last_pc = None
    progressed = False
    while total < INSTR_CAP:
        enc = dev.create_command_encoder(); cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe); cp.set_bind_group(0, bg)
        cp.dispatch_workgroups(1, 1, 1); cp.end()
        q.submit([enc.finish()])
        c = np.frombuffer(q.read_buffer(cpu_buf), dtype=CPU_DTYPE)
        total = int(c['instr_count'][0])   # persisted in cpu_buffer, survives resume
        pc = int(c['pc'][0][0]) | (int(c['pc'][0][1]) << 32)
        run = int(c['running'][0])
        progressed = True

        txt = uart_text()
        UART_LOG.write_text(txt)
        if "init: starting sh" in txt and txt.rstrip().endswith("$"):
            print(f"[SHELL] reached '$' prompt at ~{total:,} instr", flush=True)
            snapshot()
            print(repr(txt[-200:]), flush=True)
            return 0
        if "init: starting sh" in txt and not _seen_init[0]:
            _seen_init[0] = True
            print(f"[init] 'init: starting sh' at ~{total:,} instr; continuing for $ prompt", flush=True)
        if run == 0:
            print(f"[HALT] running=0 at ~{total:,} instr, pc=0x{pc:x}", flush=True)
            snapshot(); return 2

        if total - last_ckpt >= CKPT_EVERY:
            snapshot(); last_ckpt = total
            print(f"  [ckpt] {total:,} instr  pc=0x{pc:08x}  uart={len(txt)}B", flush=True)

        if time.time() - start >= WALL_BUDGET:
            snapshot()
            print(f"[wall] budget hit, checkpointed at {total:,} instr", flush=True)
            return 3
        last_pc = pc

    snapshot()
    print(f"[cap] hit instruction cap {INSTR_CAP:,}", flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
