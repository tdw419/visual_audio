#!/usr/bin/env python3
"""One-shot diagnostic: boot xv6 on the GPU shader and answer two questions.

1. Does execution ever enter U-mode (pc < 0x80000000)?
2. Does proc[0].state ever leave UNUSED -> USED/RUNNABLE/RUNNING?
   Does `initproc` ever become non-null (userinit ran)?

Prints CSR fault state at each dispatch boundary so a trap loop is visible.
"""
import sys, struct
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from boot_xv6_gpu_v2_simple import (
    ELF64Loader, make_cpu_state, create_gpu_hardware_v2, CPU_DTYPE,
)

KERNEL = "/tmp/xv6-riscv/kernel/kernel"
SHADER_FRAME = Path("emulator_v2/emulator_frame.png")
PHYS = 0x80000000
PROC0_STATE = 0x800157a0 + 24          # struct proc[0].state
INITPROC_PTR = 0x8000d248              # struct proc *initproc
PROCSTATE = {0:"UNUSED",1:"USED",2:"SLEEPING",3:"RUNNABLE",4:"RUNNING",5:"ZOMBIE"}

def rd_u32(mem, addr):
    off = addr - PHYS
    return int(mem[off // 4, off % 4]) if (off % 4 == 0) else None

def rd_u64(mem, addr):
    off = addr - PHYS
    lo = mem[off // 4].view(np.uint32)
    # bytes are stored one-per-lane; reconstruct
    b = bytes(int(mem[(off + i)//4, (off + i)%4]) for i in range(8))
    return struct.unpack("<Q", b)[0]

def main():
    loader = ELF64Loader(KERNEL)
    MEM_MB = 18
    mem = np.zeros((MEM_MB*1024*1024//4, 4), dtype=np.uint32)
    for seg in loader.get_loadable_segments():
        data = loader.get_segment_data(seg)
        base = seg['p_vaddr'] - PHYS
        for i, byte in enumerate(data):
            mem[(base+i)//4, (base+i)%4] = byte
    fs = Path("/tmp/xv6-riscv/fs.img")
    if fs.exists():
        fsb = fs.read_bytes(); fo = 0x81000000 - PHYS
        bd = np.frombuffer(fsb, np.uint8)
        pad = (-len(bd)) % 4
        if pad: bd = np.concatenate([bd, np.zeros(pad, np.uint8)])
        mem[fo//4 : fo//4 + len(bd)//4] = bd.reshape(-1,4)

    cpu = make_cpu_state(loader.entry_point, priv_mode=3)
    h = create_gpu_hardware_v2(SHADER_FRAME, mem, cpu, 250_000)
    dev, q, pipe, bg = h['device'], h['queue'], h['pipeline'], h['bind_group']
    cpu_buf, mem_buf = h['cpu_buffer'], h['memory_buffer']

    entered_user = False
    proc0_seen = set()
    initproc_seen = False
    N = 240   # 240 * 250k = 60M instructions
    for d in range(N):
        enc = dev.create_command_encoder()
        cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe); cp.set_bind_group(0, bg)
        cp.dispatch_workgroups(1,1,1); cp.end()
        q.submit([enc.finish()])
        c = np.frombuffer(q.read_buffer(cpu_buf), dtype=CPU_DTYPE)
        m = np.frombuffer(q.read_buffer(mem_buf), dtype=np.uint32).reshape(-1,4)

        pc  = int(c['pc'][0][0]) | (int(c['pc'][0][1])<<32)
        pm  = int(c['priv_mode'][0])
        ic  = int(c['instr_count'][0])
        sc  = int(c['scause'][0][0]);  se = int(c['sepc'][0][0]); st = int(c['stval'][0][0])
        mc  = int(c['mcause'][0][0]);  me = int(c['mepc'][0][0])
        p0  = rd_u32(m, PROC0_STATE)
        ip  = rd_u64(m, INITPROC_PTR)
        if pc < PHYS: entered_user = True
        if p0 is not None: proc0_seen.add(p0)
        if ip: initproc_seen = True

        if d < 8 or d % 20 == 0 or pc < PHYS:
            print(f"[{d:3d}] ic={ic:>10} pc=0x{pc:08x} priv={pm} "
                  f"scause=0x{sc:x} sepc=0x{se:08x} stval=0x{st:x} "
                  f"mcause=0x{mc:x} mepc=0x{me:08x} "
                  f"proc0={PROCSTATE.get(p0,p0)} initproc={'set' if ip else '0'}", flush=True)
        if int(c['running'][0]) == 0:
            print(f"  HALTED at ic={ic}"); break

    print("\n==== SUMMARY ====")
    print(f"entered U-mode (pc<0x80000000): {entered_user}")
    print(f"proc[0].state values seen: {sorted(PROCSTATE.get(s,s) for s in proc0_seen)}")
    print(f"initproc ever set: {initproc_seen}")

if __name__ == "__main__":
    main()
