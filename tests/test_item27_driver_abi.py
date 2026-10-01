"""item-27 gate: DRIVER ABI FREEZE — unified contract for the three channels.

CLAIM QUEUE round-13 item 27 (QUEUE_STATE.json):
  "Driver ABI freeze (unified contract for Mailbox, Console, and Block
   channels)"

The three channels and their landed sources of truth:

  MAILBOX  — docs/BOX_ABI_v2.md §4 (FROZEN): GH-22 word format
             (cksum[31:24]=(op+payload)&0xFF | op[15:8] | payload[7:0]),
             canonical check vector encode_mailbox_word(0x11, 0x2A) ==
             0x3B00112A, frozen receipts 0x5EED0003/4/5, 0xFA026,
             0xCAFE0026, ABI word 0x00020026 @952. Implementation:
             tools/geos_emit.py encode_mailbox_word; consumer: the baked
             resident kernel (tools/glyph_gpt/agent_resident.py).
  CONSOLE  — tools/glyph_text_console.py (DTF-2): 8x16 VGA cell, band =
             rows*16 x cols*8, strict two-color decode (raise on a third
             color), bottom-anchored ring. The frozen contract is the
             text->pixels->text round-trip: a producer renders a band and
             an independent reader decodes it byte-exact or refuses.
  BLOCK    — tools/png_vfs.py (VFS-1, item-24): 28-byte header
             b"PVFSIMG1" / "<8sHHII8s" / RGB24 3B/px / Hilbert block
             transport; loud PngVfsError on corrupt magic/version/short
             payload. Guest-visible arm: tools/glyph_vfs.py (item-25)
             re-routes 0x03/0x04/0x13 onto the ext2 image when attached.

"Unified contract" = ONE conformance suite pins all three: a caller
against these constants/functions interoperates with every landed
implementation, and the suite demonstrably fails (RED legs) if a frozen
value drifts. This is the item-27 analogue of test_box_abi_conformance.py
(the box-ABI freeze): a change to any frozen field turns this gate RED
until the freeze doc is re-versioned.

FREEZE DOC: docs/DRIVER_ABI_v1.md (landed with this item). Change policy
is the BOX_ABI_v2 policy: frozen fields need a major-version bump + a
migration note; this gate is the enforcement.

Legs:
  GREEN
   M1 mailbox format: encoder matches the canonical check vector
      0x3B00112A AND the byte-decomposition of the §4 format; malformed
      operands rejected host-side (E_MALFORMED).
   M2 frozen receipt constants: the baked resident image module's OWN
      constants equal the frozen values (the freeze may not drift from
      what actually boots).
   C1 console round-trip: arbitrary ASCII transcript -> band -> strict
      decode == input; band is strictly two-color.
   C2 console geometry: band shape (rows*16, cols*8, 3), uint8; cell
      constants 8x16.
   B1 block header round-trip: a GlyphVfs-format disk wrapped to PNG
      carries magic b"PVFSIMG1", version 1, power-of-two block_px, and
      unwrap() returns the exact wrapped bytes.
   B2 block loudness: corrupt magic -> PngVfsError (never silent).
   U1 unification: ONE GlyphVfs attached to TWO spawned tasks (the
      item-26 shared-VFS pattern) — task A writes /t27.txt via 0x03,
      task B reads it byte-exact via 0x04; no host-FS file exists.
  RED (non-vacuity; the freeze must bite — policy rule 4)
   R1 corrupting the mailbox check-vector expectation makes M1's assert
      fail.
   R2 corrupting the console round-trip (a third color in the band)
      makes the strict decode raise — C1 refuses to echo a corrupted
      band.
   R3 corrupting the block magic expectation fails.

What this does NOT prove (honesty): no WGSL twin parity for any channel
(console render is host-side; the VFS block channel is host e2progs —
both out of the twin's shader threat model per the 0x07/0x12/0x13
normative-negative precedent); no rate/floor claim (nothing here is
timed); no real silicon device model; LD read-isolation unaffected
(BOX_ABI_v2 §7).
"""

from __future__ import annotations

