#!/usr/bin/env python3
"""BM905 packet codec: fixed 16-byte mailbox slots (brief step 1, LOCKED).

Layout (little-endian), CRC-16/ARC over bytes 0..13:
  magic u16 0x0DB5 | seq u32 | type u8 | code u16 | value u16 | crc16 u16
Ring of SLOTS=256 slots in the reserved window; slot i holds seq seq0+i.
Types: 1=EV_KEY press (auto-release by daemon), 2=EV_KEY release, 3=EV_SYN.
"""
import struct

MAGIC = 0x0DB5
SLOT = 16
SLOTS = 256
TYPE_PRESS = 1
TYPE_RELEASE = 2
TYPE_SYN = 3


def crc16(data: bytes) -> int:
    """CRC-16/ARC (poly 0xA001 reflected, init 0x0000) — matches the rung-4/5
    loader's checksum family, implemented directly (no deps)."""
    crc = 0x0000
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def encode(seq: int, typ: int, code: int, value: int) -> bytes:
    """LOCKED 16-byte slot layout (no implicit alignment pads):
    bytes 0-1 magic u16 | 2-5 seq u32 | 6 type u8 | 7 spare u8 | 8-9 code u16
    | 10-11 value u16 | 12-13 reserved u16 (zero) | 14-15 crc16 over bytes
    [0,14)."""
    body = struct.pack("<HIBBHHH", MAGIC, seq & 0xFFFFFFFF, typ, 0,
                       code & 0xFFFF, value & 0xFFFF, 0)
    assert len(body) == 14, len(body)  # 2+4+1+1+2+2+2 = 14 (fixed 2026-09-19: format was "<HIBBHH" = 12)
    return body + struct.pack("<H", crc16(body))


def decode(slot16: bytes):
    """-> (seq, type, code, value) or None if magic/CRC invalid (skip+count)."""
    if len(slot16) != SLOT:
        return None
    (crc,) = struct.unpack("<H", slot16[14:16])
    if slot16[:2] != struct.pack("<H", MAGIC) or crc != crc16(slot16[:14]):
        return None
    _, seq, typ, _, code, value, _ = struct.unpack("<HIBBHHH", slot16[:14])
    return seq, typ, code, value


def paint_window(base_byte: int, packets: list[bytes]) -> bytes:
    """Window image: 256 zero slots, packets laid at slot (seq % SLOTS).
    Packets are the full 16 B (14 B body + u16 CRC); paint_window zero-pads
    the ring."""
    buf = bytearray(SLOT * SLOTS)
    for p in packets:
        assert len(p) == SLOT, f"packet must be 16 B, got {len(p)}"
        (seq,) = struct.unpack("<I", p[2:6])
        buf[(seq % SLOTS) * SLOT:(seq % SLOTS) * SLOT + SLOT] = p
    return bytes(buf)


def packet_bytes(buf: bytes, base_byte: int, seq: int) -> bytes:
    """The 16 bytes at the slot seq maps to (for the predictor)."""
    i = (seq % SLOTS) * SLOT
    return buf[i:i + SLOT]
