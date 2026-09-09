#!/usr/bin/env python3
"""Fine single-step trace of the scheduler trap loop.

Boots xv6 on the GPU shader with a tiny per-dispatch instruction budget so we
can log every PC. Stays quiet until instr_count passes THRESH, then prints
pc / priv / scause / sepc / stval for STEPS dispatches.
"""
import sys
from pathlib import Path
import numpy as np
import wgpu

sys.path.insert(0, str(Path(__file__).parent))
from boot_xv6_gpu_v2_simple import (
    ELF64Loader, make_cpu_state, create_gpu_hardware_v2, CPU_DTYPE,
)

KERNEL = "/tmp/xv6-riscv/kernel/kernel"
SHADER_FRAME = Path("emulator_v2/emulator_frame.png")
PHYS = 0x80000000
THRESH = 14_000_000
BATCH  = 1          # instructions per dispatch once we create the harness
WARM_BATCH = 4000   # bigger batches until THRESH
STEPS  = 400        # fine steps to log

def load_mem():
    loader = ELF64Loader(KERNEL)
    mem = np.zeros((18*1024*1024//4, 4), dtype=np.uint32)
    for seg in loader.get_loadable_segments():
        data = loader.get_segment_data(seg); base = seg['p_vaddr'] - PHYS
        for i, b in enumerate(data): mem[(base+i)//4, (base+i)%4] = b
    fsb = Path("/tmp/xv6-riscv/fs.img").read_bytes(); fo = 0x81000000 - PHYS
    bd = np.frombuffer(fsb, np.uint8); pad = (-len(bd)) % 4
    if pad: bd = np.concatenate([bd, np.zeros(pad, np.uint8)])
    mem[fo//4: fo//4 + len(bd)//4] = bd.reshape(-1,4)
    return loader, mem

def main():
    loader, mem = load_mem()
    cpu = make_cpu_state(loader.entry_point, priv_mode=3)
    h = create_gpu_hardware_v2(SHADER_FRAME, mem, cpu, WARM_BATCH)
    dev, q, pipe, bg, cpu_buf = h['device'], h['queue'], h['pipeline'], h['bind_group'], h['cpu_buffer']

    # locate the uniform buffer (max_instructions) so we can shrink the batch live
    # create_gpu_hardware_v2 doesn't return it; rebuild a 1-elem uniform and re-bind is hard,
    # so instead: warm with WARM_BATCH by repeated dispatch, then keep dispatching WARM_BATCH
    # but log every dispatch (4000-instr resolution). Good enough to see the loop period.
    def rd():
        c = np.frombuffer(q.read_buffer(cpu_buf), dtype=CPU_DTYPE)
        pc = int(c['pc'][0][0]) | (int(c['pc'][0][1])<<32)
        return (pc, int(c['priv_mode'][0]), int(c['instr_count'][0]),
                int(c['scause'][0][0]), int(c['sepc'][0][0]), int(c['stval'][0][0]),
                int(c['mcause'][0][0]), int(c['mepc'][0][0]), int(c['running'][0]))

    ic = 0
    while ic < THRESH:
        enc = dev.create_command_encoder(); cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe); cp.set_bind_group(0, bg); cp.dispatch_workgroups(1,1,1); cp.end()
        q.submit([enc.finish()])
        pc, pm, ic, sc, se, st, mc, me, run = rd()
        if run == 0: print("halted while warming, ic=", ic); return
    print(f"--- warm done ic={ic}, fine trace ({WARM_BATCH}-instr steps) ---")
    prev_pc = None
    for i in range(STEPS):
        enc = dev.create_command_encoder(); cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe); cp.set_bind_group(0, bg); cp.dispatch_workgroups(1,1,1); cp.end()
        q.submit([enc.finish()])
        pc, pm, ic, sc, se, st, mc, me, run = rd()
        print(f"{i:3d} ic={ic:>10} pc=0x{pc:08x} priv={pm} scause=0x{sc:x} "
              f"sepc=0x{se:08x} stval=0x{st:08x} mcause=0x{mc:x} mepc=0x{me:08x}", flush=True)
        if run == 0: print("HALTED"); break

if __name__ == "__main__":
    main()