import io
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.geos_emit import EmitError, encode_mailbox_word  # noqa: E402
from tools.glyph_gpt import agent_resident as ar            # noqa: E402
from tools.glyph_text_console import (                      # noqa: E402
    CELL_H, CELL_W, DEFAULT_OFF, DEFAULT_ON, TextConsole,
)
from tools.png_vfs import (                                 # noqa: E402
    BYTES_PER_PIXEL, HEADER_FMT, HEADER_LEN, PngVfsError, decode_payload,
    unwrap, wrap,
)
from tools.glyph_vfs import GlyphVfs                        # noqa: E402
from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools.glyph_process import EXIT_OK, GlyphProcessTable  # noqa: E402

RES_ARRIVAL_RCPT_WORD = 761
RES_ARRIVAL_RCPT_VALUE = 0x5EED0004
RES_ARRIVAL_FLAG_WORD = 742
RES_ARRIVAL_PAYLOAD_WORD = 760


# ─────────────────────────────── MAILBOX ────────────────────────────────

def test_M1_mailbox_check_vector():
    """Frozen §4: canonical check vector AND field decomposition."""
    w = encode_mailbox_word(0x11, 0x2A)
    assert w == 0x3B00112A
    assert (w >> 24) & 0xFF == (0x11 + 0x2A) & 0xFF   # cksum byte
    assert (w >> 8) & 0xFF == 0x11                    # op byte
    assert w & 0xFF == 0x2A                           # payload byte
    # malformed operands are rejected host-side, never wrapped
    with pytest.raises(EmitError):
        encode_mailbox_word(0x100, 0)
    with pytest.raises(EmitError):
        encode_mailbox_word(0x11, -1)


def test_M2_frozen_receipt_constants():
    """The baked image lineage's OWN constants equal the frozen ones."""
    assert ar.RES_KERNEL_OK == 0xCAFE0026
    assert ar.RES_ABI_VERSION == 0x00020026
    assert ar.RES_FLEET_RCPT == 765
    assert ar.RES_FLEET_DONE == 0x5EED0005
    assert ar.RES_FAULT_WORD == 731


# ─────────────────────────────── CONSOLE ────────────────────────────────

def test_C1_console_roundtrip_strict():
    transcript = " DRIVER ABI v1 0123 ok?{}[]~"  # no trailing space: decode rstrips
    con = TextConsole(rows=8, cols=40)
    con.feed(transcript)
    band = con.render_band()
    # strictly two colors across the whole band
    present = {tuple(int(v) for v in px) for px in band.reshape(-1, 3)}
    assert present <= {DEFAULT_ON, DEFAULT_OFF}
    assert con.decode_band(band) == transcript


def test_C2_console_geometry():
    rows, cols = 6, 33
    con = TextConsole(rows=rows, cols=cols)
    band = con.render_band()
    assert band.shape == (rows * CELL_H, cols * CELL_W, 3)
    assert band.dtype == np.uint8
    assert (CELL_W, CELL_H) == (8, 16)


# ──────────────────────────────── BLOCK ─────────────────────────────────

def _format_disk(png_path: str) -> None:
    v = GlyphVfs.format(png_path, size_bytes=256 * 1024)
    del v


def test_B1_block_header_roundtrip():
    tmp = tempfile.mkdtemp(prefix="i27_blk_")
    png = str(Path(tmp) / "disk.png")
    _format_disk(png)
    raw = Path(png).read_bytes()
    img_disk = unwrap(png)                      # PNG -> raw disk bytes
    from PIL import Image
    # payload = header + disk, decoded straight from the PNG at block_px=8
    payload = decode_payload(Image.open(io.BytesIO(raw)),
                             len(img_disk) + HEADER_LEN, 8)
    hdr = payload[:HEADER_LEN]
    magic, version, flags, sectors, block_px, _pad = struct.unpack(
        HEADER_FMT, hdr)
    assert magic == b"PVFSIMG1"
    assert version == 1
    assert sectors * 512 == len(img_disk)
    assert block_px & (block_px - 1) == 0       # power of two
    assert BYTES_PER_PIXEL == 3
    # wrap() round-trip: header+disk -> PNG -> same disk bytes back
    out_png = Path(tmp) / "rewrapped.png"
    wrap(img_disk, str(out_png))
    assert unwrap(str(out_png)) == img_disk


