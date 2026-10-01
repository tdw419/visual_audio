#!/usr/bin/env python3
"""BM903 step 2: the PXC1-convention medium (rung-4 codec EXTENDED to 13.6 MiB).

 rung-4/rung-5 put a <=1 MiB stage2 on the medium as four consecutive planes:
 payload byte i -> medium byte 512 + (i%4)*PLANE + i//4, PLANE = len/4. The
 guest reads 8-sector chunks per plane and re-interleaves them (one 64 KiB
 destination bank at a time), CRC32-gating the whole decoded payload before it
 hands control over. That design tops out at PAYLOAD_MAX = 1 MiB and at banks
 that fit under 1 MiB of REAL-mode RAM. Ours is 13.6 MiB, so two things change
 and nothing else does:

   * the walk runs in stage2's FLAT-32 phase, so destination banks are no
     longer limited to the first megabyte -- they are the kernel's own load
     address and the initrd address;
   * the payload is a concatenation of sub-images, each a whole number of
     16 KiB interleave groups, so "which destination?" is a per-group lookup
     instead of per-byte arithmetic.

Byte->pixel mapping is untouched (medium byte B == pixel (B%16384)//4 row
B//16384 channel B%4, i.e. the medium is a truncated RGBA frame); the medium
here stops at the last used sector instead of padding out to 64 MiB.

Emits bm903_px_layout.inc (nasm defines), bm903_crc32tab.inc (the reflected
0xEDB88320 table the guest uses -- so host and guest arithmetic are the SAME
table, not two implementations that happen to agree), and the payload bytes
themselves for the image builder to interleave.
"""
import json
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
KERNEL = HERE / "vmlinuz64.extracted"
INITRD = HERE.parent / "rung7" / "core.gz"
SECTOR = 512
CHUNK_BYTES = 4096           # one read of CHUNK_SECTORS=8 sectors, one plane
GROUP_BYTES = 4 * CHUNK_BYTES  # 16 KiB of decoded payload per group
BANK_BYTES = 4 * GROUP_BYTES   # rung-4's 64 KiB bank, kept as the outer stride
PATTERN = bytes([0xA5, 0x5A, 0xC3, 0x3C, 0x0F, 0xF0, 0x33, 0xCC,
                 0x81, 0x7E, 0x18, 0xE7, 0x42, 0xBD, 0x69, 0x96])
HDR_SCRATCH = 0x20000
KERNEL_ENTRY = 0x100000
INITRD_ADDR = 0x10000000
SINK = 0x34000               # where filler groups land (CRC still covers them)
PLANES = 4


def crc32_tab():
    tab = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (0xEDB88320 ^ (c >> 1)) if (c & 1) else (c >> 1)
        tab.append(c & 0xFFFFFFFF)
    return tab


def groups(n):
    return (n + GROUP_BYTES - 1) // GROUP_BYTES


