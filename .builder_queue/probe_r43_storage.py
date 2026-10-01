#!/usr/bin/env python3
"""R4.3 storage: block device with the writeback contract, ENOSPC-safe.

PRODUCT_ROADMAP.md:75 (R4.3).

Approach mirrors the R4.1 input-device probe: a HOST-SIDE device seat
built entirely over LANDED substrate channels — zero production lines
changed.

  guest -> device  : the guest storage client posts BLOCK REQUESTS into
                     live RAM between step() calls (the mailbox ABI).
                     Request slot (word addresses, plain-RAM region):
                       BLK_CMD     3100  (1=WRITE, 2=READ, 3=FLUSH; 0=idle)
                       BLK_SECTOR  3101
                       BLK_STATUS  3102  (0=OK, 1=ENOSPC, 2=E_IO)
                       BLK_DATA0   3108  (payload word in / out)
                     The guest writes SECTOR then DATA then CMD last;
                     the seat (host) services any nonzero CMD between
                     steps, writes STATUS, clears CMD. The guest polls
                     CMD==0 (bounded, r10 budget — R1.1 discipline).
  device -> host   : a backing FILE on the host filesystem. Writeback
                     contract: WRITE lands in the seat's dirty cache
                     ONLY; the backing file is written (atomically:
                     tmp + os.replace, the R3.2 container pattern) on
                     FLUSH — and on clean halt (unmount). A seat that
                     never flushes leaves the file empty: --no-flush
                     turns that into the RED leg.
  ENOSPC-safe      : capacity is N_BLOCKS=8 sectors BY CONSTRUCTION
                     (the contract is tested, not the host disk): a
                     WRITE to sector >= 8 returns STATUS=1 (ENOSPC),
                     the guest logs the error and CONTINUES; committed
                     sectors are untouched. No crash, no silent
                     truncation, no real disk exhaustion (measured:
                     /home at 98% — the rung's own hazard).

GREEN contract (exit 0), CPU engine (GlyphCPUv2 oracle):
  - status log (10 jobs) matches [0,0,0,0,0,0, 0(flush), 0(read),
    1(ENOSPC), 0(flush)];
  - the read-back payload (job 8, sector 3) equals the written word;
  - the BACKING FILE (read host-side, not guest RAM) holds all 6
    committed sectors word-exact with valid per-sector checksums;
  - the out-of-range write left every committed sector intact;
  - the 0xAA sentinel beyond the guest's log survives.

RED legs (each exits 1 = RED by contract, shown before green):
  --no-flush      : the seat never persists (no flush, no unmount
                    write); the host-side persistence check must
                    REJECT the empty backing file (writeback contract
                    is load-bearing).
  --torn-block    : ONE byte of one committed sector is flipped in the
                    backing file post-write; the checksum check must
                    REJECT it (torn-write detection).
  --corrupt-verify: the verifier checks the good run against WRONG
                    expected payloads; it must REJECT (discrimination).

What PASS does NOT prove: no real block hardware (the device channel
is the mailbox ABI + a host file, not virtio-blk); NO WGSL shader-path
leg (request servicing needs a per-step host hook — the same measured
gap R4.1 recorded; run_wgsl runs to HALT in one call); no filesystem
(no directory tree, no names — this is the raw block layer); no rate
or floor claims (nothing here quotes a rate).
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from tools.glyph_isa_v2 import (                      # noqa: E402
    OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2,
)

# ── device contract ──────────────────────────────────────────────────────
N_BLOCKS = 8            # sectors 0..7
BLOCK_WORDS = 16        # payload words per sector (only DATA0 exercised)
OP_WRITE, OP_READ, OP_FLUSH = 1, 2, 3
ST_OK, ST_ENOSPC, ST_EIO = 0, 1, 2
MAGIC = b"GBD1"

# ── memory map (word addresses; plain-RAM region; no production words) ──
BLK_CMD = 3100
BLK_SECTOR = 3101
BLK_STATUS = 3102
BLK_DATA0 = 3108
LOG_COUNT = 3296
LOG_BASE = 3300         # one packed word per job: (sector<<8)|status
RD_PAYLOAD = 3350       # guest copies READ's DATA0 here
JOBS = 3200             # 4 words per job: op, sector, payload, pad
SENTINEL_ADDR = 3400
SENTINEL = 0xAA
MAX_STEPS = 60000

# ── job script (op, sector, payload, expected_status) ────────────────────
PAYLOADS = {
    0: 0x11110001, 1: 0x22220002, 2: 0x33330004,
    3: 0x44440008, 4: 0x55550010, 5: 0x66660020,
}
JOBSPEC = (
    [(OP_WRITE, s, PAYLOADS[s], ST_OK) for s in range(6)]
    + [(OP_FLUSH, 0, 0, ST_OK)
                                  # read back sector 3, expect payload
       , (OP_READ, 3, 0, ST_OK)
                                  # out-of-range write: ENOSPC surfaced
       , (OP_WRITE, N_BLOCKS, 0xDEAD0008, ST_ENOSPC)
       , (OP_FLUSH, 0, 0, ST_OK)]
)
EXPECTED_STATUSES = [j[3] for j in JOBSPEC]
N_JOBS = len(JOBSPEC)
READ_SECTOR = 3
READ_EXPECT = PAYLOADS[READ_SECTOR]

GUEST_PROG = [
    "LDI r6 0",           # r6 = zero constant
    "LDI r5 3200",        # job pointer
    "LDI r8 0",           # jobs completed
    "LDI r10 8000",       # bounded poll budget
    ":job",
    "LDI r4 10",
    "CMP r8 r4",
    "JZ :done",           # all jobs serviced -> halt cleanly
    "CMP r10 r6",
    "JZ :done",           # budget exhausted -> halt with what we have
    "LD r1 r5",           # op = job+0
    "CMP r1 r6",
    "JZ :done",           # op-0 terminator (safety)
    "LDI r4 1",
    "ADD r4 r5",
    "LD r2 r4",           # sector = job+1
    "LDI r4 2",
    "ADD r4 r5",
    "LD r3 r4",           # payload = job+2
    # ---- post the request: SECTOR, DATA0, then CMD last ----
    "LDI r7 3101",
    "ST r7 r2",
    "LDI r7 3108",
    "ST r7 r3",
    "LDI r7 3100",
    "ST r7 r1",
    ":wait",
    "CMP r10 r6",
    "JZ :done",
    "LDI r7 3100",
    "LD r9 r7",
    "CMP r9 r6",
    "JZ :serviced",
    "LDI r4 1",
    "SUB r10 r4",
    "JMP :wait",
    ":serviced",
    "LDI r7 3102",
    "LD r9 r7",           # status from the seat
    # ---- log[done] = (sector<<8)|status; count++ ----
    "LDI r4 8",
    "SHL r2 r4",
    "OR r2 r9",           # r2 = packed log word
    "LDI r7 3296",
    "LD r9 r7",           # count
    "LDI r7 3300",        # LOG_BASE (into r7 — the ADD's base register)
    "ADD r7 r9",          # LOG_BASE + count
    "ST r7 r2",
    "LDI r4 1",
    "ADD r9 r4",
    "LDI r7 3296",
    "ST r7 r9",
    # ---- READ: copy DATA0 payload out for host verification ----
    "LDI r4 2",
    "CMP r1 r4",
    "JZ :copy",
    "JMP :next",
    ":copy",
    "LDI r7 3108",
    "LD r9 r7",
    "LDI r7 3350",
    "ST r7 r9",
    ":next",
    "LDI r4 4",
    "ADD r5 r4",          # job ptr += 4
    "LDI r4 1",
    "ADD r8 r4",
    "LDI r4 1",
    "SUB r10 r4",
    "JMP :job",
    ":done",
    "LDI r7 3400",
    "LD r9 r7",           # sentinel: guest reads it, never writes it
    "HALT",
]


def _assemble():
    om = OpcodeMapV2()
    return om, GlyphAssemblerV2(om).assemble(GUEST_PROG, width_instrs=8)


# ── backing file format ──────────────────────────────────────────────────
# MAGIC | u32 n_blocks | u32 block_words
# | per sector: block_words data words + 1 checksum word (sum & 0xFFFFFFFF)
# checksum 0 on an all-zero sector = never-written; any nonzero payload
# yields a nonzero checksum, so written-vs-unwritten is decidable.

def _sectors_from_file(path: Path):
    raw = path.read_bytes()
    if raw[:4] != MAGIC:
        raise ValueError(f"bad magic in {path}")
    import struct
    nb, bw = struct.unpack_from("<II", raw, 4)
    if nb != N_BLOCKS or bw != BLOCK_WORDS:
        raise ValueError(f"geometry mismatch: {nb}x{bw}")
    words = list(struct.unpack_from(f"<{nb * (bw + 1)}I", raw, 12))
    sectors = {}
    for s in range(nb):
        base = s * (bw + 1)
        data = words[base:base + bw]
        csum = words[base + bw]
        sectors[s] = (data, csum)
    return sectors


def _write_backing_file(path: Path, sectors: dict[int, int]) -> None:
    import struct
    buf = bytearray()
    buf += MAGIC
    buf += struct.pack("<II", N_BLOCKS, BLOCK_WORDS)
    for s in range(N_BLOCKS):
        # only DATA0 is exercised by the job script; a full multi-word
        # sector payload is the same loop with more guest stores.
        data = [sectors.get(s, 0)] + [0] * (BLOCK_WORDS - 1)
        buf += struct.pack(f"<{BLOCK_WORDS + 1}I", *data,
                           (sum(data)) & 0xFFFFFFFF)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(bytes(buf))
    os.replace(tmp, path)          # atomic: torn tmp is ignored on read


def _seed_memory(mem: list[int]) -> None:
    for i, (op, sec, pay, _st) in enumerate(JOBSPEC):
        b = JOBS + 4 * i
        mem[b], mem[b + 1], mem[b + 2], mem[b + 3] = op, sec, pay, 0
    mem[JOBS + 4 * N_JOBS] = 0     # op-0 terminator
    mem[LOG_COUNT] = 0
    mem[RD_PAYLOAD] = 0
    mem[BLK_CMD] = 0
    mem[BLK_STATUS] = 0
    mem[BLK_DATA0] = 0
    mem[SENTINEL_ADDR] = SENTINEL


def run_python(workdir: Path) -> dict:
    """Run the storage client on the reference engine; the seat services
    block requests between step() calls (mailbox ABI)."""
    om, img = _assemble()
    cpu = GlyphCPUv2(om, cols_instrs=8, fs_pix_enabled=True)
    cpu.memory = [0] * 16384
    _seed_memory(cpu.memory)
    cpu.running = True
    steps = 0
    serviced = {"write": 0, "read": 0, "flush": 0, "enospc": 0}
    dirty: dict[int, int] = {}
    committed = 0
    no_flush = "--no-flush" in sys.argv
    backing = workdir / "blockdev.gbd"

    def flush() -> int:
        nonlocal committed
        if no_flush:
            return 0
        _write_backing_file(backing, dirty)
        committed = len(dirty)
        return 1

    def service() -> None:
        if cpu.memory[BLK_CMD] == 0:
            return
        op = cpu.memory[BLK_CMD]
        sec = cpu.memory[BLK_SECTOR]
        if op == OP_WRITE:
            if sec >= N_BLOCKS:
                cpu.memory[BLK_STATUS] = ST_ENOSPC
                serviced["enospc"] += 1
            else:
                dirty[sec] = cpu.memory[BLK_DATA0]
                cpu.memory[BLK_STATUS] = ST_OK
                serviced["write"] += 1
        elif op == OP_READ:
            if sec >= N_BLOCKS:
                cpu.memory[BLK_STATUS] = ST_ENOSPC
                serviced["enospc"] += 1
            else:
                cpu.memory[BLK_DATA0] = dirty.get(sec, 0)
                cpu.memory[BLK_STATUS] = ST_OK
                serviced["read"] += 1
        elif op == OP_FLUSH:
            flush()
            cpu.memory[BLK_STATUS] = ST_OK
            serviced["flush"] += 1
        else:
            cpu.memory[BLK_STATUS] = ST_EIO
        cpu.memory[BLK_CMD] = 0

    while cpu.running and not cpu.faulted and steps < MAX_STEPS:
        cpu.step(img)
        steps += 1
        service()
    # unmount flush on a clean halt (the writeback contract's unmount leg)
    if not no_flush and not cpu.running:
        flush()
    if cpu.faulted:
        raise RuntimeError(f"python engine faulted: {cpu.fault_reason}")
    return {"halted": not cpu.running, "steps": steps, "serviced": serviced,
            "committed": committed, "backing": str(backing),
            "ram": list(cpu.memory)}


def verify(rec: dict, workdir: Path, corrupt: bool = False,
           torn: bool = False) -> tuple[bool, str]:
    ram = rec["ram"]
    if corrupt:
        exp_status = [s ^ 0x5A for s in EXPECTED_STATUSES]
        exp_read = READ_EXPECT ^ 0x5A5A5A5A
    else:
        exp_status, exp_read = EXPECTED_STATUSES, READ_EXPECT
    if ram[LOG_COUNT] != N_JOBS:
        return False, f"log count {ram[LOG_COUNT]} != {N_JOBS}"
    want_log = [(JOBSPEC[i][1] << 8) | exp_status[i] for i in range(N_JOBS)]
    got_log = ram[LOG_BASE:LOG_BASE + N_JOBS]
    if got_log != want_log:
        return False, f"status log {got_log} != {want_log}"
    if ram[RD_PAYLOAD] != exp_read:
        return False, (f"read-back {ram[RD_PAYLOAD]:#010x} != "
                       f"{exp_read:#010x}")
    if ram[SENTINEL_ADDR] != SENTINEL:
        return False, "sentinel overwritten — log overran"
    # host-side persistence check over the BACKING FILE (not guest RAM)
    backing = Path(rec["backing"])
    if not backing.exists():
        return False, "backing file MISSING — writeback never persisted"
    if torn:
        raw = bytearray(backing.read_bytes())
        # flip one byte inside committed sector READ_SECTOR's payload
        off = 12 + READ_SECTOR * (BLOCK_WORDS + 1) * 4 + 1
        raw[off] ^= 0xFF
        backing.write_bytes(bytes(raw))
    sectors = _sectors_from_file(backing)
    for s in range(6):
        data, csum = sectors[s]
        if sum(data) & 0xFFFFFFFF != csum:
            return False, (f"torn write: sector {s} checksum "
                           f"{csum:#010x} != {sum(data) & 0xFFFFFFFF:#010x}")
        expect = [READ_EXPECT ^ 0x5A5A5A5A] if corrupt else [PAYLOADS[s]]
        expect = expect + [0] * (BLOCK_WORDS - 1)
        if corrupt:
            expect = [(w ^ 0x5A5A5A5A) for w in expect]
        if data != expect:
            return False, f"sector {s} data mismatch: {data[0]:#010x}"
    # the ENOSPC write must NOT have landed anywhere: sector payloads are
    # the exact 6 committed words and nothing else (checked above)
    return True, (f"{rec['committed']} sectors persisted, checksums valid, "
                  f"read-back word-exact, ENOSPC surfaced cleanly "
                  f"({rec['serviced']})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-flush", action="store_true",
                    help="RED leg: seat never persists; the host-side "
                         "persistence check must reject")
    ap.add_argument("--torn-block", action="store_true",
                    help="RED leg: one byte of a committed sector flipped "
                         "post-write; checksum must reject")
    ap.add_argument("--corrupt-verify", action="store_true",
                    help="RED leg: verify the good run against wrong "
                         "expectations")
    args = ap.parse_args()

    print(f"R4.3 storage probe: no_flush={args.no_flush} "
          f"torn_block={args.torn_block} corrupt_verify={args.corrupt_verify} "
          f"engine=python(CPU oracle)")

    with tempfile.TemporaryDirectory(prefix="r43_storage_") as d:
        workdir = Path(d)
        rec = run_python(workdir)
        print(f"R4.3 seat serviced {rec['serviced']} in {rec['steps']} steps; "
              f"halted={rec['halted']} committed={rec['committed']}")

        if args.corrupt_verify:
            ok, detail = verify(rec, workdir, corrupt=True)
            if ok:
                print("R4.3 FAIL-RED: corrupted expectations ACCEPTED — "
                      "verifier NOT load-bearing")
                return 1
            print("R4.3 corrupt-verify RED leg: verifier REJECTED the good "
                  f"run under wrong expectations (correct discrimination): "
                  f"{detail}")
            return 1

        if args.no_flush:
            ok, detail = verify(rec, workdir)
            if ok:
                print("R4.3 FAIL-RED: unflushed data PASSED the persistence "
                      "check — writeback contract NOT load-bearing")
                return 1
            print("R4.3 no-flush RED leg: the seat skipped the writeback "
                  f"and the persistence check REJECTED (data loss detected): "
                  f"{detail}")
            return 1

        if args.torn_block:
            ok, detail = verify(rec, workdir, torn=True)
            if ok:
                print("R4.3 FAIL-RED: a torn sector PASSED the checksum "
                      "check — torn-write detection NOT load-bearing")
                return 1
            print("R4.3 torn-block RED leg: the flipped byte REJECTED by "
                  f"the sector checksum (torn write detected): {detail}")
            return 1

        ok, detail = verify(rec, workdir)
        if not ok:
            print(f"R4.3 STORAGE: FAIL: {detail}")
            return 1
        print(f"R4.3 STORAGE: MATCH ({detail}) — block device with the "
              f"writeback contract, ENOSPC-safe, host-verified")
        return 0


if __name__ == "__main__":
    sys.exit(main())
