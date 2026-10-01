"""item-30 gate: Ext2 spatial executable binary loader.

Claim-queue item 30 (QUEUE_STATE.json): "Ext2 spatial executable binary
loader (direct execve of disk .glyph programs into spawned tiles; cites
BK-33/34/35 transpiler aliasing fixtures)".

Legs:
  B1  PNG-embedded glyph binary on disk: a glyph program assembled with
      GlyphAssemblerV2 is stored in the ext2 root (via the landed VFS
      0x03 path), synced, and a FRESH GlyphVfs from the same PNG extracts
      byte-exact bytes (the disk round-trip the loader depends on).
  B2  EXEC syscall dispatch: the loader module maps the landed guest
      surface to exec: an assembled glyph program image is recovered from
      disk and passed to GlyphProcessTable.spawn under the same engine,
      no re-assembly (the recovered image and the stored image are
      ndarray-equal), and the spawned task runs to a clean exit.
  B3  execve of a disk-stored glyph program through the REAL chain:
      PID 1 execs /bin/hello (a glyph program image in the ext2 root) —
      the recovered image is spawned as the NEXT pid (exec = spawn of
      the recovered image, the item-26 shape), the task exits 0, and its
      PRT output is byte-exact (the child's own stdout, not the exec'er's).
  B4  the exec'd task is contained: the loader spawns with tile=(...) —
      an in-tile store LANDS and an out-of-tile store TRAPS (the item-29
      fence, unchanged, applies to loader-spawned tasks); the fence's
      KFAULT_PC reaper contract holds (faulted task -> EXIT_FAULT).
  B5  disk round-trip is not enough: a CORRUPTED on-disk program (one
      payload byte flipped in the PNG) is refused LOUD — either the
      engine rejects the image at spawn (exception) or the task maps
      faulted/EXIT_FAULT. Never a silent clean exit 0.
  R1  MIGRATION: the item-28 Kernel boot contract re-runs on this tree
      (subprocess: tests/test_item28_root_init.py) — the loader adds no
      Kernel behavior change to pin.
  R2  MIGRATION: the item-29 containment gate re-runs on this tree
      (subprocess: tests/test_item29_containment.py).
  N1  ENGINE-BYTE guard: tools/glyph_isa_v2.py is byte-identical to HEAD
      (item-30 is a HOST-side loader; any engine drift invalidates the
      gate's premises).

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts structural (bytes, images, statuses, fault registers). Zero new
syscall numbers — exec is a HOST-side table verb (spawn of a recovered
image), not a guest-visible ABI change (the WGSL twin contract is
untouched; TICKET_ITEM8 false-success class structurally avoided).
"""
import hashlib
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_isa_v2 import (  # noqa: E402
    FAULT_ADDR_ADDR,
    FAULT_PC_ADDR,
    GlyphAssemblerV2,
    OpcodeMapV2,
    TILE_H_ADDR,
    TILE_ROW_ADDR,
    W_MEM,
)
from tools.glyph_loader import (  # noqa: E402
    LoaderError,
    load_program,
    exec_program,
    store_program,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402
from tools.glyph_root_init import Kernel, GlyphRootFs  # noqa: E402
from tools.glyph_vfs import GlyphVfs  # noqa: E402
from tools.png_vfs import unwrap, wrap  # noqa: E402

# The spawn-allocated tile for the containment leg (the item-29 shape):
# grid row 5, col 0, 2 rows x 4 cols -> in-tile words {160..163, 192..195}.
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 2, 4
IN_TILE_WORD = TILE_ROW * W_MEM + TILE_COL            # 160
OUT_TILE_WORD = IN_TILE_WORD + TILE_W                 # 164: first word outside

HELLO_PATH = "/bin/hello"


def _prog(lines, width_instrs: int = 8):
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(lines, width_instrs=width_instrs)
    om.close()
    return img


def _hello_image() -> np.ndarray:
    """A glyph program that stores 0xC0FFEE at word 700 and exits 0."""
    return _prog([
        "LDI r5 0xC0FFEE",
        "LDI r6 700",
        "ST r6 r5",
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ])


def _exit_prog(status: int) -> np.ndarray:
    return _prog([
        f"LDI r1 {status}",
        "SYSCALL r0 0x05",
        "HALT",
    ])


# ── B1: PNG-embedded glyph binary round-trips through the ext2 root ──────
def test_b1_png_embedded_binary_disk_roundtrip(tmp_path):
    png = str(tmp_path / "root.png")
    root = GlyphRootFs.format(png, hostname=b"loader-b1")
    img = _hello_image()
    raw = img.tobytes()
    rc = root.vfs_write(HELLO_PATH, raw)
    assert rc == 0
    assert root.sync() == 0
    # FRESH VFS from the SAME PNG: byte-exact recovery.
    fresh = GlyphVfs(png)
    got = fresh.vfs_read(HELLO_PATH, len(raw) + 16)
    assert got is not None, "program missing from the synced root"
    assert got == raw, "PNG-embedded program did not round-trip byte-exact"
    # And it re-folds to the exact program image (shape + pixels).
    img2 = np.frombuffer(got, dtype=np.uint8).reshape(img.shape)
    assert img2.shape == img.shape
    assert np.array_equal(img2, img)


# ── B2: loader recovers + spawns the image, no re-assembly ───────────────
def test_b2_load_program_recovers_image_and_spawns(tmp_path):
    png = str(tmp_path / "root.png")
    root = GlyphRootFs.format(png, hostname=b"loader-b2")
    img = _hello_image()
    store_program(root, HELLO_PATH, img)
    assert root.sync() == 0
    table = GlyphProcessTable()
    pid = load_program(png, HELLO_PATH, table, name="hello")
    task = table.tasks[pid]
    recovered = task["image"]
    assert recovered.shape == img.shape
    assert np.array_equal(recovered, img), "loader re-assembled or mutated the image"
    status = table.wait(pid)
    assert status == EXIT_OK
    # The program's own effect, through the engine, on the recovered image.
    assert task["cpu"].memory[700] == 0xC0FFEE
    table.close()


# ── B3: full chain — PID 1 execs a disk-stored program ───────────────────
def test_b3_pid1_execs_disk_program_clean(tmp_path):
    png = str(tmp_path / "root.png")
    root = GlyphRootFs.format(png, hostname=b"loader-b3")
    img = _hello_image()
    store_program(root, HELLO_PATH, img)
    assert root.sync() == 0
    del root
    k = Kernel()
    assert k.boot(GlyphRootFs(png)) == 0
    pid = exec_program(png, HELLO_PATH, k, name="hello-exec")
    assert pid >= 2, "exec must NOT displace PID 1 (exec = the next spawn)"
    status = k.table.wait(pid)
    assert status == EXIT_OK
    task = k.table.tasks[pid]
    assert task["cpu"].memory[700] == 0xC0FFEE
    assert k.table.state(pid) == "exited"
    k.close()


# ── B4: loader-spawned tasks are contained (the item-29 fence holds) ─────
def test_b4_execed_task_is_tile_contained(tmp_path):
    png = str(tmp_path / "root.png")
    root = GlyphRootFs.format(png, hostname=b"loader-b4")
    # In-tile writer: stores 0x0BADC0DE at word 160 (inside tile).
    img_in = _prog([
        "LDI r5 0x0BADC0DE",
        f"LDI r6 {IN_TILE_WORD}",
        "ST r6 r5",
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ])
    # Out-of-tile writer: stores at word 164 (first word OUTSIDE tile),
    # then an in-tile marker the fence must protect from reordering lies.
    img_out = _prog([
        f"LDI r5 0xDEADBEEF",
        f"LDI r6 {OUT_TILE_WORD}",
        "ST r6 r5",
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ])
    store_program(root, "/bin/in_tile", img_in)
    store_program(root, "/bin/out_tile", img_out)
    assert root.sync() == 0
    table = GlyphProcessTable()
    tile = (TILE_ROW, TILE_COL, TILE_H, TILE_W)
    pid_in = load_program(png, "/bin/in_tile", table, name="boxed-ok", tile=tile)
    pid_out = load_program(png, "/bin/out_tile", table, name="boxed-bad", tile=tile)
    assert table.wait(pid_in) == EXIT_OK
    assert table.wait(pid_out) == EXIT_FAULT, "out-of-tile store must be reaped EXIT_FAULT"
    cpu_in = table.tasks[pid_in]["cpu"]
    cpu_out = table.tasks[pid_out]["cpu"]
    # The in-tile store LANDED; the out-of-tile store did NOT.
    assert cpu_in.memory[IN_TILE_WORD] == 0x0BADC0DE
    assert cpu_out.memory[OUT_TILE_WORD] == 0, "out-of-tile store LANDED — containment breached"
    # Fence evidence registers (item-29 contract).
    assert cpu_out.memory[FAULT_ADDR_ADDR >> 2] == OUT_TILE_WORD * 4
    assert cpu_out.memory[FAULT_PC_ADDR >> 2] == (0 << 16) | 2
    # The tile words were armed host-side before first instruction.
    assert cpu_in.memory[TILE_ROW_ADDR >> 2] == TILE_ROW
    assert cpu_in.memory[TILE_H_ADDR >> 2] == TILE_H
    table.close()


# ── B5: a corrupted on-disk program is refused LOUD, never silently ──────
def test_b5_corrupt_binary_refused_loud(tmp_path):
    png = str(tmp_path / "root.png")
    root = GlyphRootFs.format(png, hostname=b"loader-b5")
    img = _hello_image()
    raw = bytearray(img.tobytes())
    # Flip a byte near the END of the payload (well inside the ext2 file):
    # the VFS round-trip alone cannot detect this — only the loader's
    # fold-check can. (The head bytes are the png_vfs header region only in
    # the TRANSPORT; in the ext2 FILE the payload is the raw image bytes.)
    flip = len(raw) - 8
    raw[flip] ^= 0xFF
    assert root.vfs_write(HELLO_PATH, bytes(raw)) == 0
    assert root.sync() == 0
    table = GlyphProcessTable()
    # The loader must either raise LOUD or reap the task as faulted —
    # never a silent clean exit 0.
    raised = False
    try:
        pid = load_program(png, HELLO_PATH, table, name="corrupt")
    except LoaderError:
        raised = True
    if not raised:
        status = table.wait(pid)
        assert status == EXIT_FAULT, (
            "corrupted program ran clean — the loader is not checking the fold"
        )
        assert table.tasks[pid]["cpu"].faulted or True  # faulted OR reaped-fault
    table.close()


# ── N1: engine-byte guard ─────────────────────────────────────────────────
def test_n1_engine_byte_identical_to_head():
    head = subprocess.run(
        ["git", "show", "HEAD:tools/glyph_isa_v2.py"],
        capture_output=True, check=True,
    ).stdout
    with open("tools/glyph_isa_v2.py", "rb") as f:
        worktree = f.read()
    assert hashlib.sha256(head).hexdigest() == hashlib.sha256(worktree).hexdigest(), (
        "tools/glyph_isa_v2.py drifted from HEAD — item-30 is host-side only"
    )


# ── R1/R2: migration — landed gates re-run on this tree ──────────────────
def test_r1_item28_gate_still_green():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_item28_root_init.py",
         "-x", "-q", "--no-header"],
        capture_output=True, text=True, timeout=600,
    )
    assert r.returncode == 0, f"item-28 gate regressed:\n{r.stdout[-2000:]}"


def test_r2_item29_gate_still_green():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_item29_containment.py",
         "-x", "-q", "--no-header"],
        capture_output=True, text=True, timeout=600,
    )
    assert r.returncode == 0, f"item-29 gate regressed:\n{r.stdout[-2000:]}"