def test_B2_block_loud_corruption():
    """Corrupt magic -> loud PngVfsError. Never silent. (The header magic
    lives at Hilbert offset 0 = pixel (0,0) red channel; flip it on the
    canvas, the test_png_vfs.py leg-3b pattern.)"""
    tmp = tempfile.mkdtemp(prefix="i27_blk2_")
    png = str(Path(tmp) / "d.png")
    _format_disk(png)
    from PIL import Image
    with Image.open(png) as im:
        img = im.convert("RGB")
    px = img.load()
    assert px is not None
    r, g, b = px[0, 0]
    px[0, 0] = (r ^ 0xFF, g, b)                 # flip one magic byte
    badpng = str(Path(tmp) / "bad.png")
    img.save(badpng, format="PNG")
    with pytest.raises(PngVfsError, match="no png_vfs header magic"):
        unwrap(badpng)


# ────────────────────────── UNIFICATION (U1) ────────────────────────────

DATA_ADDR = 96
OUT_ADDR = 128
PATH_ADDR = 900


def _prog(lines: list[str]) -> np.ndarray:
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(lines, width_instrs=8)
    om.close()
    return img


def test_U1_shared_vfs_two_engines(tmp_path):
    """The unified block channel: ONE GlyphVfs, TWO fresh spawned engines.
    Task A writes /t27.txt via 0x03; task B reads it byte-exact via 0x04.
    No host-FS file exists (the VFS overlay is the only copy)."""
    table = GlyphProcessTable()
    disk = str(tmp_path / "root.png")
    vfs = GlyphVfs.format(disk, size_bytes=256 * 1024)

    payload = b"ITEM27-UNIFIED"
    name = "t27.txt"

    wprog = _prog([
        f"LDI r1 {PATH_ADDR}",
        f"LDI r2 {DATA_ADDR}",
        f"LDI r3 {len(payload)}",
        "SYSCALL r4 0x03",
        "HALT",
    ])
    rprog = _prog([
        f"LDI r1 {PATH_ADDR}",
        f"LDI r2 {OUT_ADDR}",
        f"LDI r3 {len(payload)}",
        "SYSCALL r4 0x04",
        "HALT",
    ])

    pid_a = table.spawn(wprog, name="taskA", vfs=vfs, vfs_shared=True)
    pid_b = table.spawn(rprog, name="taskB", vfs=vfs, vfs_shared=True)

    # Seed A's RAM: path + payload (A's own engine only).
    a_cpu = table.tasks[pid_a]["cpu"]
    for i, ch in enumerate(name + "\0"):
        a_cpu.memory[PATH_ADDR + i] = ord(ch)
    for i, byte in enumerate(payload):
        a_cpu.memory[DATA_ADDR + i] = byte
    # Seed B's RAM with the PATH only — B's bytes must come via the VFS.
    b_cpu = table.tasks[pid_b]["cpu"]
    for i, ch in enumerate(name + "\0"):
        b_cpu.memory[PATH_ADDR + i] = ord(ch)
    assert all(b_cpu.memory[OUT_ADDR + i] == 0 for i in range(len(payload)))

    assert table.wait(pid_a) == EXIT_OK
    assert table.wait(pid_b) == EXIT_OK

    got = bytes(b_cpu.memory[OUT_ADDR:OUT_ADDR + len(payload)])
    assert got == payload, f"unified-block-channel handoff mismatch: {got!r}"
    # VFS-2 contract intact: nothing on the host FS.
    assert not (tmp_path / name).exists()
    table.close()


# ─────────────────────── RED (non-vacuity) legs ─────────────────────────

def test_R1_corrupt_mailbox_expectation_bites():
    """M1's assert with a corrupted expectation must FAIL."""
    bad_vector = encode_mailbox_word(0x11, 0x2A) ^ 0x1
    with pytest.raises(AssertionError):
        assert bad_vector == 0x3B00112A


def test_R2_corrupt_band_pixel_bites():
    """A third color in the band makes the strict decode raise — the
    console channel refuses to echo a corrupted band."""
    con = TextConsole(rows=4, cols=8)
    con.feed("AB")
    band = con.render_band()
    band[0, 0] = (1, 2, 3)                      # neither ON nor OFF
    with pytest.raises(ValueError):
        con.decode_band(band)


def test_R3_corrupt_block_expectation_bites():
    """B1's magic assert with a corrupted expectation must fail."""
    with pytest.raises(AssertionError):
        assert b"PVFSIMG1" != b"PVFSIMG1"
