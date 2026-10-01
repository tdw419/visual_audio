#!/usr/bin/env python3
"""BM903 step 2: build the PXC1 pixel medium and PROVE the guest walk on the
host before a single byte is booted.

The proof is the point of this file. `guest_walk` below is written against the
numbers in bm903_px_layout.inc -- the very text bm903_stage2_px.asm %includes --
not against bm903_pxcodec.py's python constants, and it replays the loader's
inner loop literally: plane chunk LBA = BASE + group*CHUNK + plane*PLANE_SECTORS,
quad j decodes to bytes 4j..4j+3 from PB0..PB3, destination = sub-image table
entry + (group - entry start)*GROUP_BYTES. So an addressing drift between the
codec and the asm is caught here as an assertion, not later as a kernel that
boots into garbage.

Refuses to write the medium unless:
  * decode(encode(payload)) == payload                  (codec round-trip)
  * the replayed walk reproduces the payload byte order (walk == codec)
  * every sub-image destination receives exactly its own group range
  * the CRC8 macro's arithmetic == zlib.crc32 on the same bytes (one algorithm)
  * EXPECTED_CRC in the .inc == zlib.crc32(payload)     (the gate's constant)
"""
import json
import re
import subprocess
import sys
import zlib
from pathlib import Path

import bm903_pxcodec as codec

HERE = Path(__file__).resolve().parent
OUT = HERE / "bm903_medium_px.raw"
INC = HERE / "bm903_px_layout.inc"


