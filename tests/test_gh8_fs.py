#!/usr/bin/env python3
"""tests/test_gh8_fs.py — GH-8 oracle test (RED until baker grows
fs_kernel_image()).

Falsifiable gate for GH-8 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):

1. baker.fs_kernel_image(atlas, program_text, out_path=...) emits ONE image
   whose resident kernel:
     - seeds the in-image flat FS: header at word 740 (FSTAB: 2 file slots,
       each 4 words: [name u32, start, len, in_use]), data region at word 760,
     - arms vectors: KSYS_PC -> in-image FS syscall dispatcher, KFAULT_PC ->
       fault handler (loader-seeded packed pixel PCs, two-pass bake),
     - programs BOX0 (task arena), latches MODE_LATCH = MODE_USER, KJMPs
       into the baked user task (program_text).

2. Syscall ABI (engine marshals r17/r10/r11 -> SYS_N/SYS_A0/SYS_A1):
     - SYS 6 = create+write: a0 = file name u32, a1 = byte count; the data
       words the task stored to the shared FS scratch window (words 736..739)
       are appended by the kernel to the file's data extent,
     - SYS 7 = read: a0 = file name u32, a1 = max bytes; kernel copies the
       file's data into the shared read-out window (words 752..755) and
       returns the byte count,
     - SYS 8 = delete: a0 = file name u32; kernel marks the slot free.

3. Persistence proof (the GH-8 thesis): run 1 bakes kernel + WRITE task,
   runs to HALT, then the runner's mutated image ndarray is saved to disk
   (the kernel copies file bytes INTO the image's data region via ST stores
   to word addresses -- the image IS the disk). Re-load the SAME saved image
   offline, bake-only-swap the user task region... no: strictly NO host
   re-bake. Instead the image is baked WITH both tasks (task A: create+write
   "DATA" then KJMP to kernel switch; task B: read "DATA", verify content,
   write exit word). The kernel round-robins A -> B via MODE_LATCH/KJMP
   (GH-7 machinery). Receipt checks:
     - receipt["halted"], not receipt["faulted"]
     - FSTAB slot 0 shows name = pack('DATA'), in_use = 1, len = 8
     - file data words 760..761 == the two payload words the task wrote
     - task B's exit word == 0xFEED0008 (read-back byte-exact)
     - a SECOND offline run of the same image file (fresh GlyphRunner, zero
       host writes) shows task B's read STILL succeeds (in_use survives:
       B re-creates nothing; the file persists in the image).

4. Delete leg: separate image with a third syscall 8 after B reads; the
   FSTAB slot shows in_use = 0 and a subsequent read returns 0 bytes
   (ERR_NOFILE marker 'E' at the read window).

5. Isolation leg: task A writes OUTSIDE its box -> fault handler records
   0xFA171; the FS header stays untouched.

6. Zero-dev-import property (same as GH-2/3/5/6/7): runner.py stays clean.

Today this FAILS at import: fs_kernel_image does not exist yet.
"""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import fs_kernel_image                # noqa: E402  (RED: not implemented)

STATUS_WORD = 950

# GH-8 image ABI (fixed word indices; BOX0 = task arena [700..768)).
# GH-8b: FSTAB + file data moved into the pixel-aliased window [1024,1280);
# scratch/readout/exits stay in BOX0 RAM.
GH8_FSTAB_WORD = 1024       # FSTAB: slot table (kernel-owned, SUPER-only, PIXELS)
GH8_FSTAB_NSLOTS = 2        # slots; each slot = 4 words (name,start,len,in_use)
GH8_DATA_WORD = 1044        # file data region start (kernel-owned, PIXELS)
GH8_SCRATCH_WORD = 736      # task -> kernel staging window (in BOX0)
GH8_READOUT_WORD = 752      # kernel -> task read-out window (in BOX0)
GH8_EXIT_A = 703            # task A exit word
GH8_EXIT_B = 723            # task B exit word
GH8_FAULT_WORD = 731        # fault-leg verdict (0xFA171)
GH8_N_WRITE = 6             # create+write
GH8_N_READ = 7              # read
GH8_N_DEL = 8               # delete
GH8_NAME_DATA = (ord('D') | (ord('A') << 8) | (ord('T') << 16) | (ord('A') << 24))
GH8_PAYLOAD0 = 0x11223344   # file bytes 0..3 (as word)
GH8_PAYLOAD1 = 0x55667788   # file bytes 4..7
GH8_FILE_BYTES = 8
GH8_IN_USE = 1
GH8_FAULT_SEEN = 0xFA171
GH8_ERR_NOFILE = ord('E')   # read of missing/deleted file -> 'E' in readout w0
KERNEL_OK = 0xCAFE0008      # 0xCAFE0000 | 8 (final status after task B)
EXIT_OK_A = 0xFEED0006      # 0xFEED0000 | write syscall number
EXIT_OK_B = 0xFEED0007      # 0xFEED0000 | read syscall number
PACK_D = GH8_PAYLOAD0

