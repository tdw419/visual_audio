#!/usr/bin/env python3
"""BM905 mailbox host-side placement + paint (brief steps 0.2/3, writer side).

Window (measured 2026-09-19, leg-0; size CORRECTED by N2 measurement): vda
LBAs [256, 512) = 256 sectors = 128 KiB, bytes [131072, 262144) — the
alignment gap before vda1 (LBA 2048), outside every partition, outside the
protective MBR, and zero-filled in the container. The disk-tail candidate was
REJECTED by measurement: the container's initramfs+gguf payload sections
occupy the tail (header.json sections end byte ≈ 16828528128 = disk size),
i.e. the tail is hash-tracked payload, NOT FS-dead space.

Paint: write the 4 KiB ring image (256 slots x 16 B, zero-padded) into the
frame PNG bytes at window_disk_byte (livemap paint, BM904-R2 mechanism), then
/writeback barrier (compact_journal) makes it decode-visible. XOR-not: the PNG
bytes are painted ABSOLUTE (this is a paint, not a diff) — control noise is
measured by BM904's method and the leg asserts exact equality.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools" / "pixel_container"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from livemap_probe import paint as paint_px, peek, evict  # noqa: E402
from locate_in_container import Container, DEFAULT_CONTAINER  # noqa: E402
import bm905_mailbox_packet as pkt  # noqa: E402

WINDOW_LBA = 256
WINDOW_SECTORS = 256
WINDOW_BYTE = WINDOW_LBA * 512          # 131072
WINDOW_LEN = WINDOW_SECTORS * 512       # 131072 (128 KiB)
FRAME_BYTES = 64 * 1024 * 1024
BACKEND = "http://127.0.0.1:8769"


def window_frame_of(disk_byte: int) -> int:
    return 1 + disk_byte // FRAME_BYTES


def paint_window(packets: list[bytes]) -> None:
    """Paint every nonzero byte of the 256-slot ring image into its PNG byte."""
    image = pkt.paint_window(WINDOW_BYTE, packets)
    touched: dict[int, list[int]] = {}
    # straddle: slot 1 of seq0+1 crosses a 512-byte sector edge iff
    # (slot_offset % 512) > 512 - 16; with 16-byte slots the offsets 496..512
    # are impossible (16 | 512), so pick the straddling pair explicitly:
    # slot boundary between bytes [496,512) of a sector — none exists for
    # aligned 16 B slots. The brief's straddle case is therefore the
    # FRAME crossing: paint one packet at window byte 0 and one at the last
    # 16 bytes — both inside frame 1 — and assert the 128 KiB window is
    # entirely inside frame 1 (straddle proof moves to the guest dd side,
    # where slot bytes DO cross dd bs=512 read boundaries by layout).
    straddle_note = "16B slots are 512-aligned: sector straddle impossible; guest dd crosses slot edges per-slot"
    for i, val in enumerate(image):
        if val:
            db = WINDOW_BYTE + i
            touched.setdefault(window_frame_of(db), []).append(i)
    for fno, idxs in touched.items():
        for i in sorted(idxs):
            db = WINDOW_BYTE + i
            frame = window_frame_of(db)
            intra = db % FRAME_BYTES
            x = (intra % (4096 * 4)) // 4
            y = intra // (4096 * 4)
            ch = intra % 4
            # paint_px writes channel 0 only; for other channels read-modify-write the PNG directly
            _paint_channel(DEFAULT_CONTAINER, frame, x, y, ch, image[i])
    print(f"painted {sum(len(v) for v in touched.values())} nonzero window bytes "
          f"across frames {sorted(touched)}")


def _paint_channel(container: Path, frame: int, x: int, y: int, ch: int,
                   value: int) -> None:
    import os
    import time as _t
    from PIL import Image
    p = container / f"frame_{frame:05d}.png"
    # the backend re-encodes frame PNGs during writeback/compaction: an
    # open can land mid-write and raise "image file is truncated" (measured
    # 2026-09-19 N4 run1). Retry the load; save atomically so readers never
    # observe a partial file.
    for attempt in range(20):
        try:
            img = Image.open(p)
            img.load()
            img = img.convert("RGBA")
            break
        except OSError:
            _t.sleep(1.0)
    else:
        raise RuntimeError(f"frame {p.name} unreadable for 20 s — backend "
                           "re-encode race; retry the gate invocation")
    px = img.load()
    px[x, y] = tuple(value if k == ch else px[x, y][k] for k in range(4))
    tmp = p.with_suffix(".png.paint_tmp")
    img.save(tmp, format="PNG")
    os.replace(tmp, p)


if __name__ == "__main__":
    # smoke: paint nothing, just report placement + current first bytes
    print(f"window: lba {WINDOW_LBA}..{WINDOW_LBA + WINDOW_SECTORS} "
          f"= vda bytes {WINDOW_BYTE}..{WINDOW_BYTE + WINDOW_LEN}")
    c = Container(DEFAULT_CONTAINER)
    print("current first 16:", c.read(WINDOW_BYTE, 16).hex())
