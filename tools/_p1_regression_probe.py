#!/usr/bin/env python3
"""Phase 1 regression probe: hash SPATIAL_RV64I core state at checkpoints during
an OpenSBI+Alpine boot (no disk, vq_ready=0). Run once per shader version and
diff the output. Any difference before the first virtio QueueNotify == the
mmio_write virtio-branch patch regressed the non-virtio path."""
import sys, os, hashlib, json
from pathlib import Path
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "tools")); sys.path.insert(0, str(_REPO))
import standalone_alpine_boot_quick as q
from spatial_rv64i_cpu import SpatialRV64ICore

CHECKPOINTS = [50_000, 150_000, 400_000, 800_000]

def snap(core):
    st = core.get_state()
    regs = [tuple(r) for r in st["regs"]]
    key = {
        "pc": st["pc"], "halted": int(st["halted"]), "mode": int(st["mode"]),
        "regs": regs,
        "csr_mtvec": core.read_csr(0x305), "csr_mepc": core.read_csr(0x341),
        "csr_mcause": core.read_csr(0x342), "csr_satp": core.read_csr(0x180),
        "csr_mstatus": core.read_csr(0x300), "csr_sepc": core.read_csr(0x141),
    }
    blob = json.dumps(key, sort_keys=True)
    return st["pc"], int(st["halted"]), hashlib.sha256(blob.encode()).hexdigest()[:16]

def main():
    core = SpatialRV64ICore(q.RAM_SIZE)
    dtb = q.load_opensbi_alpine_and_dtb(core)
    core.write_register(10, 0)
    core.write_register(11, dtb)
    done = 0
    for target in CHECKPOINTS:
        core.step(steps=target - done)
        done = target
        pc, halted, h = snap(core)
        print(f"@{done:>9} pc=0x{pc:016x} halted={halted} state={h}")
        if halted:
            print(f"  (halted at {done})")
            break

if __name__ == "__main__":
    main()