def build_payload():
    """Returns (payload bytes, sub-image table of (group, ngroups, dst))."""
    kern = KERNEL.read_bytes()
    assert kern[0x202:0x206] == b'HdrS'
    setup_sects = kern[0x1f1]
    setup_bytes = (setup_sects + 1) * SECTOR
    pm = kern[setup_bytes:]
    initrd = INITRD.read_bytes()

    subs = []

    def chunk(blob, dst):
        g = groups(len(blob))
        subs.append((blob, g, dst))
        return g

    g_hdr = chunk(kern[:setup_bytes], HDR_SCRATCH)
    g_kern = chunk(pm, KERNEL_ENTRY)
    g_init = chunk(initrd, INITRD_ADDR)
    total = g_hdr + g_kern + g_init
    pad_groups = (-total) % 4                     # whole banks only
    payload = kern[:setup_bytes].ljust(g_hdr * GROUP_BYTES, b'\0')
    payload += pm.ljust(g_kern * GROUP_BYTES, b'\0')
    payload += initrd.ljust(g_init * GROUP_BYTES, b'\0')
    payload += (PATTERN * (pad_groups * GROUP_BYTES // 16 + 1))[:pad_groups * GROUP_BYTES]
    table = [(0, g_hdr, HDR_SCRATCH), (g_hdr, g_kern, KERNEL_ENTRY),
             (g_hdr + g_kern, g_init, INITRD_ADDR)]
    assert len(payload) % BANK_BYTES == 0
    return payload, table, len(initrd), len(pm)


def encode(stage1: bytes, stage2: bytes, payload: bytes, base_lba: int) -> bytes:
    plane = len(payload) // PLANES
    med = bytearray((base_lba + PLANES * (plane // SECTOR)) * SECTOR)
    med[0:512] = stage1
    med[512:512 + len(stage2)] = stage2
    for p in range(PLANES):
        start = base_lba * SECTOR + p * plane
        med[start:start + plane] = payload[p::PLANES]
    return bytes(med)


def decode(med: bytes, base_lba: int, payload_len: int) -> bytes:
    plane = payload_len // PLANES
    out = bytearray(payload_len)
    for p in range(PLANES):
        start = base_lba * SECTOR + p * plane
        out[p::PLANES] = med[start:start + plane]
    return bytes(out)


def main() -> int:
    payload, table, initrd_len, pm_len = build_payload()
    ngroups = len(payload) // GROUP_BYTES
    banks = len(payload) // BANK_BYTES
    plane = len(payload) // PLANES
    base_lba = 1 + 16                          # stage1 + 16 sectors of stage2
    crc = zlib.crc32(payload) & 0xFFFFFFFF

    # codec self-test BEFORE anything consumes it: decode(encode(x)) == x
    s1 = (HERE / "bm903_stage1.bin").read_bytes() if (HERE / "bm903_stage1.bin").exists() else b'\0' * 512
    s2 = (HERE / "bm903_stage2_px.bin").read_bytes() if (HERE / "bm903_stage2_px.bin").exists() else b''
    med = encode(s1, s2, payload, base_lba)
    assert decode(med, base_lba, len(payload)) == payload, 'codec round-trip BROKEN'
    assert len(med) == (base_lba + PLANES * (plane // SECTOR)) * SECTOR

    (HERE / "bm903_px_payload.bin").write_bytes(payload)
    (HERE / "bm903_px_meta.json").write_text(json.dumps({
        "convention": "PXC1 (rung-4 four-plane interleave), truncated frame",
        "planes": PLANES, "base_lba": base_lba, "sector": SECTOR,
        "chunk_sectors": CHUNK_BYTES // SECTOR, "group_bytes": GROUP_BYTES,
        "bank_bytes": BANK_BYTES, "payload_len": len(payload),
        "groups": ngroups, "banks": banks, "plane_bytes": plane,
        "plane_sectors": plane // SECTOR,
        "subimages": [{"start_group": g, "groups": n, "dst": hex(d),
                       "src": name}
                      for (g, n, d), name in zip(table,
                                                 ["kernel setup+header",
                                                  "kernel pm payload",
                                                  "initrd"])],
        "filler_groups": ngroups - sum(t[1] for t in table),
        "sink": hex(SINK),
        "payload_crc32": f"{crc:08X}",
        "payload_sha256": __import__('hashlib').sha256(payload).hexdigest(),
        "initrd_bytes": initrd_len, "pm_bytes": pm_len,
    }, indent=1) + '\n')

    rows = []
    for g, n, d in table:
        rows.append(f"%define SUB{len(rows)}_GROUP {g}\n"
                    f"%define SUB{len(rows)}_NGROUPS {n}\n"
                    f"%define SUB{len(rows)}_DEST {hex(d)}")
    (HERE / "bm903_px_layout.inc").write_text(
        "; generated by bm903_pxcodec.py -- DO NOT EDIT\n"
        f"%define PX_BASE_LBA {base_lba}\n"
        f"%define PX_PLANE_SECTORS {plane // SECTOR}\n"
        f"%define PX_CHUNK_SECTORS {CHUNK_BYTES // SECTOR}\n"
        f"%define PX_GROUP_BYTES {GROUP_BYTES}\n"
        f"%define PX_GROUPS {ngroups}\n"
        f"%define PX_BANKS {banks}\n"
        f"%define PX_PAYLOAD_BYTES {len(payload)}\n"
        f"%define PB0 0x30000\n%define PB1 0x31000\n"
        f"%define PB2 0x32000\n%define PB3 0x33000\n"
        f"%define PX_SINK {hex(SINK)}\n"
        f"%define PX_SUBIMAGE_COUNT {len(table)}\n"
        + "\n".join(rows) + "\n"
        f"%define EXPECTED_CRC 0x{crc:08X}\n"
        f"%define INITRD_BYTES {initrd_len}\n"
        f"%define HDR_SCRATCH {hex(HDR_SCRATCH)}\n")
    tab = crc32_tab()
    lines = ["; reflected CRC32 table (poly 0xEDB88320) -- host and guest share it"]
    for i in range(0, 256, 4):
        lines.append("  dd " + ", ".join(f"0x{v:08X}" for v in tab[i:i + 4]))
    (HERE / "bm903_crc32tab.inc").write_text("\n".join(lines) + "\n")
    print(f"px payload {len(payload)} B = {ngroups} groups = {banks} banks, "
          f"plane {plane} B ({plane // SECTOR} sectors), base LBA {base_lba}, "
          f"medium {len(med) // SECTOR} sectors, CRC={crc:08X}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
