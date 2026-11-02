#!/usr/bin/env python3
"""livemap_probe — standing regression gate for PXC1 live-mapped reads.

Proves end-to-end that a running virtio_pixel_backend serves host-painted PNG
bytes through the guest-equivalent disk read path (HTTP /peek), including
across decoder-LRU eviction. This is the behavior measured 2026-09-18
(16-frame lazy LRU, re-decode from current PNG on miss — see skill
pixel-container-pxc1 and the memory note on PXC1 live-mapping).

Legs (all reversible, one marker byte, cold frame):
  0. heal    — if the pinned byte still holds a MARKER from a crashed prior
               run, restore the pinned original first (self-healing).
  1. baseline— read disk byte D via /peek, record original value, pin it.
  2. paint   — write MARKER into the frame PNG at D (host-side, PIL).
  3. cold-read — /peek D must return MARKER (frame never in cache: immediate).
  4. evict   — force 20 cold-frame decodes through the same LRU, then /peek D
               must STILL return MARKER (proves re-decode from PNG, i.e. the
               live map, not a stale cache).
  5. restore — write original byte back, /peek D must return original.
     (Frame file sha will differ from pre-run due to PNG re-encode
     nondeterminism; the guest-visible byte is the contract, and format
     integrity is pxc1-verify's job — run that separately after any FAIL.)

Usage:
  python3 livemap_probe.py [--backend http://127.0.0.1:8769]
                           [--container DIR] [--pin-file PATH]

Exit 0 = all legs green. Exit 1 = FAIL with the leg named; leave the marker
in place ONLY on crash-between-legs — the next run's heal step removes it.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BYTES_PER_FRAME = 67108864          # 4096*4096*4 RGBA
FRAME_SIZE = 4096
MARKERS = (0xAB, 0x5A)              # first not equal to the original wins

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CONTAINER = REPO / "ubuntu_desktop_pxc1_v3_selfhost"
DEFAULT_PIN = Path("/tmp/livemap_probe_pin.json")


def peek(backend: str, addr: int, attempts: int = 4) -> int:
    """One disk byte through the backend's own extractor (guest-equivalent).

    Retries transient failures: the HTTP plane is single-threaded and every
    request takes the extractor mutex — a journal compaction holds that mutex
    for ~35s (measured), so peeks during a fold block or reset. That is
    normal co-tenancy with a live guest, not an outage.
    """
    import socket as _s
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(f"{backend}/peek?addr={addr}&size=1", timeout=90) as r:
                word = r.read().decode().split()[0]
                return int(word[-2:], 16)   # little-endian word: last byte is addr+0
        except (urllib.error.URLError, TimeoutError, _s.timeout, ConnectionError) as e:
            last = e
            time.sleep(2 + 3 * i)
    raise RuntimeError(f"/peek failed after {attempts} attempts: {last}")


def frame_xych(disk_byte: int):
    frame = 1 + disk_byte // BYTES_PER_FRAME          # frame 0 = metadata
    intra = disk_byte % BYTES_PER_FRAME
    return frame, (intra % (FRAME_SIZE * 4)) // 4, intra // (FRAME_SIZE * 4), intra % 4


def paint(container: Path, frame: int, x: int, y: int, value: int) -> None:
    from PIL import Image
    p = container / f"frame_{frame:05d}.png"
    img = Image.open(p).convert("RGBA")
    data = bytearray(img.tobytes())
    data[(y * FRAME_SIZE + x) * 4] = value
    Image.frombytes("RGBA", (FRAME_SIZE, FRAME_SIZE), bytes(data)).save(p)


def evict(backend: str, container: Path) -> None:
    """Force >LRU-capacity cold-frame decodes to push any cached frame out.

    Frames MUST be valid (< header total_frames): a peek past the end returns
    handler-padded zeros WITHOUT decoding, so it inserts nothing into the LRU
    (measured 2026-09-18: frames 252+ of a 252-frame container are no-ops,
    which silently gutted the eviction leg). 24 valid frames > 16-frame
    decoder capacity, with margin.
    """
    total = json.loads((container / "header.json").read_text())["total_frames"]
    assert total > 26, f"container too small to evict: {total} frames"
    for k in range(24):
        frame = 2 + (k % (total - 3))       # skip frame 0 (metadata) + margin
        peek(backend, frame * BYTES_PER_FRAME + 512)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="http://127.0.0.1:8769")
    ap.add_argument("--container", default=str(DEFAULT_CONTAINER))
    ap.add_argument("--pin-file", default=str(DEFAULT_PIN))
    ap.add_argument("--disk-byte", type=int, default=15367933952,   # frame 230, pixel (1024,0) ch R — measured cold 2026-09-18
                    help="raw vda byte to probe (defaults to the pinned cold frame)")
    a = ap.parse_args()

    container = Path(a.container)
    pin = {}
    pf = Path(a.pin_file)
    if pf.exists():
        pin = json.loads(pf.read_text())
        a.disk_byte = pin["disk_byte"]

    frame, x, y, ch = frame_xych(a.disk_byte)
    marker = next(m for m in MARKERS if m != pin.get("orig", 0xAB) or "orig" not in pin)

    # Leg 0: heal a crashed prior run. Evict FIRST — a painted byte reads
    # stale until its frame leaves the LRU, so verification without eviction
    # would see the marker's own shadow and skip the restore.
    if pin.get("orig") is not None and "marker" in pin:
        evict(a.backend, container)
        cur = peek(a.backend, a.disk_byte)
        if cur == pin["marker"] and cur != pin["orig"]:
            paint(container, frame, x, y, pin["orig"])
            evict(a.backend, container)
            cur = peek(a.backend, a.disk_byte)
            print(f"heal: restored {pin['orig']:#04x} from crashed run -> now {cur:#04x}")
            if cur != pin["orig"]:
                print("FAIL heal: restore did not surface"); return 1
    cur = peek(a.backend, a.disk_byte)

    # Leg 1: baseline + pin
    orig = cur
    pin.update(disk_byte=a.disk_byte, orig=orig, marker=marker)
    pf.write_text(json.dumps(pin))
    if orig in MARKERS:                       # pathological: original IS a marker
        print(f"FAIL baseline: original byte {orig:#04x} collides with markers — pick another --disk-byte"); return 1
    print(f"baseline: disk_byte={a.disk_byte} frame={frame} pixel=({x},{y}) ch={ch} orig={orig:#04x} marker={marker:#04x}")

    # Leg 2+3: evict (frame may be LRU-hot from prior reads) -> paint -> read
    evict(a.backend, container)
    paint(container, frame, x, y, marker)
    t0 = time.time()
    got = peek(a.backend, a.disk_byte)
    if got != marker:
        print(f"FAIL cold-read: painted {marker:#04x}, backend served {got:#04x} (live map broken or frame cached stale)"); return 1
    print(f"cold-read: MARKER served ({time.time()-t0:.2f}s) ✓")

    # Leg 4: evict -> read (re-decode from PNG is THE property under test)
    evict(a.backend, container)
    got = peek(a.backend, a.disk_byte)
    if got != marker:
        print(f"FAIL post-evict: served {got:#04x} after cold decodes — re-decode-from-PNG regression"); return 1
    print("post-evict: MARKER served after LRU eviction ✓")

    # Leg 5: restore -> evict -> verify
    paint(container, frame, x, y, orig)
    evict(a.backend, container)
    got = peek(a.backend, a.disk_byte)
    if got != orig:
        print(f"FAIL restore: served {got:#04x}, expected {orig:#04x}"); return 1
    print(f"restore: original {orig:#04x} served ✓")
    print("LIVEMAP GATE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
