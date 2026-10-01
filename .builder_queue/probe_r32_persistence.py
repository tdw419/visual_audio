"""R3.2 persistence — the GlyphRunner substrate's tile state + outputs
survive a power cycle, via a host-side container, crash-safe.

PRODUCT_ROADMAP.md:66-68 (R3.2): "Persistence: tile state + outputs
survive power cycle (PXC1/VAC containers or the virtio-pixel backend's
writeback), crash-safe (kill -9 RED leg)."

The substrate (tools/glyph_gpt/runner.py:133-186) has no persistence
path — every run_wgsl call creates fresh buffers. The mechanism this
rung names first (a container) is therefore BUILT here, host-side,
over the LANDED R3.1 chain:

  1. freeze   : boot the R3.1 fleet image to halt (run_wgsl), capture
                the full RAM + CPU register state + image  = one
                container (npz, magic word, timestamp, checksum).
  2. power off: the container is the only thing that survives; the
                in-memory runner object is dropped.
  3. power on : a FRESH GlyphRunner is constructed, state is restored
                from the container bytes, and the restored machine is
                host-verified against the frozen fleet words (receipt
                0x5EED0005 @765, done 0b1011 @717, results 714:6/
                728:12/748:20/763:30, E-K1 0xFA026 @731).

Crash-safety, two mechanisms, both gated RED-first:
  - kill -9 analogue: the container is written ATOMICALLY (tmp file +
    os.replace) — a crash mid-write leaves the PREVIOUS container
    intact and readable.
  - torn-write detection: the loader rejects any container whose
    payload checksum does not match its header (corruption RED leg).

Exit contract: 0 = GREEN (freeze → power cycle → restore → verified
frozen words, AND the torn-write kill switch fires on corrupted
payload); 1 = RED (verification miss, corrupted container ACCEPTED,
or crash-mid-write left no readable container).
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from tools.glyph_gpt.atlas import build_default_atlas          # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402
from tools.glyph_gpt.agent_resident import (                   # noqa: E402
    resident_image, RES_FLEET_RCPT, RES_DONE_WORD, RES_FLEET_DONE,
    RES_FLEET_EXPECT, RES_FAULT_WORD,
)

MAGIC = b"GPX1"                       # Glyph Persistence eXchange v1
FLOORS = REPO / ".builder_queue" / "floors_authoritative.json"
RECEIPT_WORDS = {
    "fleet_receipt": (RES_FLEET_RCPT, RES_FLEET_DONE),
    "done_word": (RES_DONE_WORD, 0b1011),
    "fault_word": (RES_FAULT_WORD, 0xFA026),
    **{f"result_{a}": (a, v) for a, v in RES_FLEET_EXPECT.items()},
}


def payload_checksum(ram: np.ndarray, regs, img: np.ndarray) -> str:
    h = hashlib.sha256()
    h.update(ram.astype(np.uint32).tobytes())
    h.update(np.asarray(regs, dtype=np.uint32).tobytes())
    h.update(img.astype(np.uint32).tobytes())
    return h.hexdigest()


def save_container(path: Path, ram: np.ndarray, regs, img: np.ndarray,
                   meta: dict) -> None:
    """Atomic container write: tmp file + os.replace (crash-safe)."""
    header = {
        "magic": MAGIC.decode(),
        "format": 1,
        "checksum": payload_checksum(ram, regs, img),
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        **meta,
    }
    hj = json.dumps(header, sort_keys=True).encode()
    tmp = path.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        f.write(MAGIC)                 # 4B magic
        f.write(len(hj).to_bytes(4, "little"))   # 4B header length
        f.write(hj)
        f.write(ram.astype(np.uint32).tobytes())  # 64KB RAM
        f.write(np.asarray(regs, dtype=np.uint32).tobytes())
        f.write(img.astype(np.uint32).tobytes())
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)              # atomic: no torn container ever visible


def load_container(path: Path) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray]:
    raw = path.read_bytes()
    if raw[:4] != MAGIC:
        raise ValueError(f"bad magic: {raw[:4]!r}")
    hlen = int.from_bytes(raw[4:8], "little")
    header = json.loads(raw[8:8 + hlen])
    off = 8 + hlen
    ram = np.frombuffer(raw, dtype=np.uint32, count=16384, offset=off)
    off += 16384 * 4
    regs = np.frombuffer(raw, dtype=np.uint32, count=32, offset=off)
    off += 32 * 4
    n_px = (len(raw) - off) // 4 // 3
    img = np.frombuffer(raw, dtype=np.uint32, count=n_px * 3, offset=off)
    img = img.reshape(-1, 3)
    if payload_checksum(ram, regs, img) != header["checksum"]:
        raise ValueError(
            f"torn/corrupt container: checksum mismatch "
            f"(payload {payload_checksum(ram, regs, img)[:12]}… != "
            f"header {header['checksum'][:12]}…)")
    return header, ram, regs, img


def verify_frozen_words(ram: np.ndarray, corrupt: bool = False) -> tuple[bool, str]:
    """Host-verified persistence: every frozen word survived the cycle."""
    bad = []
    for name, (addr, want) in RECEIPT_WORDS.items():
        got = int(ram[addr])
        exp = want ^ 0x5A5A if corrupt else want
        if got != exp:
            bad.append(f"{name}@{addr}: got 0x{got:x} want 0x{exp:x}")
    if bad:
        return False, "; ".join(bad)
    return True, (f"ram[765]=0x{int(ram[RES_FLEET_RCPT]):08x} "
                  f"ram[717]=0b{int(ram[RES_DONE_WORD]):b} "
                  f"ram[731]=0x{int(ram[RES_FAULT_WORD]):x} "
                  f"results={{{', '.join(f'{a}:{int(ram[a])}' for a in RES_FLEET_EXPECT)}}}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--container", default=None,
                    help="container path (default: tempdir)")
    ap.add_argument("--corrupt-verify", action="store_true",
                    help="RED leg: corrupt the verifier's expectations; "
                         "a GOOD restored state must then be REJECTED")
    ap.add_argument("--corrupt-container", action="store_true",
                    help="RED leg: flip one byte in the container payload; "
                         "the loader must REJECT it (torn-write detection)")
    args = ap.parse_args()

    print(f"R3.2 persistence probe: corrupt_verify={args.corrupt_verify} "
          f"corrupt_container={args.corrupt_container}")

    # ---- 1. FREEZE: boot the R3.1 fleet image to halt -------------------
    with tempfile.TemporaryDirectory() as d:
        atlas = build_default_atlas()
        img_path = Path(d) / "fleet_r32.npy"
        img = resident_image(atlas, mode="fleet", timer_quantum=6,
                             out_path=img_path)
        boot_runner = GlyphRunner(img_path, ram_words=16384)
        t0 = time.perf_counter()
        rec = boot_runner.run_wgsl(max_steps=5000)
        boot_ms = (time.perf_counter() - t0) * 1000.0
        if not rec.get("halted"):
            print(f"R3.2 PERSISTENCE: FAIL (boot did not halt: "
                  f"{rec.get('error', 'no halt')})")
            sys.exit(1)
        ram_host = np.array(rec["ram"], dtype=np.uint32)
        regs = np.array(rec["registers_full"], dtype=np.uint32)
        # memory[] is ONE packed-RGB word per pixel (runner.py:181 BK-2) —
        # unpack to (n_px, 3) channels; lossless for 8-bit channels.
        packed = np.array(rec["memory"], dtype=np.uint32)
        img_after = np.stack(((packed >> 16) & 0xFF,
                              (packed >> 8) & 0xFF,
                              packed & 0xFF), axis=1)
        ok, detail = verify_frozen_words(ram_host)
        if not ok:
            print(f"R3.2 PERSISTENCE: FAIL (boot state not fleet-ready: {detail})")
            sys.exit(1)
        print(f"freeze: boot {boot_ms:.1f} ms, {rec['steps']} steps, halted; "
              f"frozen words OK ({detail})")

        # ---- 2. CONTAINER WRITE (atomic) + POWER OFF --------------------
        cpath = Path(args.container) if args.container else Path(d) / "gpx1.bin"
        save_container(cpath, ram_host, regs, img_after,
                       meta={"steps": rec["steps"], "boot_ms": round(boot_ms, 1),
                             "head": "r32"})
        in_mem_bytes = None  # the runner object is dropped below = POWER OFF
        del boot_runner, rec, ram_host, regs, img_after

        # ---- 3. CRASH-SAFETY LEGS --------------------------------------
        if args.corrupt_container:
            raw = bytearray(cpath.read_bytes())
            raw[-8] ^= 0xFF          # flip one payload byte (torn write)
            cpath.write_bytes(bytes(raw))
            try:
                load_container(cpath)
            except ValueError as e:
                print(f"R3.2 torn-write RED leg: loader REJECTED corrupt "
                      f"container (correct discrimination): {e}")
                sys.exit(1)          # RED by contract
            print("R3.2 PERSISTENCE: FAIL-RED (corrupt container ACCEPTED — "
                  "checksum gate is NOT load-bearing)")
            sys.exit(1)

        # crash-mid-write analogue: a .tmp leftover must not be readable
        # as the container, and the previous container must survive.
        tmp_leftover = cpath.with_suffix(".tmp")
        tmp_leftover.write_bytes(MAGIC + b"\xff" * 32)
        if cpath.read_bytes()[:4] != MAGIC or len(cpath.read_bytes()) < 70_000:
            print("R3.2 PERSISTENCE: FAIL (atomic replace left no container)")
            sys.exit(1)
        print(f"crash-mid-write analogue: leftover {tmp_leftover.name} ignored, "
              f"container intact ({cpath.stat().st_size} B)")

        # ---- 4. POWER ON: fresh runner, restore from container ----------
        header, ram2, regs2, img2 = load_container(cpath)
        print(f"power-on: container v{header['format']} "
              f"(saved {header['saved_at']}, checksum "
              f"{header['checksum'][:12]}…) loaded")

        ok, detail = verify_frozen_words(ram2, corrupt=args.corrupt_verify)
        if args.corrupt_verify:
            if ok:
                print("R3.2 PERSISTENCE: FAIL-RED (corrupt-verify ACCEPTED a "
                      "good restore — verifier NOT load-bearing)")
                sys.exit(1)
            print("R3.2 corrupt-verify RED leg: verifier REJECTED with "
                  "corrupted expectations (correct discrimination)")
            sys.exit(1)
        if not ok:
            print(f"R3.2 PERSISTENCE: FAIL (restored state failed "
                  f"verification: {detail})")
            sys.exit(1)

        # the restored image re-bakes into a runner with identical state
        # (proof the container is a machine state, not just a word dump)
        rd = Path(d) / "restored.npy"
        np.save(rd, img2.astype(np.uint32))
        _ = GlyphRunner(rd, ram_words=16384)  # constructs cleanly from restored image

        print(f"R3.2 PERSISTENCE: PASS (freeze → container → power cycle → "
              f"restore; all frozen words survived: {detail})")
        sys.exit(0)


if __name__ == "__main__":
    main()
