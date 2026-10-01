#!/usr/bin/env python3
"""BM905 guest listener daemon (brief step 2, reader/injector side).

Runs INSIDE the guest (deployed to /var/tmp, root via sudo channel):
  - polls the reserved window on its own /dev/vda via dd (direct if allowed)
  - parses 16-byte packets (bm905_mailbox_packet layout, reimplemented here —
    the guest has no repo checkout; the byte layout is the LOCKED interface)
  - tracks last_seq; strictly-newer valid packets are injected through
    /dev/uinput on BM905-Mailbox-Keyboard (press auto-pairs release)
  - appends JSONL testimony to /var/tmp/bm905_testify.jsonl
  - skips+counts malformed (magic/CRC) slots — never injects them
  - bounded lifetime (--max-seconds), clean exit for the gate

Usage: python3 bm905_guest_listener.py --window-lba 256 --max-seconds 300
"""
import argparse
import fcntl
import json
import os
import struct
import subprocess
import sys
import time

MAGIC = 0x0DB5
SLOT = 16
SLOTS = 256
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
EV_KEY = 0x01
EV_SYN = 0x00
DEV_NAME = b"BM905-Mailbox-Keyboard"


def crc16(data: bytes) -> int:
    crc = 0x0000
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def read_window(lba: int, sectors: int, direct: bool) -> bytes:
    cmd = ["dd", "if=/dev/vda", "bs=512", f"skip={lba}", f"count={sectors}"]
    if direct:
        cmd.append("iflag=direct")
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    if r.returncode != 0 and direct:
        return read_window(lba, sectors, False)
    return r.stdout


def setup_uinput():
    fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_SYN)
    for k in range(1, 248):  # full keycode range: the host picks keys, not us
        try:
            fcntl.ioctl(fd, UI_SET_KEYBIT, k)
        except OSError:
            pass
    setup = struct.pack("<80sHHHHI", DEV_NAME, 0x06, 0xB905, 1, 0, 0)
    setup += struct.pack("<64i", *([0] * 64)) * 4
    os.write(fd, setup)
    fcntl.ioctl(fd, UI_DEV_CREATE)
    return fd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-lba", type=int, default=256)
    ap.add_argument("--window-sectors", type=int, default=256)
    ap.add_argument("--max-seconds", type=int, default=300)
    ap.add_argument("--poll-ms", type=int, default=200)
    ap.add_argument("--testify", default="/var/tmp/bm905_testify.jsonl")
    args = ap.parse_args()

    ufd = setup_uinput()
    last_seq = 0
    injected = skipped = 0
    t_end = time.monotonic() + args.max_seconds

    def emit(t, c, v):
        os.write(ufd, struct.pack("<qqHHi", 0, 0, t, c, v))

    def testify(rec):
        with open(args.testify, "a") as f:
            f.write(json.dumps(rec) + "\n")

    def dump_stats():
        # Leg E polls this WHILE the daemon runs — must be periodic, not
        # exit-only (measured gap: exit-only stats made the leg unsatisfiable).
        with open("/var/tmp/bm905_daemon_stats.json", "w") as f:
            json.dump({"injected": injected, "skipped_malformed": skipped,
                       "last_seq": last_seq}, f)

    try:
        while time.monotonic() < t_end:
            try:
                data = read_window(args.window_lba, args.window_sectors, True)
            except Exception as e:  # dd timeout etc. under a live fold —
                print(f"read failed: {e}", file=sys.stderr, flush=True)
                time.sleep(1)       # keep polling, never die mid-gate
                continue
            dump_stats()
            if len(data) < SLOTS * SLOT:
                time.sleep(args.poll_ms / 1000)
                continue
            cands = []
            for i in range(SLOTS):
                slot = data[i * SLOT:(i + 1) * SLOT]
                # LOCKED layout: body = magic(2)+seq(4)+type(1)+spare(1)+
                # code(2)+value(2)+reserved(2) = 14 B, CRC16 over [0,14) at
                # [14:16). (Fixed 2026-09-19: was slot[:10]+CRC@10 — a
                # different layout than the host codec writes.)
                got = slot[:14]
                magic, seq, typ, _, code, value, _ = struct.unpack("<HIBBHHH", got)
                (crc,) = struct.unpack("<H", slot[14:16])
                if magic != MAGIC or crc != crc16(got):
                    if any(slot):
                        skipped += 1
                    continue
                if seq > last_seq:
                    cands.append((seq, typ, code, value))
            # Process the pass in ASCENDING SEQ order, not slot order: ring
            # placement (seq % 256) can map a newer seq to a LOWER slot
            # (measured gate v2: SYN seq0+10 at slot 18 poisoned slots
            # 232-234 holding seq0..seq0+2 — monotonic dedup requires
            # seq-order dispatch).
            cands.sort()
            changed = False
            for seq, typ, code, value in cands:
                if seq <= last_seq:
                    continue
                if typ in (1, 2):
                    emit(EV_KEY, code, 1 if typ == 1 else 0)
                    emit(EV_SYN, 0, 0)
                    if typ == 1:  # auto-paired release: press+release is one packet
                        emit(EV_KEY, code, 0)
                        emit(EV_SYN, 0, 0)
                    testify({"seq": seq, "type": typ, "code": code,
                             "mono_ts": time.monotonic()})
                    injected += 1
                    changed = True
                elif typ == 3:
                    testify({"seq": seq, "type": 3, "code": code,
                             "mono_ts": time.monotonic()})
                last_seq = seq
            if not changed:
                time.sleep(args.poll_ms / 1000)
        return 0
    finally:
        try:
            fcntl.ioctl(ufd, UI_DEV_DESTROY)
        except OSError:
            pass
        os.close(ufd)
        with open("/var/tmp/bm905_daemon_stats.json", "w") as f:
            json.dump({"injected": injected, "skipped_malformed": skipped,
                       "last_seq": last_seq}, f)


if __name__ == "__main__":
    sys.exit(main())
