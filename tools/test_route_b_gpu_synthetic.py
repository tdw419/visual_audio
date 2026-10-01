#!/usr/bin/env python3
"""
Route B Phase 2/3 on the real GPU, without a Linux boot.

A hand-written RV64 "driver" sets up a legacy virtio-mmio queue in guest RAM
and rings QueueNotify. Two modes:

  offload  (vq_ready=2): shader must yield (halted==2); host VirtioBlkHost
           services the ring against a real file; data must land in the guest
           data buffer, status byte 0, used ring advanced; then the core
           resumes and halts on ecall.

  standalone (vq_ready=0): shader's own process_virtqueue_spatial() must walk
           the same ring. Needs RAM covering DISK_PA (0x81600000) -> 64MB core.

Run:  python3 tools/test_route_b_gpu_synthetic.py [--standalone]
Exit 0 = pass.
"""
from __future__ import annotations
import argparse, os, struct, sys, tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "tools")); sys.path.insert(0, str(_REPO))

from spatial_rv64i_cpu import SpatialRV64ICore
from rv64i_asm import assemble
from qemu_gpu_offload import GpuRam, QueueConfig, VirtioBlkHost

RAM_BASE   = 0x80000000
VIRTIO     = 0x10007000
QNUM       = 4
SECTOR     = 512
PATTERN    = bytes([0x5A]) * SECTOR

# Guest layout. The shader derives avail/used from desc on the 0x40 write:
#   desc  = PFN*4096
#   avail = desc + QNUM*16
#   used  = align_up(avail + 6 + QNUM*2, align)
PFN        = 0x80010                      # -> desc = 0x80010000
DESC       = PFN * 4096
AVAIL      = DESC + QNUM * 16             # 0x80010040
USED       = (AVAIL + 6 + QNUM * 2 + 4095) & ~4095   # 0x80011000
HDR_BUF    = 0x80012000
DATA_BUF   = 0x80013000
STATUS_BUF = 0x80014000

VRING_DESC_F_NEXT  = 1
VRING_DESC_F_WRITE = 2
VIRTIO_BLK_T_IN    = 0

DRIVER_ASM = f"""
    li   t0, {VIRTIO}
    li   a0, {QNUM}
    sw   a0, 0x38(t0)          # QueueNum
    li   a0, 4096
    sw   a0, 0x3c(t0)          # QueueAlign
    li   a0, {PFN}
    sw   a0, 0x40(t0)          # QueuePFN  -> desc/avail/used latched
    li   a0, 4
    sw   a0, 0x70(t0)          # Status = DRIVER_OK
    li   a0, 0
    sw   a0, 0x50(t0)          # QueueNotify  -> yield (offload) / in-shader walk
    ecall                      # halt after the request is serviced
"""


def w32(core, gpa, val):
    core.write_mem_word(gpa - RAM_BASE, val & 0xFFFFFFFF)

def w16pair(core, gpa, lo, hi):
    core.write_mem_word(gpa - RAM_BASE, (lo & 0xFFFF) | ((hi & 0xFFFF) << 16))

def r32(core, gpa):
    return core.read_mem_word(gpa - RAM_BASE) & 0xFFFFFFFF


def build_queue(core):
    # desc[0] header (read by device), -> desc[1]
    w32(core, DESC + 0,  HDR_BUF)
    w32(core, DESC + 4,  0)
    w32(core, DESC + 8,  16)
    w16pair(core, DESC + 12, VRING_DESC_F_NEXT, 1)          # flags, next=1
    # desc[1] data buffer (written by device), -> desc[2]
    w32(core, DESC + 16, DATA_BUF)
    w32(core, DESC + 20, 0)
    w32(core, DESC + 24, SECTOR)
    w16pair(core, DESC + 28, VRING_DESC_F_NEXT | VRING_DESC_F_WRITE, 2)
    # desc[2] status byte (written by device)
    w32(core, DESC + 32, STATUS_BUF)
    w32(core, DESC + 36, 0)
    w32(core, DESC + 40, 1)
    w16pair(core, DESC + 44, VRING_DESC_F_WRITE, 0)

    # virtio_blk_req header: type=IN, reserved, sector=0
    w32(core, HDR_BUF + 0, VIRTIO_BLK_T_IN)
    w32(core, HDR_BUF + 4, 0)
    w32(core, HDR_BUF + 8, 0)
    w32(core, HDR_BUF + 12, 0)

    w32(core, DATA_BUF, 0)                                  # scratch, will be overwritten
    w32(core, STATUS_BUF, 0xFFFFFFFF)                       # poison; device writes 0

    # avail: flags=0, idx=1, ring[0]=0 (head descriptor index)
    w16pair(core, AVAIL + 0, 0, 1)
    w16pair(core, AVAIL + 4, 0, 0)
    # used: flags=0, idx=0
    w16pair(core, USED + 0, 0, 0)