# GH-8b pixel-FS ABI: the FS lives in IMAGE PIXELS via a window mapped 2
# pixels per 32-bit word (pixel0 = bits 23..0, pixel1 = bits 31..24). Word
# W maps to linear pixel (W*2, W*2+1) in scanline order. The FSTAB occupies
# pix-words 780..787 (2 slots x 4 words), file data starts at pix-word 800.
GH8B_PIX_FSTAB_WORD = 1024  # FSTAB base in pix-words (== GH8_FSTAB_WORD)
GH8B_PIX_WORD = 1044        # file data region base in pix-words (== GH8_DATA_WORD)


def _pack_u32(*bs: int) -> int:
    v = 0
    for i, b in enumerate(bs):
        v |= (b & 0xFF) << (8 * i)
    return v


def _bake(tmp: Path, name: str = "gh8.glyph.npy", del_leg: bool = False, fault_leg: bool = False) -> Path:
    atlas = build_default_atlas()
    out = tmp / name
    # min_rows=80: the GH-8b pixel-FS window (words 1024..1279 -> 2 px/word =
    # pixels 2048..2559) must (a) fit INSIDE the image without wrap-around
    # (npx >= 2560 keeps word->pixel bijective) and (b) sit clear of the
    # program region (last program pixel = 977 at this size).
    fs_kernel_image(atlas, del_leg=del_leg, fault_leg=fault_leg, min_rows=80, out_path=out)
    return out


def _run(tmp: Path, **kw):
    out = _bake(tmp, **kw)
    # The FS kernel programs the isolation MMIO block (KSYS_PC/KFAULT_PC/
    # BOX0/BOX1/MODE_LATCH at word 8192+), so the runner must size RAM past
    # the MMIO top word to arm GlyphCPUv2._iso_enabled.
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=60000)
    return runner, receipt


def test_gh8_fs_image_bakes():
    with tempfile.TemporaryDirectory() as d:
        assert _bake(Path(d), "gh8.glyph.npy").exists(), (
            "fs_kernel_image must emit one image")