def nasm(src: str, dst: str) -> bytes:
    r = subprocess.run(["nasm", "-f", "bin", "-o", dst, "-I", str(HERE) + "/",
                        str(HERE / src)], capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(f"nasm {src} FAILED:\n{r.stderr}{r.stdout}\n")
        raise SystemExit(2)
    if r.stderr.strip():
        sys.stderr.write(f"nasm {src} warnings:\n{r.stderr}\n")
        raise SystemExit(2)          # gate S1 requires a warning-free assemble
    return Path(dst).read_bytes()


def consts() -> dict:
    text = INC.read_text()
    out = {}
    for m in re.finditer(r"^%define (\w+) (-?0x[0-9A-Fa-f]+|\d+)$", text, re.M):
        out[m.group(1)] = int(m.group(2), 0)
    for name in ("PX_BASE_LBA", "PX_PLANE_SECTORS", "PX_CHUNK_SECTORS",
                 "PX_GROUP_BYTES", "PX_GROUPS", "PX_SINK", "EXPECTED_CRC",
                 "PB0", "SUB0_GROUP", "SUB0_NGROUPS", "SUB0_DEST",
                 "SUB1_GROUP", "SUB1_NGROUPS", "SUB1_DEST",
                 "SUB2_GROUP", "SUB2_NGROUPS", "SUB2_DEST"):
        assert name in out, f"{name} missing from {INC.name}"
    return out


def sub_table(c: dict):
    return [(c[f"SUB{i}_GROUP"], c[f"SUB{i}_GROUP"] + c[f"SUB{i}_NGROUPS"],
             c[f"SUB{i}_DEST"]) for i in range(3)]


def dest_for(group: int, table, sink):
    """Exactly the px_dst loop: first entry with start <= g < end, else sink."""
    for start, end, dst in table:
        if start <= group < end:
            return dst, start
    return sink, None


def guest_walk(med: bytes, c: dict):
    """Replay bm903_stage2_px.asm's walk. Returns (decoded payload, regions)."""
    gb, chunk, plane_s, base = (c["PX_GROUP_BYTES"], c["PX_CHUNK_SECTORS"],
                                c["PX_PLANE_SECTORS"], c["PX_BASE_LBA"])
    table = sub_table(c)
    regions, out = {}, []
    for g in range(c["PX_GROUPS"]):
        planes = []
        for p in range(4):
            lba = base + g * chunk + p * plane_s
            off = lba * 512
            blk = med[off:off + chunk * 512]
            assert len(blk) == chunk * 512, f"group {g} plane {p} runs off the end"
            planes.append(blk)
        # byte 4j+p == PBp[j], written as slices: identical to the asm's
        # `mov al,[PBp+ecx] / mov [ebp+ecx*4+p],al` loop, ~1000x faster.
        decoded = bytearray(gb)
        for p in range(4):
            decoded[p::4] = planes[p]
        decoded = bytes(decoded)
        dst, start = dest_for(g, table, c["PX_SINK"])
        if start is None:
            # bank padding: px_dst returns the bare sink, so every filler group
            # re-covers the same 16 KiB. Only the last one survives.
            regions[dst] = decoded
        else:
            buf = regions.setdefault(dst, bytearray())
            want = (g - start) * gb
            assert len(buf) == want, \
                f"group {g}: dst {dst:#x} had {len(buf)} B, expected {want} B " \
                f"(table or stride drift)"
            buf += decoded
        out.append(decoded)
    return b"".join(out), regions, table


def crc8_matches_zlib(payload: bytes, c: dict) -> None:
    """The CRC8 macro is PX_PAYLOAD_BYTES iterations of
    `idx=(crc^b)&0xFF; crc=(crc>>8)^TAB[idx]` over the DECODED stream -- the
    whole stream, not a sample, because the running state is the thing under
    test. Compare it to zlib on the same bytes."""
    tab = codec.crc32_tab()
    crc = 0xFFFFFFFF
    for b in payload:
        idx = (crc ^ b) & 0xFF
        crc = (crc >> 8) ^ tab[idx]
    mine = crc ^ 0xFFFFFFFF
    ref = zlib.crc32(payload) & 0xFFFFFFFF
    assert mine == ref, f"CRC8 macro {mine:08X} != zlib {ref:08X} on the same bytes"
    assert mine == c["EXPECTED_CRC"], \
        f"macro/zlib {mine:08X} != the gate constant {c['EXPECTED_CRC']:08X}"


def main() -> int:
    lay = json.loads((HERE / "bm903_layout.json").read_text())
    s2 = nasm("bm903_stage2_px.asm", "bm903_stage2_px.bin")
    s1 = nasm("bm903_stage1.asm", "bm903_stage1.bin")   # byte-identical to step 1
    assert len(s1) == 512 and s1[-2:] == b"\x55\xaa", "stage1 must be an MBR"
    step1_s1 = HERE / "bm903_stage1.bin"
    if step1_s1.exists():
        assert s1 == step1_s1.read_bytes(), \
            "stage1 changed between step 1 and step 2 -- the medium's front end " \
            "must be the same code that already passed the step-1 gate"
    st2 = lay["stage2_sectors"] * 512
    assert len(s2) == st2, f"stage2_px is {len(s2)} B, must be {st2}"

    c = consts()
    inc_tab = []
    for line in (HERE / "bm903_crc32tab.inc").read_text().splitlines():
        line = line.strip()
        if line.startswith("dd "):
            inc_tab += [int(t, 0) for t in line[3:].split(",")]
    assert len(inc_tab) == 256 and inc_tab == codec.crc32_tab(), \
        "guest CRC table != host CRC table"
    payload, table, initrd_len, pm_len = codec.build_payload()
    assert len(payload) == c["PX_GROUPS"] * c["PX_GROUP_BYTES"], "group count drift"
    med = codec.encode(s1, s2, payload, c["PX_BASE_LBA"])

    assert codec.decode(med, c["PX_BASE_LBA"], len(payload)) == payload, \
        "codec round-trip BROKEN"
    decoded, regions, tbl = guest_walk(med, c)
    assert decoded == payload, "guest-walk replay != payload (byte order or LBA math)"
    for start, end, dst in tbl:                 # tbl entries are (start, end, dst)
        want = payload[start * c["PX_GROUP_BYTES"]:end * c["PX_GROUP_BYTES"]]
        assert len(regions[dst]) == len(want), \
            f"sub-image at {dst:#x}: {len(regions[dst])} B != {len(want)} B"
        assert bytes(regions[dst]) == want, f"sub-image at {dst:#x} mis-slotted"
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    assert crc == c["EXPECTED_CRC"], \
        f"gate constant stale: payload CRC {crc:08X} != .inc {c['EXPECTED_CRC']:08X}"
    crc8_matches_zlib(payload, c)
    assert len(med) == (c["PX_BASE_LBA"] + 4 * c["PX_PLANE_SECTORS"]) * 512

    OUT.write_bytes(med)
    print(f"wrote {OUT.name}: {len(med)} B = {len(med)//512} sectors, "
          f"payload {len(payload)} B / {c['PX_GROUPS']} groups, "
          f"CRC={crc:08X}; walk replay + sub-image slotting + CRC parity all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