def run(standalone: bool) -> int:
    ram_mb = 64 if standalone else 4
    print(f"[init] SpatialRV64ICore({ram_mb}MB)  mode={'standalone' if standalone else 'offload'}")
    core = SpatialRV64ICore(ram_mb * 1024 * 1024)

    core.load_program(assemble(DRIVER_ASM), entry_point=RAM_BASE, ram_base=RAM_BASE)
    build_queue(core)

    disk = None
    if standalone:
        # in-shader walker reads the disk out of RAM at DISK_PA
        DISK_PA = 0x81600000
        for i in range(SECTOR // 4):
            w32(core, DISK_PA + i * 4, struct.unpack("<I", PATTERN[i*4:i*4+4])[0])
    else:
        fd, path = tempfile.mkstemp(suffix=".img"); os.close(fd)
        Path(path).write_bytes(PATTERN + b"\x00" * SECTOR)
        disk = path
        core.queue.write_buffer(core.state_buffer, 43 * 4,
                                struct.pack("<I", 2))       # vq_ready = 2

    core.step(200)
    st = core.get_state()
    print(f"[step] pc=0x{st['pc']:x} halted={st['halted']}")

    ok = True
    if standalone:
        if st["halted"] not in (0, 1):
            print(f"  FAIL: expected halted 0/1, got {st['halted']}"); ok = False
    else:
        if st["halted"] != 2:
            print(f"  FAIL: offload expected yield halted==2, got {st['halted']}"); ok = False
        else:
            state_arr = __import__("numpy").frombuffer(
                core.queue.read_buffer(core.state_buffer), dtype="uint32")
            cfg = QueueConfig(state_arr)
            print(f"  latched desc=0x{cfg.desc:x} avail=0x{cfg.avail:x} used=0x{cfg.used:x} num={cfg.num}")
            if (cfg.desc, cfg.avail, cfg.used) != (DESC, AVAIL, USED):
                print(f"  FAIL: ring addrs != expected "
                      f"(0x{DESC:x}/0x{AVAIL:x}/0x{USED:x})"); ok = False
            ram = GpuRam(core, RAM_BASE)
            blk = VirtioBlkHost(disk_path=disk)
            n = blk.service_queue(ram, cfg)
            blk.close()
            print(f"  service_queue processed {n}")
            if n != 1:
                print("  FAIL: expected 1 request"); ok = False
            core.queue.write_buffer(core.state_buffer, 2 * 4, struct.pack("<I", 0))
            core.step(50)
            st2 = core.get_state()
            print(f"  after resume: pc=0x{st2['pc']:x} halted={st2['halted']}")
            if st2["halted"] != 1:
                print("  FAIL: core did not reach ecall halt after resume"); ok = False

    data = b"".join(struct.pack("<I", r32(core, DATA_BUF + i * 4)) for i in range(SECTOR // 4))
    status = r32(core, STATUS_BUF) & 0xFF
    used_idx = r32(core, USED) >> 16
    used_id = r32(core, USED + 4)
    print(f"  data[:8]={data[:8].hex()}  status={status}  used.idx={used_idx}  used.id={used_id}")

    if data != PATTERN:
        print(f"  FAIL: data buffer != disk pattern"); ok = False
    if status != 0:
        print(f"  FAIL: status byte {status} != 0"); ok = False
    if used_idx != 1:
        print(f"  FAIL: used.idx {used_idx} != 1"); ok = False
    if used_id != 0:
        print(f"  FAIL: used.ring[0].id {used_id} != 0"); ok = False

    if disk:
        os.unlink(disk)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--standalone", action="store_true",
                    help="test in-shader process_virtqueue_spatial (vq_ready=0, 64MB core)")
    raise SystemExit(run(ap.parse_args().standalone))