def test_gh8_create_write_then_read_persists():
    """The whole GH-8 gate in one image run: task A create+writes 'DATA',
    kernel switches to task B which reads it back byte-exact; the FSTAB and
    data region show the file resident in the image itself."""
    with tempfile.TemporaryDirectory() as d:
        runner, receipt = _run(Path(d))
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        img = np.asarray(runner.image)
        h, w, _ = img.shape
        def _pw(word: int) -> int:   # read a pix-word: 2 px per 32-bit word
            lin = word * 2
            lo = (int(img[lin // w, lin % w][0]) << 16) | (int(img[lin // w, lin % w][1]) << 8) | int(img[lin // w, lin % w][2])
            lin2 = word * 2 + 1
            hi = int(img[lin2 // w, lin2 % w][2])
            return (lo | (hi << 24)) & 0xFFFFFFFF
        # FSTAB slot 0 lives in PIXELS now: name 'DATA', in_use, len 8 (start = data region)
        assert _pw(GH8_FSTAB_WORD) == GH8_NAME_DATA, (
            f"fstab name 0x{_pw(GH8_FSTAB_WORD):08x} != 0x{GH8_NAME_DATA:08x}")
        assert _pw(GH8_FSTAB_WORD + 3) == GH8_IN_USE
        assert _pw(GH8_FSTAB_WORD + 2) == GH8_FILE_BYTES
        assert _pw(GH8_FSTAB_WORD + 1) == GH8_DATA_WORD
        # file bytes resident in the image pixel data region
        assert _pw(GH8_DATA_WORD) == GH8_PAYLOAD0
        assert _pw(GH8_DATA_WORD + 1) == GH8_PAYLOAD1
        # task A completed the write syscall + exit
        assert mem[GH8_EXIT_A] == EXIT_OK_A, (
            f"task A exit 0x{mem[GH8_EXIT_A]:08x} != 0x{EXIT_OK_A:08x}")
        # task B read the file back byte-exact (payload in read-out window)
        assert mem[GH8_READOUT_WORD] == GH8_PAYLOAD0, (
            f"readout w0 0x{mem[GH8_READOUT_WORD]:08x} != 0x{GH8_PAYLOAD0:08x}")
        assert mem[GH8_READOUT_WORD + 1] == GH8_PAYLOAD1
        assert mem[GH8_EXIT_B] == EXIT_OK_B, (
            f"task B exit 0x{mem[GH8_EXIT_B]:08x} != 0x{EXIT_OK_B:08x}")
        assert receipt["status_word_value"] == KERNEL_OK, receipt


def test_gh8_file_survives_offline_rerun():
    """Persistence is in-image, not host: after run 1 halts, the mutated
    image ndarray is saved to disk; a FRESH GlyphRunner on that file (zero
    host writes, no re-bake) re-executes task B's read against the data the
    previous run's kernel wrote into the image. The offline receipt proves
    the file survived in the image itself."""
    with tempfile.TemporaryDirectory() as d:
        runner, receipt = _run(Path(d), name="gh8_persist.glyph.npy")
        assert receipt["halted"] is True and receipt["faulted"] is False
        post_path = Path(d) / "post_gh8.glyph.png"
        Image.fromarray(runner.image, "RGB").save(post_path)
        # Fresh runner, zero host writes: the image re-runs its resident
        # kernel + tasks. Task A re-creates 'DATA' (idempotent rewrite of
        # the same bytes), task B reads it back -- the FSTAB start/len the
        # offline kernel sees must match the ONLINE run's layout exactly,
        # proving the bytes (not host state) carried the file.
        offline = GlyphRunner(post_path, ram_words=16384)
        r2 = offline.run(max_instructions=60000)
        assert r2["halted"] is True, r2.get("error", r2)
        assert r2["faulted"] is False
        mem2 = r2["memory"]
        # FSTAB lives in pixels now (GH-8b): assert via the pixel decode
        img2 = np.asarray(offline.image)
        h2, w2, _ = img2.shape
        npx2 = h2 * w2
        px2 = img2.reshape(-1, 3)
        def _pw(word: int) -> int:
            lin = (word * 2) % npx2
            lin2 = (word * 2 + 1) % npx2
            lo = (int(px2[lin][0]) << 16) | (int(px2[lin][1]) << 8) | int(px2[lin][2])
            return (lo | (int(px2[lin2][2]) << 24)) & 0xFFFFFFFF
        assert _pw(GH8_FSTAB_WORD + 1) == GH8_DATA_WORD
        assert _pw(GH8_FSTAB_WORD + 2) == GH8_FILE_BYTES
        assert mem2[GH8_READOUT_WORD] == GH8_PAYLOAD0
        assert mem2[GH8_READOUT_WORD + 1] == GH8_PAYLOAD1
        assert mem2[GH8_EXIT_B] == EXIT_OK_B
        assert r2["status_word_value"] == KERNEL_OK


def test_gh8b_tampered_pixel_survives_offline_rerun():
    """GH-8b negative control — THE persistence gate.

    Run 1 writes 'DATA' and halts; the image is saved. We then TAMPER with
    the file-data pixels in the saved image (0x11223344 -> 0xDEADBE00,
    0x55667788 -> 0xDEADBE01). A fresh offline runner re-executes the
    resident kernel. Because SYS 6 is idempotent (in_use already set in the
    FSTAB pixels), task A's create must be a no-op and the kernel must copy
    file data FROM THE TAMPERED PIXELS into the read-out window. Task B
    reading the corrupted values back proves data lives in image pixels.
    A canonical-byte readout means the FS is faking persistence via
    deterministic task re-execution -- exactly the GH-8 defect."""
    with tempfile.TemporaryDirectory() as d:
        runner, receipt = _run(Path(d), name="gh8b_tamper.glyph.npy")
        assert receipt["halted"] is True and receipt["faulted"] is False
        post_path = Path(d) / "post_gh8b.glyph.png"
        Image.fromarray(runner.image, "RGB").save(post_path)

        # --- THE TAMPER PROBE: corrupt the file-data pixels in place ----
        tampered = np.array(Image.open(post_path).convert("RGB"))
        h, w, _ = tampered.shape
        def _px(pix_index: int):
            return pix_index % w, pix_index // w
        def _poke(word: int, value: int):
            # engine layout: lo24 -> pixel word*2, hi8 -> pixel word*2+1 BLUE
            lo, hi = value & 0xFFFFFF, (value >> 24) & 0xFF
            x, y = _px(word * 2)
            tampered[y, x] = ((lo >> 16) & 0xFF, (lo >> 8) & 0xFF, lo & 0xFF)
            x, y = _px(word * 2 + 1)
            tampered[y, x] = (0, 0, hi)
        _poke(GH8B_PIX_WORD + 0, 0xDEADBE00)   # payload0 (word 800)
        _poke(GH8B_PIX_WORD + 1, 0xDEADBE01)   # payload1 (word 801)
        tampered_path = Path(d) / "tampered.glyph.png"
        Image.fromarray(tampered, "RGB").save(tampered_path)

        # Fresh runner on the TAMPERED image; kernel must read the pixels.
        offline = GlyphRunner(tampered_path, ram_words=16384)
        r2 = offline.run(max_instructions=60000)
        assert r2["halted"] is True, r2.get("error", r2)
        assert r2["faulted"] is False, r2
        mem2 = r2["memory"]
        # the file data (NOT canonical payload) reaches the read-out window
        assert mem2[GH8_READOUT_WORD] == 0xDEADBE00, (
            f"readout 0x{mem2[GH8_READOUT_WORD]:08x} != tampered 0xDEADBE00 — "
            "FS data did NOT come from image pixels (deterministic replay defect)")
        assert mem2[GH8_READOUT_WORD + 1] == 0xDEADBE01, (
            f"readout w1 0x{mem2[GH8_READOUT_WORD + 1]:08x} != tampered 0xDEADBE01")
        assert mem2[GH8_EXIT_B] == EXIT_OK_B
        assert r2["status_word_value"] == KERNEL_OK


def test_gh8_delete_leg():
    """Task B reads 'DATA' fine, then a SYS 8 delete lands; FSTAB shows
    in_use = 0, and the read-out window shows the ERR_NOFILE marker."""
    with tempfile.TemporaryDirectory() as d:
        _, receipt = _run(Path(d), del_leg=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # delete landed: slot freed
        assert mem[GH8_FSTAB_WORD + 3] == 0, "FSTAB slot must be freed (in_use=0)"
        # post-delete read attempt returns the ERR_NOFILE marker
        assert mem[GH8_READOUT_WORD] == GH8_ERR_NOFILE, (
            f"post-delete readout 0x{mem[GH8_READOUT_WORD]:08x} != ERR '{chr(GH8_ERR_NOFILE)}'")


def test_gh8_fault_leg_isolates_fs():
    """A task-A out-of-box store vectors to KFAULT_PC; the handler records
    0xFA171; the FS header + data region stay untouched (the kernel never
    processed a syscall)."""
    with tempfile.TemporaryDirectory() as d:
        _, receipt = _run(Path(d), fault_leg=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is True, "out-of-box user store must fault"
        mem = receipt["memory"]
        assert mem[GH8_FAULT_WORD] == GH8_FAULT_SEEN
        # no syscall was serviced: FS untouched
        assert mem[GH8_FSTAB_WORD + 3] == 0
        assert mem[GH8_DATA_WORD] == 0
        assert mem[GH8_EXIT_B] == 0


def test_gh8_runner_still_zero_dev_imports():
    src = (_REPO / "tools" / "glyph_gpt" / "runner.py").read_text()
    tree = ast.parse(src)
    forbidden = {"atlas", "spatial_builder", "synth", "generate",
                 "model", "tokenizer", "corpus", "train", "pack_dataset",
                 "baker"}
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for n in names:
            for f in forbidden:
                assert f not in n, f"runner.py must not import '{n}'"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
