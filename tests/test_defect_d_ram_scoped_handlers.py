"""Backlog (d) implementation: (A) scoped to handlers only.

RULED 2026-09-16 (GLYPH_ISA_ROADMAP.md Pillar 3): 5 syscall handlers whose
data/dest arg currently addresses IMAGE space migrate to RAM (self.memory),
per the SYSCALL_READ (0x02) precedent. 0x11 STORE_CODE is explicitly
excluded (stays pixel-space per DEFECT-27). Migrating: 0x01 WRITE, 0x03
FILE_WRITE's data, 0x04 FILE_READ's dest, 0x08 AUDIO_OUT, 0x09 AUDIO_IN's
dest.

Shape (per Jericho's endorsed plan): baseline first, then one handler per
commit with its own parity leg, so each commit's blast radius is one
syscall. This file grows one section per handler as each lands - a
migrated handler's "baseline" test is kept (renamed to document what WAS
true) alongside its new "post-migration" test, so the history of the
change stays legible in the test file itself, not just the git log.

Handlers call _handle_syscall(...) directly rather than going through a
full assembled program - it's a plain bound method, and this keeps each
leg's setup to "poke registers + memory/image, call, assert" instead of
round-tripping through the assembler for a single syscall.

CORRECTION 2026-09-16 (caught by review after 0x01's first commit,
fd24c76): "twin synced" in that commit checked only the Python<->Python
twin (glyph_dispatch's copy of glyph_isa_v2.py); it did NOT check
Python<->WGSL parity, and tools/wgsl_glyph_isa_v2.py was not migrated -
a fresh SE022a-class divergence, same day as the one 2.2a closed. Fixed
via a backfill commit (WGSL's WRITE now reads a new `ram` buffer -
binding 5, added specifically for this - instead of image pixels) and a
new rule: every handler from here lands on BOTH engines in the same
commit, with its own WGSL/cross-engine parity leg in this file, not just
Python-side legs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import types  # noqa: E402

import pytest  # noqa: E402

from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2  # noqa: E402


@pytest.fixture(autouse=True)
def _bk44_arm_fs_allow(tmp_path):
    """BK-44 (2026-09-30): the engine's 0x03/0x04 host arms now require the
    path under a GLYPH_FS_ALLOW root (deny-by-default, the BK-15 model
    extended). These legs' subject is the RAM-vs-image DATA migration, not
    host-FS containment, so the suite arms the env for its own tmp_path
    roots (per-test, via tmp_path fixture) — migrated, never weakened:
    the HISTORICAL legs run neutered in-memory copies and pin their
    anchors against the LIVE source, which now carries the check."""
    import os
    old = os.environ.get("GLYPH_FS_ALLOW")
    os.environ["GLYPH_FS_ALLOW"] = str(tmp_path.resolve())
    yield
    if old is None:
        os.environ.pop("GLYPH_FS_ALLOW", None)
    else:
        os.environ["GLYPH_FS_ALLOW"] = old

# An address safely outside the GH-8b FS window [1024, 1280) so these tests
# never accidentally exercise that (unrelated, correct) aliasing mechanism.
ADDR = 2000


def _fresh_cpu(cols_instrs=8, image_shape=(64, 32, 3)):
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=cols_instrs)
    cpu.memory = [0] * 16384
    image = np.zeros(image_shape, dtype=np.uint8)
    return cpu, image


# --- 0x01 SYSCALL_WRITE ------------------------------------------------------

def test_historical_pre_migration_0x01_write_read_image_not_ram():
    """HISTORICAL (true before 2026-09-16's migration, kept for the
    record): WRITE's addr arg (r1) used to read IMAGE space via
    _mem_read. This test now runs the PRE-fix behavior through a
    neutered in-memory copy (live file untouched) rather than asserting
    it against the real engine - the real engine has moved on; see
    test_0x01_write_reads_ram_not_image below for current behavior."""
    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    old_body = (
        "        if syscall_num == 0x01:  # SYSCALL_WRITE\n"
        "            # Write r2 bytes from address r1 to output buffer.\n"
        "            # DEFECT-D/backlog(d): migrated from image space to RAM\n"
        "            # (self.memory) 2026-09-16 - (A) scoped to handlers, per the\n"
        "            # SYSCALL_READ (0x02) precedent. Out-of-range addr reads as 0\n"
        "            # rather than IndexError-ing (same no-crash default 0x02 uses,\n"
        "            # here for reads instead of the growth guard writes need).\n"
        "            addr = self.registers[1]\n"
        "            length = self.registers[2]\n"
        "            for i in range(length):\n"
        "                a = addr + i\n"
        "                val = self.memory[a] if 0 <= a < len(self.memory) else 0\n"
        "                self.output.append(val)\n"
    )
    reverted_body = (
        "        if syscall_num == 0x01:  # SYSCALL_WRITE\n"
        "            # Write r2 bytes from address r1 to output buffer\n"
        "            addr = self.registers[1]\n"
        "            length = self.registers[2]\n"
        "            for i in range(length):\n"
        "                val = self._mem_read(image, addr + i)\n"
        "                self.output.append(val)\n"
    )
    assert old_body in source, "anchor stale - re-sync with the live 0x01 handler"
    reverted_source = source.replace(old_body, reverted_body)
    assert reverted_source != source

    mod = types.ModuleType("glyph_isa_v2_pre_migration_probe")
    mod.__file__ = str(src_path)
    exec(compile(reverted_source, str(src_path), "exec"), mod.__dict__)

    cpu = mod.GlyphCPUv2(mod.OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    cpu.memory[ADDR] = 0xAA  # RAM decoy the pre-migration handler ignored
    cpu._mem_write(image, ADDR, 0xBB)  # image: what pre-migration WRITE saw
    cpu.registers[1] = ADDR
    cpu.registers[2] = 1
    cpu._handle_syscall(0x01, image)
    assert cpu.output == [0xBB], "pre-migration probe's own anchor is wrong"

    # Live file is untouched - this ran entirely from an in-memory copy.
    assert src_path.read_text() == source


def test_0x01_write_reads_ram_not_image():
    """POST-MIGRATION (2026-09-16): WRITE's addr arg (r1) now reads RAM
    (self.memory), matching SYSCALL_READ's (0x02) established convention.
    Same decoy setup as the historical test, roles reversed: RAM now
    carries the real value, image carries the decoy."""
    cpu, image = _fresh_cpu()
    cpu.memory[ADDR] = 0xBB  # RAM: the value WRITE should see now
    cpu._mem_write(image, ADDR, 0xAA)  # image: a decoy WRITE should NOT see
    cpu.registers[1] = ADDR
    cpu.registers[2] = 1
    cpu._handle_syscall(0x01, image)
    assert cpu.output == [0xBB]


def test_0x01_write_out_of_range_addr_reads_zero_not_crash():
    """Same no-crash discipline as 0x02: a model-controlled out-of-range
    addr must not IndexError."""
    cpu, image = _fresh_cpu()
    cpu.registers[1] = 999_999
    cpu.registers[2] = 3
    cpu._handle_syscall(0x01, image)
    assert cpu.output == [0, 0, 0]


def test_non_vacuity_neutered_0x01_fix_reads_image_again():
    """Prove the migration is load-bearing: neuter it out-of-tree (live
    file untouched) and confirm the OLD (image-reading) behavior
    reappears identically - the exact probe test_historical_... uses
    above, phrased as a non-vacuity check on the CURRENT fix."""
    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    target = (
        "            for i in range(length):\n"
        "                a = addr + i\n"
        "                val = self.memory[a] if 0 <= a < len(self.memory) else 0\n"
        "                self.output.append(val)\n"
    )
    assert target in source, "non-vacuity probe's anchor text is stale"
    neutered_source = source.replace(
        target,
        "            for i in range(length):\n"
        "                self.output.append(self._mem_read(image, addr + i))\n",
    )
    assert neutered_source != source

    mod = types.ModuleType("glyph_isa_v2_neutered_0x01_probe")
    mod.__file__ = str(src_path)
    exec(compile(neutered_source, str(src_path), "exec"), mod.__dict__)

    cpu = mod.GlyphCPUv2(mod.OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    cpu.memory[ADDR] = 0xBB  # RAM: what the CURRENT (unneutered) fix reads
    cpu._mem_write(image, ADDR, 0xAA)  # image: what the NEUTERED code reads
    cpu.registers[1] = ADDR
    cpu.registers[2] = 1
    cpu._handle_syscall(0x01, image)
    assert cpu.output == [0xAA], (
        "expected the neutered (pre-migration) behavior to reappear - "
        "if this fails, the GREEN leg above isn't actually testing the fix"
    )

    assert src_path.read_text() == source


# --- 0x04 SYSCALL_FILE_READ --------------------------------------------------

def test_historical_pre_migration_0x04_file_read_wrote_image_not_ram(tmp_path):
    """HISTORICAL: FILE_READ's dest (r2) used to write IMAGE space via
    _mem_write. Runs the pre-fix body through a neutered in-memory copy
    (live file untouched)."""
    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    old_body = (
        "                with open(path, \"rb\") as f:\n"
        "                    data = f.read(max_len)\n"
        "                # backlog(d)/DEFECT-D (2026-09-16): dest migrated from\n"
        "                # image space to RAM (self.memory), (A) scoped to\n"
        "                # handlers. path_addr is untouched - _read_path's\n"
        "                # view-merge (RUN2/GH-9 in-flight work) is a separate\n"
        "                # concern, not part of this migration. Out-of-range dest\n"
        "                # bytes are dropped rather than growing RAM, same\n"
        "                # no-crash convention as 0x01/0x02.\n"
        "                for i, byte_val in enumerate(data):\n"
        "                    a = data_addr + i\n"
        "                    if 0 <= a < len(self.memory):\n"
        "                        self.memory[a] = byte_val\n"
    )
    reverted_body = (
        "                with open(path, \"rb\") as f:\n"
        "                    data = f.read(max_len)\n"
        "                for i, byte_val in enumerate(data):\n"
        "                    self._mem_write(image, data_addr + i, byte_val)\n"
    )
    assert old_body in source, "anchor stale - re-sync with the live 0x04 handler"
    reverted_source = source.replace(old_body, reverted_body)
    assert reverted_source != source

    mod = types.ModuleType("glyph_isa_v2_pre_migration_0x04_probe")
    mod.__file__ = str(src_path)
    exec(compile(reverted_source, str(src_path), "exec"), mod.__dict__)

    test_file = tmp_path / "l1.bin"
    test_file.write_bytes(b"AB")
    cpu = mod.GlyphCPUv2(mod.OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    path_bytes = str(test_file).encode() + b"\0"
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    cpu.registers[1] = 500
    cpu.registers[2] = ADDR
    cpu.registers[3] = 2
    n = cpu._handle_syscall(0x04, image)
    assert n == 2
    assert cpu.memory[ADDR] == 0, "pre-migration probe should NOT have touched RAM"
    assert cpu._mem_read(image, ADDR) & 0xFF == ord("A"), "pre-migration probe's own anchor is wrong"

    assert src_path.read_text() == source


def test_0x04_file_read_writes_ram_not_image(tmp_path):
    """POST-MIGRATION: FILE_READ's dest (r2) now writes RAM (self.memory).
    path_addr (r1) is untouched - _read_path still reads it via
    _mem_read, unaffected by this migration."""
    test_file = tmp_path / "l2.bin"
    test_file.write_bytes(b"CD")
    cpu, image = _fresh_cpu()
    path_bytes = str(test_file).encode() + b"\0"
    for i, b in enumerate(path_bytes):
        # PATH is data: RAM view (view-merge retired 2026-09-22).
        cpu.memory[500 + i] = b
    cpu.registers[1] = 500
    cpu.registers[2] = ADDR
    cpu.registers[3] = 2
    n = cpu._handle_syscall(0x04, image)
    assert n == 2
    assert cpu.memory[ADDR] == ord("C")
    assert cpu.memory[ADDR + 1] == ord("D")


def test_0x04_file_read_out_of_range_dest_drops_not_crashes(tmp_path):
    test_file = tmp_path / "l3.bin"
    test_file.write_bytes(b"XY")
    cpu, image = _fresh_cpu()
    path_bytes = str(test_file).encode() + b"\0"
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    cpu.registers[1] = 500
    cpu.registers[2] = 999_999
    cpu.registers[3] = 2
    n = cpu._handle_syscall(0x04, image)  # must not raise
    assert n == 2  # FILE_READ itself succeeded; the dest write was silently dropped


def test_non_vacuity_neutered_0x04_fix_writes_image_again(tmp_path):
    """Neuter the RAM fix, confirm the pre-fix (image-writing) behavior
    reproduces identically."""
    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    target = (
        "                for i, byte_val in enumerate(data):\n"
        "                    a = data_addr + i\n"
        "                    if 0 <= a < len(self.memory):\n"
        "                        self.memory[a] = byte_val\n"
    )
    assert target in source, "non-vacuity probe's anchor text is stale"
    neutered_source = source.replace(
        target,
        "                for i, byte_val in enumerate(data):\n"
        "                    self._mem_write(image, data_addr + i, byte_val)\n",
    )
    assert neutered_source != source

    mod = types.ModuleType("glyph_isa_v2_neutered_0x04_probe")
    mod.__file__ = str(src_path)
    exec(compile(neutered_source, str(src_path), "exec"), mod.__dict__)

    test_file = tmp_path / "l4.bin"
    test_file.write_bytes(b"EF")
    cpu = mod.GlyphCPUv2(mod.OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    path_bytes = str(test_file).encode() + b"\0"
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    cpu.registers[1] = 500
    cpu.registers[2] = ADDR
    cpu.registers[3] = 2
    cpu._handle_syscall(0x04, image)
    assert cpu.memory[ADDR] == 0, (
        "expected the neutered (pre-migration) behavior to reappear - "
        "RAM should stay untouched"
    )
    assert cpu._mem_read(image, ADDR) & 0xFF == ord("E")

    assert src_path.read_text() == source


def test_0x04_wgsl_stub_is_unchanged_no_op_documented():
    """WGSL's FILE_READ (0x04) is, and remains, an honest no-op stub
    returning 0 - GPU lanes have no host filesystem access, by design
    (see systems/SCOPING_MEMORY_VIEW_UNIFICATION.md #4). There is no
    real behavior to migrate and no divergence risk: a stub that
    returns 0 doesn't fabricate data the way a silently-wrong RAM/image
    read would. This test documents that explicitly rather than
    skipping the "both engines" step silently."""
    wgpu = pytest.importorskip("wgpu")
    from tools.glyph_isa_v2 import GlyphAssemblerV2
    from tools.glyph_gpt.runner import GlyphRunner

    om = OpcodeMapV2()
    prog = ["LDI r1 500", "LDI r2 2000", "LDI r3 2", "SYSCALL r9 0x04", "HALT"]
    img = GlyphAssemblerV2(om).assemble(prog, width_instrs=8)
    runner = GlyphRunner(image_or_path=img)
    rec = runner.run_wgsl(max_steps=50)
    assert rec.get("error") is None, rec.get("error")
    assert rec.get("halted"), rec
    assert rec["registers_full"][9] == 0, (
        "WGSL FILE_READ should still stub to 0 - if this changed, either "
        "someone added real (GPU-side) file I/O, which needs its own "
        "design pass, or something else regressed"
    )


# --- 0x03 SYSCALL_FILE_WRITE -------------------------------------------------

def test_historical_pre_migration_0x03_file_write_read_image_not_ram(tmp_path):
    """HISTORICAL: FILE_WRITE's data arg (r2) used to read IMAGE space via
    _mem_read. Runs the pre-fix body through a neutered in-memory copy
    (live file untouched)."""
    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    old_body = (
        "                path = _read_path(path_addr)\n"
        "                data = bytes(self._mem_read(image, data_addr + i) & 0xFF for i in range(length))\n"
    )
    reverted_body = (
        "                data = bytes((self.memory[data_addr + i] & 0xFF)\n"
        "                             if 0 <= data_addr + i < len(self.memory) else 0\n"
        "                             for i in range(length))\n"
    )
    # The LIVE 0x03 handler must NOT contain the old image-reading line any
    # more. (The identical line legitimately survives in the 0x08 AUDIO_OUT
    # handler - handler 4/5, not yet migrated - so the negative leg scopes
    # to the 0x03..0x04 slice of the source, not the whole file.)
    h03 = source[source.find("elif syscall_num == 0x03:"):source.find("elif syscall_num == 0x04:")]
    assert old_body not in h03, "anchor stale - the live 0x03 handler has moved on; re-sync this historical leg"
    # Rebuild a pre-migration module from the LIVE source by swapping the
    # migrated RAM read back out for the historical image read. (The swap
    # targets only the 0x03 handler's data line: the identical line in the
    # 0x08 AUDIO_OUT handler is still live there and must stay untouched -
    # replace() with count=1 plus the surrounding try/path context keeps
    # the probe surgical.)
    # BK-44 (2026-09-30): the anchor re-synced to the LIVE handler body —
    # it now includes the item-25 VFS reroute block (between the path line
    # and the DEFECT-D comment) and the landed BK-44 host-arm root check
    # (before the data read). The historical revert swaps the WHOLE live
    # body for the pre-migration image-reading form, so the probe module
    # reproduces the pre-fix behavior exactly (no root check, image read).
    new_body = (
        "                path = _read_path(path_addr)\n"
        "                # item-25 VFS-2: attached VFS re-route — the write lands in\n"
        "                # the VFS staging overlay (ext2 image behind it), rc 0/-1.\n"
        "                vfs = getattr(self, \"vfs\", None)\n"
        "                if vfs is not None:\n"
        "                    data = bytes((self.memory[data_addr + i] & 0xFF)\n"
        "                                 if 0 <= data_addr + i < len(self.memory) else 0\n"
        "                                 for i in range(length))\n"
        "                    rc = vfs.vfs_write(path, data)\n"
        "                    if rc == 0:\n"
        "                        print(f\"[SYSCALL] FILE_WRITE(vfs): {length} bytes from addr {data_addr} path {path!r}\")\n"
        "                    else:\n"
        "                        print(f\"[SYSCALL] FILE_WRITE(vfs) refused: {path!r}\")\n"
        "                    return rc\n"
        "                # backlog(d)/DEFECT-D (2026-09-16, handler 3/5): the data\n"
        "                # arg (r2) migrated from image space to RAM (self.memory),\n"
        "                # matching 0x01/0x02/0x04's precedent - file payloads are\n"
        "                # DATA, and the DEFECT-23-ROOT convention is RAM for data.\n"
        "                # path_addr (r1) is untouched - _read_path's own\n"
        "                # view-merge (RUN2/GH-9 in-flight work) is a separate\n"
        "                # concern, not part of this migration. Out-of-range source\n"
        "                # bytes read as 0 rather than raising (same no-crash\n"
        "                # convention 0x01's RAM read uses); FILE_WRITE's return\n"
        "                # value is unaffected either way.\n"
        "                # BK-44: host arm requires the realpath under a\n"
        "                # GLYPH_FS_ALLOW root — SAME check/model/rationale as the\n"
        "                # 0x13 arm below (BK-15): deny-by-default, the host-FS\n"
        "                # write primitive must not be cheaper to reach than the\n"
        "                # listing primitive. VFS-attached writes (the reroute\n"
        "                # above) are NOT host-FS and stay on the VFS's own\n"
        "                # containment (item-25).\n"
        "                import os as _os\n"
        "                _resolved = _os.path.realpath(path)\n"
        "                _roots = _get_fs_allow_roots()\n"
        "                if not any(_resolved == r or _resolved.startswith(r + _os.sep)\n"
        "                           for r in _roots):\n"
        "                    print(f\"[SYSCALL] FILE_WRITE denied: {path} not under GLYPH_FS_ALLOW\")\n"
        "                    return -1\n"
        "                data = bytes((self.memory[data_addr + i] & 0xFF)\n"
        "                             if 0 <= data_addr + i < len(self.memory) else 0\n"
        "                             for i in range(length))\n"
    )
    assert new_body in source, "anchor stale - re-sync with the live 0x03 handler"
    reverted_source = source.replace(new_body, old_body)
    assert reverted_source != source

    mod = types.ModuleType("glyph_isa_v2_pre_migration_0x03_probe")
    mod.__file__ = str(src_path)
    exec(compile(reverted_source, str(src_path), "exec"), mod.__dict__)

    test_file = tmp_path / "l5.bin"
    cpu = mod.GlyphCPUv2(mod.OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    path_bytes = str(test_file).encode() + b"\0"
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    for i, b in enumerate(path_bytes):
        # PATH is data: RAM view (view-merge retired 2026-09-22).
        cpu.memory[500 + i] = b
    # Seed the DATA as image pixels at ADDR (below the FS window, so no
    # aliasing): what the pre-migration handler read from.
    for i, b in enumerate(b"PQ"):
        cpu._mem_write(image, ADDR + i, b)
    cpu.registers[1] = 500
    cpu.registers[2] = ADDR
    cpu.registers[3] = 2
    rc = cpu._handle_syscall(0x03, image)
    assert rc == 0
    assert test_file.read_bytes() == b"PQ", (
        "pre-migration probe should have written the IMAGE-seeded bytes"
    )

    assert src_path.read_text() == source


def test_0x03_file_write_reads_ram_not_image(tmp_path):
    """POST-MIGRATION: FILE_WRITE's data arg (r2) now reads RAM
    (self.memory). path_addr (r1) is untouched - _read_path's view-merge
    is a separate concern. Image pixels at the same address are NOT read
    (that was the pre-migration behavior)."""
    test_file = tmp_path / "l6.bin"
    cpu, image = _fresh_cpu()
    path_bytes = str(test_file).encode() + b"\0"
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    # RAM holds one payload; the IMAGE at ADDR holds a DIFFERENT one. The
    # migrated handler must write the RAM bytes, proving it did not fall
    # back to the image view.
    cpu.memory[ADDR] = ord("R")
    cpu.memory[ADDR + 1] = ord("S")
    for i, b in enumerate(b"ZZ"):
        cpu._mem_write(image, ADDR + i, b)
    cpu.registers[1] = 500
    cpu.registers[2] = ADDR
    cpu.registers[3] = 2
    rc = cpu._handle_syscall(0x03, image)
    assert rc == 0
    assert test_file.read_bytes() == b"RS"


def test_0x03_file_write_out_of_range_source_reads_zero_not_crashes(tmp_path):
    test_file = tmp_path / "l7.bin"
    cpu, image = _fresh_cpu()
    path_bytes = str(test_file).encode() + b"\0"
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    cpu.registers[1] = 500
    cpu.registers[2] = 999_999
    cpu.registers[3] = 2
    rc = cpu._handle_syscall(0x03, image)  # must not raise
    assert rc == 0  # FILE_WRITE itself succeeded; OOR source bytes read as 0
    assert test_file.read_bytes() == b"\x00\x00"


def test_non_vacuity_neutered_0x03_fix_reads_image_again(tmp_path):
    """Neuter the RAM fix, confirm the pre-fix (image-reading) behavior
    reproduces identically."""
    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    target = (
        "                data = bytes((self.memory[data_addr + i] & 0xFF)\n"
        "                             if 0 <= data_addr + i < len(self.memory) else 0\n"
        "                             for i in range(length))\n"
    )
    assert target in source, "non-vacuity probe's anchor text is stale"
    neutered_source = source.replace(
        target,
        "                data = bytes(self._mem_read(image, data_addr + i) & 0xFF for i in range(length))\n",
    )
    assert neutered_source != source

    mod = types.ModuleType("glyph_isa_v2_neutered_0x03_probe")
    mod.__file__ = str(src_path)
    exec(compile(neutered_source, str(src_path), "exec"), mod.__dict__)

    test_file = tmp_path / "l8.bin"
    cpu = mod.GlyphCPUv2(mod.OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    path_bytes = str(test_file).encode() + b"\0"
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    # Same setup as the post-migration leg: RAM says RS, image says ZZ.
    # The neutered (pre-migration) engine must write the IMAGE bytes.
    cpu.memory[ADDR] = ord("R")
    cpu.memory[ADDR + 1] = ord("S")
    for i, b in enumerate(b"ZZ"):
        cpu._mem_write(image, ADDR + i, b)
    cpu.registers[1] = 500
    cpu.registers[2] = ADDR
    cpu.registers[3] = 2
    cpu._handle_syscall(0x03, image)
    assert test_file.read_bytes() == b"ZZ", (
        "expected the neutered (pre-migration) behavior to reappear - "
        "the image-seeded bytes should be written, not the RAM ones"
    )

    assert src_path.read_text() == source


def test_0x03_wgsl_stub_is_unchanged_no_op_documented():
    """WGSL's FILE_WRITE (0x03) is, and remains, an honest no-op stub
    returning 0 - GPU lanes have no host filesystem access, by design
    (see systems/SCOPING_MEMORY_VIEW_UNIFICATION.md #4). Same reasoning
    as the 0x04 leg: no real behavior to migrate and no divergence risk;
    documented explicitly so 'both engines' doesn't silently become
    'one engine, and nobody checked the other.'"""
    wgpu = pytest.importorskip("wgpu")
    from tools.glyph_isa_v2 import GlyphAssemblerV2
    from tools.glyph_gpt.runner import GlyphRunner

    om = OpcodeMapV2()
    prog = ["LDI r1 500", "LDI r2 2000", "LDI r3 2", "SYSCALL r9 0x03", "HALT"]
    img = GlyphAssemblerV2(om).assemble(prog, width_instrs=8)
    runner = GlyphRunner(image_or_path=img)
    rec = runner.run_wgsl(max_steps=50)
    assert rec.get("error") is None, rec.get("error")
    assert rec.get("halted"), rec
    assert rec["registers_full"][9] == 0, (
        "WGSL FILE_WRITE should still stub to 0 - if this changed, either "
        "someone added real (GPU-side) file I/O, which needs its own "
        "design pass, or something else regressed"
    )


def test_0x01_write_wgsl_parity():
    """Cross-engine parity leg (added on review, backfilling the gap
    fd24c76 left): WGSL's WRITE must read the same RAM value Python's
    does, via the new `ram` buffer (binding 5) + ram_read/ram_write in
    tools/wgsl_glyph_isa_v2.py - not the old mem_read (image pixels).
    Runs on real GPU hardware, not mocked."""
    wgpu = pytest.importorskip("wgpu")
    from tools.glyph_isa_v2 import GlyphAssemblerV2
    from tools.glyph_gpt.runner import GlyphRunner

    om = OpcodeMapV2()
    prog = [f"LDI r1 {ADDR}", "LDI r2 1", "SYSCALL r0 1", "HALT"]
    img = GlyphAssemblerV2(om).assemble(prog, width_instrs=8)
    runner = GlyphRunner(image_or_path=img)
    rec = runner.run_wgsl(max_steps=50, ram_seed={ADDR: 0xBB})
    assert rec.get("error") is None, rec.get("error")
    assert rec.get("halted"), rec
    assert rec["output"][0] == 0xBB, (
        f"WGSL WRITE read {rec['output'][0]:#x}, expected the RAM value "
        f"0xBB - if this reads 0 (image default), WGSL's WRITE has "
        f"regressed back to image space"
    )


# --- 0x08 SYSCALL_AUDIO_OUT (handler 4/5) ------------------------------------

def test_historical_pre_migration_0x08_audio_out_read_image_not_ram(tmp_path):
    """HISTORICAL: AUDIO_OUT's data arg (r2) used to read IMAGE space via
    _mem_read. Runs the pre-fix body through a neutered in-memory copy
    (live file untouched)."""
    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    new_body = (
        "                path = _read_path(path_addr)\n"
        "                # backlog(d)/DEFECT-D (2026-09-16, handler 4/5): the data\n"
        "                # arg (r2) migrated from image space to RAM (self.memory),\n"
        "                # matching 0x01/0x02/0x03/0x04's precedent - audio payloads\n"
        "                # are DATA, and the DEFECT-23-ROOT convention is RAM for\n"
        "                # data. path_addr (r1) is untouched - _read_path's own\n"
        "                # view-merge (RUN2/GH-9 in-flight work) is a separate\n"
        "                # concern, not part of this migration. Out-of-range source\n"
        "                # bytes read as 0 rather than raising (same no-crash\n"
        "                # convention 0x01's RAM read uses); AUDIO_OUT's return\n"
        "                # value is unaffected either way.\n"
        "                data = bytes((self.memory[data_addr + i] & 0xFF)\n"
        "                             if 0 <= data_addr + i < len(self.memory) else 0\n"
        "                             for i in range(length))\n"
    )
    assert new_body in source, "anchor stale - re-sync with the live 0x08 handler"
    reverted_body = (
        "                path = _read_path(path_addr)\n"
        "                data = bytes(self._mem_read(image, data_addr + i) & 0xFF for i in range(length))\n"
    )
    reverted_source = source.replace(new_body, reverted_body)
    assert reverted_source != source

    mod = types.ModuleType("glyph_isa_v2_pre_migration_0x08_probe")
    mod.__file__ = str(src_path)
    exec(compile(reverted_source, str(src_path), "exec"), mod.__dict__)

    import scipy.io.wavfile as wavfile
    from src.codec.phy import Phy16Tone

    wav_path = tmp_path / "l9.wav"
    cpu = mod.GlyphCPUv2(mod.OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    path_bytes = str(wav_path).encode() + b"\0"
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    # Seed the DATA as image pixels at ADDR: what the pre-migration handler read.
    for i, b in enumerate(b"PQ"):
        cpu._mem_write(image, ADDR + i, b)
    cpu.registers[1] = 500
    cpu.registers[2] = ADDR
    cpu.registers[3] = 2
    rc = cpu._handle_syscall(0x08, image)
    assert rc == 0
    _, samples = wavfile.read(str(wav_path))
    assert Phy16Tone.decode(samples) == b"PQ", (
        "pre-migration probe should have encoded the IMAGE-seeded bytes"
    )

    assert src_path.read_text() == source


def test_0x08_audio_out_reads_ram_not_image(tmp_path):
    """POST-MIGRATION (handler 4/5): AUDIO_OUT's data arg (r2) now reads
    RAM (self.memory). path_addr (r1) is untouched. Image pixels at the
    same address are NOT read (that was the pre-migration behavior)."""
    wav_path = tmp_path / "l10.wav"
    cpu, image = _fresh_cpu()
    path_bytes = str(wav_path).encode() + b"\0"
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    # RAM holds one payload; the IMAGE at ADDR holds a DIFFERENT one. The
    # migrated handler must encode the RAM bytes.
    cpu.memory[ADDR] = ord("R")
    cpu.memory[ADDR + 1] = ord("S")
    for i, b in enumerate(b"ZZ"):
        cpu._mem_write(image, ADDR + i, b)
    cpu.registers[1] = 500
    cpu.registers[2] = ADDR
    cpu.registers[3] = 2
    rc = cpu._handle_syscall(0x08, image)
    assert rc == 0
    import scipy.io.wavfile as wavfile
    from src.codec.phy import Phy16Tone
    _, samples = wavfile.read(str(wav_path))
    assert Phy16Tone.decode(samples) == b"RS"


def test_0x08_audio_out_out_of_range_source_reads_zero_not_crashes(tmp_path):
    wav_path = tmp_path / "l11.wav"
    cpu, image = _fresh_cpu()
    path_bytes = str(wav_path).encode() + b"\0"
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    cpu.registers[1] = 500
    cpu.registers[2] = 999_999
    cpu.registers[3] = 2
    rc = cpu._handle_syscall(0x08, image)  # must not raise
    assert rc == 0  # AUDIO_OUT itself succeeded; OOR source bytes read as 0
    import scipy.io.wavfile as wavfile
    from src.codec.phy import Phy16Tone
    _, samples = wavfile.read(str(wav_path))
    assert Phy16Tone.decode(samples) == b"\x00\x00"


def test_non_vacuity_neutered_0x08_fix_reads_image_again(tmp_path):
    """Neuter the RAM fix, confirm the pre-fix (image-reading) behavior
    reproduces identically."""
    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    target = (
        "                data = bytes((self.memory[data_addr + i] & 0xFF)\n"
        "                             if 0 <= data_addr + i < len(self.memory) else 0\n"
        "                             for i in range(length))\n"
    )
    # The LIVE 0x03 handler legitimately contains the identical migrated
    # RAM-read block (handler 3/5, landed 85922f8) - scope the swap to the
    # 0x08 handler's slice so the probe stays surgical.
    h08 = source[source.find("elif syscall_num == 0x08:"):source.find("elif syscall_num == 0x09:")]
    assert target in h08, "non-vacuity probe's anchor text is stale"
    # Replace INSIDE the 0x08 slice only - source.replace(count=1) alone
    # would hit 0x03's identical migrated block first (it comes earlier
    # in the file), neutering the wrong handler.
    neutered_source = source.replace(
        h08,
        h08.replace(
            target,
            "                data = bytes(self._mem_read(image, data_addr + i) & 0xFF for i in range(length))\n",
        ),
    )
    # Verify the swap landed INSIDE the 0x08 handler (and nowhere else).
    h08_after = neutered_source[neutered_source.find("elif syscall_num == 0x08:"):neutered_source.find("elif syscall_num == 0x09:")]
    assert "self._mem_read(image, data_addr + i)" in h08_after, (
        "the surgical swap did not land inside the 0x08 handler"
    )
    h03_after = neutered_source[neutered_source.find("elif syscall_num == 0x03:"):neutered_source.find("elif syscall_num == 0x04:")]
    assert "self._mem_read(image, data_addr + i)" not in h03_after, (
        "the swap leaked into the 0x03 handler - the probe neutered the wrong handler"
    )
    assert neutered_source != source

    mod = types.ModuleType("glyph_isa_v2_neutered_0x08_probe")
    mod.__file__ = str(src_path)
    exec(compile(neutered_source, str(src_path), "exec"), mod.__dict__)

    wav_path = tmp_path / "l12.wav"
    cpu = mod.GlyphCPUv2(mod.OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    path_bytes = str(wav_path).encode() + b"\0"
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    # Same setup as the post-migration leg: RAM says RS, image says ZZ.
    cpu.memory[ADDR] = ord("R")
    cpu.memory[ADDR + 1] = ord("S")
    for i, b in enumerate(b"ZZ"):
        cpu._mem_write(image, ADDR + i, b)
    cpu.registers[1] = 500
    cpu.registers[2] = ADDR
    cpu.registers[3] = 2
    cpu._handle_syscall(0x08, image)
    import scipy.io.wavfile as wavfile
    from src.codec.phy import Phy16Tone
    _, samples = wavfile.read(str(wav_path))
    assert Phy16Tone.decode(samples) == b"ZZ", (
        "expected the neutered (pre-migration) behavior to reappear - "
        "the image-seeded bytes should be encoded, not the RAM ones"
    )

    assert src_path.read_text() == source


def test_0x08_wgsl_unknown_stub_is_unchanged_documented():
    """WGSL has NO AUDIO_OUT (0x08) branch at all - the syscall number
    falls through to the Unknown branch and returns -1 (0xFFFFFFFF).
    There is no host audio device on GPU lanes, so there is no real
    behavior to migrate and no divergence risk: an unknown-syscall -1
    doesn't fabricate data the way a silently-wrong RAM/image read
    would. This test documents that explicitly rather than skipping
    the 'both engines' step silently."""
    wgpu = pytest.importorskip("wgpu")
    from tools.glyph_isa_v2 import GlyphAssemblerV2
    from tools.glyph_gpt.runner import GlyphRunner

    om = OpcodeMapV2()
    prog = ["LDI r1 500", "LDI r2 2000", "LDI r3 2", "SYSCALL r9 0x08", "HALT"]
    img = GlyphAssemblerV2(om).assemble(prog, width_instrs=8)
    runner = GlyphRunner(image_or_path=img)
    rec = runner.run_wgsl(max_steps=50)
    assert rec.get("error") is None, rec.get("error")
    assert rec.get("halted"), rec
    assert rec["registers_full"][9] == 0xFFFFFFFF, (
        "WGSL AUDIO_OUT should still fall through to the Unknown branch "
        "(-1) - if this changed, either someone added real (GPU-side) "
        "audio output, which needs its own design pass, or the unknown-"
        "syscall fallthrough itself regressed"
    )


# --- 0x09 SYSCALL_AUDIO_IN (handler 5/5) -------------------------------------

def test_historical_pre_migration_0x09_audio_in_wrote_image_not_ram(tmp_path):
    """HISTORICAL: AUDIO_IN's dest (r2) used to be written to IMAGE space
    via _mem_write. Runs the pre-fix body through a neutered in-memory
    copy (live file untouched)."""
    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    new_body = (
        "                for i, byte_val in enumerate(decoded):\n"
        "                    a = dest_addr + i\n"
        "                    if 0 <= a < len(self.memory):\n"
        "                        self.memory[a] = byte_val\n"
    )
    assert new_body in source, "anchor stale - re-sync with the live 0x09 handler"
    reverted_body = (
        "                for i, byte_val in enumerate(decoded):\n"
        "                    self._mem_write(image, dest_addr + i, byte_val)\n"
    )
    reverted_source = source.replace(new_body, reverted_body)
    assert reverted_source != source

    mod = types.ModuleType("glyph_isa_v2_pre_migration_0x09_probe")
    mod.__file__ = str(src_path)
    exec(compile(reverted_source, str(src_path), "exec"), mod.__dict__)

    import scipy.io.wavfile as wavfile
    from src.codec.phy import Phy16Tone

    wav_path = tmp_path / "l13.wav"
    symbols = Phy16Tone.bytes_to_symbols(b"WX")
    audio = Phy16Tone.encode_symbols(symbols)
    wavfile.write(str(wav_path), Phy16Tone.SAMPLE_RATE,
                  (audio * 32767).astype(np.int16))

    cpu = mod.GlyphCPUv2(mod.OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    path_bytes = str(wav_path).encode() + b"\0"
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    cpu.registers[1] = 500
    cpu.registers[2] = ADDR
    cpu.registers[3] = 2
    rc = cpu._handle_syscall(0x09, image)
    assert rc == 2
    # Pre-migration probe: dest bytes landed in IMAGE space, RAM untouched.
    assert bytes((cpu._mem_read(image, ADDR + i) & 0xFF for i in range(2))) == b"WX", (
        "pre-migration probe should have written the dest to IMAGE space"
    )
    assert cpu.memory[ADDR] == 0 and cpu.memory[ADDR + 1] == 0

    assert src_path.read_text() == source


def test_0x09_audio_in_writes_ram_not_image(tmp_path):
    """POST-MIGRATION (handler 5/5): AUDIO_IN's dest (r2) is now written
    to RAM (self.memory). path_addr (r1) is untouched. Image pixels at the
    same address are NOT written (that was the pre-migration behavior)."""
    import scipy.io.wavfile as wavfile
    from src.codec.phy import Phy16Tone

    wav_path = tmp_path / "l14.wav"
    symbols = Phy16Tone.bytes_to_symbols(b"RS")
    audio = Phy16Tone.encode_symbols(symbols)
    wavfile.write(str(wav_path), Phy16Tone.SAMPLE_RATE,
                  (audio * 32767).astype(np.int16))

    cpu, image = _fresh_cpu()
    path_bytes = str(wav_path).encode() + b"\0"
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    cpu.registers[1] = 500
    cpu.registers[2] = ADDR
    cpu.registers[3] = 2
    rc = cpu._handle_syscall(0x09, image)
    assert rc == 2
    assert bytes((cpu.memory[ADDR + i] & 0xFF for i in range(2))) == b"RS", (
        "decoded bytes must land in RAM, not image pixels"
    )
    for i in range(2):
        assert cpu._mem_read(image, ADDR + i) == 0, (
            "image pixels at the dest must stay untouched by the migrated handler"
        )


def test_0x09_audio_in_out_of_range_dest_drops_not_crashes(tmp_path):
    import scipy.io.wavfile as wavfile
    from src.codec.phy import Phy16Tone

    wav_path = tmp_path / "l15.wav"
    symbols = Phy16Tone.bytes_to_symbols(b"QX")
    audio = Phy16Tone.encode_symbols(symbols)
    wavfile.write(str(wav_path), Phy16Tone.SAMPLE_RATE,
                  (audio * 32767).astype(np.int16))

    cpu, image = _fresh_cpu()
    path_bytes = str(wav_path).encode() + b"\0"
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    cpu.registers[1] = 500
    cpu.registers[2] = 999_999
    cpu.registers[3] = 2
    rc = cpu._handle_syscall(0x09, image)  # must not raise
    assert rc == 2  # decode itself succeeded; OOR dest bytes are dropped (0x04 convention)


def test_non_vacuity_neutered_0x09_fix_writes_image_again(tmp_path):
    """Neuter the RAM fix, confirm the pre-fix (image-writing) behavior
    reproduces identically."""
    import scipy.io.wavfile as wavfile
    from src.codec.phy import Phy16Tone

    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    target = (
        "                for i, byte_val in enumerate(decoded):\n"
        "                    a = dest_addr + i\n"
        "                    if 0 <= a < len(self.memory):\n"
        "                        self.memory[a] = byte_val\n"
    )
    # Scope the swap to the 0x09 handler's slice - the same defense as the
    # 0x08 probe: source.replace(count=1) alone could hit an earlier
    # identical block if one ever appears.
    h09 = source[source.find("elif syscall_num == 0x09:"):source.find("elif syscall_num == 0x10:")]
    assert target in h09, "non-vacuity probe's anchor text is stale"
    neutered_source = source.replace(
        h09,
        h09.replace(
            target,
            "                for i, byte_val in enumerate(decoded):\n"
            "                    self._mem_write(image, dest_addr + i, byte_val)\n",
        ),
    )
    # Verify the swap landed INSIDE the 0x09 handler (and nowhere else).
    h09_after = neutered_source[neutered_source.find("elif syscall_num == 0x09:"):neutered_source.find("elif syscall_num == 0x10:")]
    assert "self._mem_write(image, dest_addr + i, byte_val)" in h09_after, (
        "the surgical swap did not land inside the 0x09 handler"
    )
    h08_after = neutered_source[neutered_source.find("elif syscall_num == 0x08:"):neutered_source.find("elif syscall_num == 0x09:")]
    assert "self._mem_write(image, dest_addr + i, byte_val)" not in h08_after, (
        "the swap leaked into the 0x08 handler - the probe neutered the wrong handler"
    )
    # 0x08's own migrated RAM-read block must be intact (no collateral edit).
    assert "self.memory[data_addr + i] & 0xFF" in h08_after
    assert neutered_source != source

    mod = types.ModuleType("glyph_isa_v2_neutered_0x09_probe")
    mod.__file__ = str(src_path)
    exec(compile(neutered_source, str(src_path), "exec"), mod.__dict__)

    wav_path = tmp_path / "l16.wav"
    symbols = Phy16Tone.bytes_to_symbols(b"WX")
    audio = Phy16Tone.encode_symbols(symbols)
    wavfile.write(str(wav_path), Phy16Tone.SAMPLE_RATE,
                  (audio * 32767).astype(np.int16))

    cpu = mod.GlyphCPUv2(mod.OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    path_bytes = str(wav_path).encode() + b"\0"
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    # PATH is data: seed the RAM view (DEFECT-23-ROOT convention);
    # the image-seeded form relied on _read_path's view-merge,
    # retired 2026-09-22 (claim-queue item 2 step 2).
    for i, b in enumerate(path_bytes):
        cpu.memory[500 + i] = b
    cpu.registers[1] = 500
    cpu.registers[2] = ADDR
    cpu.registers[3] = 2
    cpu._handle_syscall(0x09, image)
    assert bytes((cpu._mem_read(image, ADDR + i) & 0xFF for i in range(2))) == b"WX", (
        "expected the neutered (pre-migration) behavior to reappear - "
        "the dest bytes should land in image pixels, not RAM"
    )
    assert cpu.memory[ADDR] == 0 and cpu.memory[ADDR + 1] == 0

    assert src_path.read_text() == source


def test_0x09_wgsl_unknown_stub_is_unchanged_documented():
    """WGSL has NO AUDIO_IN (0x09) branch - the syscall number falls
    through to the Unknown branch and returns -1 (0xFFFFFFFF). There is
    no host audio capture device on GPU lanes, so there is no real
    behavior to migrate and no divergence risk: an unknown-syscall -1
    doesn't fabricate data the way a silently-wrong RAM/image write
    would. This test documents that explicitly rather than skipping
    the 'both engines' step silently."""
    wgpu = pytest.importorskip("wgpu")
    from tools.glyph_isa_v2 import GlyphAssemblerV2
    from tools.glyph_gpt.runner import GlyphRunner

    om = OpcodeMapV2()
    prog = ["LDI r1 500", "LDI r2 2000", "LDI r3 2", "SYSCALL r9 0x09", "HALT"]
    img = GlyphAssemblerV2(om).assemble(prog, width_instrs=8)
    runner = GlyphRunner(image_or_path=img)
    rec = runner.run_wgsl(max_steps=50)
    assert rec.get("error") is None, rec.get("error")
    assert rec.get("halted"), rec
    assert rec["registers_full"][9] == 0xFFFFFFFF, (
        "WGSL AUDIO_IN should still fall through to the Unknown branch "
        "(-1) - if this changed, either someone added real (GPU-side) "
        "audio capture, which needs its own design pass, or the unknown-"
        "syscall fallthrough itself regressed"
    )


# --- 0x10 SYSCALL_BOOT_LINUX (backlog (d) residual, 2026-09-22) --------------
# The scoping receipt (systems/SCOPING_MEMORY_VIEW_UNIFICATION.md #2) listed
# 0x10's container-header read as IMAGE-space; the 5/5 sweep (addendum 109)
# retired the data-arg members but left 0x10 (its fixtures seeded via
# cpu._mem_write, so nothing forced the question). This section finishes the
# sweep: the VAC2 header is DATA (it describes a payload, it is not code),
# so it reads RAM one byte per word - the same convention as 0x01/0x02/0x04/
# 0x08/0x09. 0x11 STORE_CODE stays pixel per DEFECT-27 (unchanged, terminal).

VAC2_SIG_PIXEL0 = 0x434156  # OLD (pre-migration) pixel packing of 'V','A','C' - historical legs only
VAC2_SIG_PIXEL1 = 0x000032  # OLD pixel packing of '2'
VAC2_BYTES = b"VAC2"        # POST-MIGRATION: one byte per word, low byte first


def _seed_vac2(cpu, image, addr, ram_side):
    """Seed a valid VAC2 signature on one side and a decoy on the other.

    ram_side=True: RAM carries the real signature, image carries a decoy.
    ram_side=False: roles reversed (the pre-migration expectation).
    Post-migration byte layout (glyph_isa_v2.py 0x10 docstring): one byte
    per word, LOW byte first: [addr..addr+3] = 'V','A','C','2'.
    """
    real = list(VAC2_BYTES)
    decoy = [0x41, 0x42, 0x43, 0x44]  # 'A','B','C','D' - not VAC2
    r = real if ram_side else decoy
    d = decoy if ram_side else real
    for i in range(4):
        cpu.memory[addr + i] = r[i]
        cpu._mem_write(image, addr + i, d[i])


def test_historical_pre_migration_0x10_boot_linux_read_image_not_ram():
    """HISTORICAL: 0x10 used to read its VAC2 header from IMAGE space via
    _mem_read (glyph_isa_v2.py 0x10 arm, pre-migration). Frozen by running
    the OLD body verbatim against today's seeding helpers: image-seeded
    signature + empty RAM -> recognized (return 0)."""
    cpu, image = _fresh_cpu()
    # OLD behavior, replayed here (not imported): read via _mem_read.
    cpu._mem_write(image, ADDR, VAC2_SIG_PIXEL0)
    cpu._mem_write(image, ADDR + 1, VAC2_SIG_PIXEL1)
    p0 = cpu._mem_read(image, ADDR)
    p1 = cpu._mem_read(image, ADDR + 1)
    sig = bytes((p0 & 0xFF, (p0 >> 8) & 0xFF, (p0 >> 16) & 0xFF, p1 & 0xFF))
    assert sig == b"VAC2"  # the old mechanism recognized this seeding
    assert cpu.memory[ADDR] == 0  # RAM was untouched by this seeding


def test_0x10_boot_linux_reads_ram_not_image():
    """POST-MIGRATION: 0x10's container header (r1) reads RAM
    (self.memory), one byte per word. Image pixels at the same address are
    NOT consulted (that was the pre-migration behavior)."""
    cpu, image = _fresh_cpu()
    _seed_vac2(cpu, image, ADDR, ram_side=True)
    cpu.registers[1] = ADDR
    cpu.registers[2] = 0x05
    assert cpu._handle_syscall(0x10, image) == 0, (
        "expected recognition from the RAM-seeded signature - if this "
        "returns -1, the handler is still reading image space"
    )


def test_0x10_boot_linux_image_signature_alone_is_not_recognized():
    """The mirror of the post-migration leg: an image-seeded signature
    (old-style seeding, RAM zeroed) must now be REFUSED (-1). This is the
    leg that goes RED before the fix and GREEN after."""
    cpu, image = _fresh_cpu()
    _seed_vac2(cpu, image, ADDR, ram_side=False)
    cpu.registers[1] = ADDR
    cpu.registers[2] = 0x05
    assert cpu._handle_syscall(0x10, image) == -1, (
        "image-space header was recognized - 0x10 still reads image space"
    )


def test_0x10_boot_linux_out_of_range_addr_reads_zero_not_crash():
    """No-crash convention: an out-of-RAM container_addr reads zeros ->
    invalid signature -> -1, never IndexError."""
    cpu, image = _fresh_cpu()
    cpu.registers[1] = 999_999
    cpu.registers[2] = 0
    assert cpu._handle_syscall(0x10, image) == -1


def test_non_vacuity_neutered_0x10_fix_reads_image_again():
    """Prove the migration is load-bearing: neuter it out-of-tree and
    confirm the OLD (image-reading) behavior reappears - the mirror leg
    above must flip back to recognizing the image-seeded signature."""
    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    target = (
        "            p0 = (self.memory[container_addr] if 0 <= container_addr < len(self.memory) else 0)\n"
        "            p1 = (self.memory[container_addr + 1] if 0 <= container_addr + 1 < len(self.memory) else 0)\n"
        "            p2 = (self.memory[container_addr + 2] if 0 <= container_addr + 2 < len(self.memory) else 0)\n"
        "            p3 = (self.memory[container_addr + 3] if 0 <= container_addr + 3 < len(self.memory) else 0)\n"
        "            sig = bytes((p0 & 0xFF, p1 & 0xFF, p2 & 0xFF, p3 & 0xFF))\n"
    )
    assert target in source, "non-vacuity probe's anchor text is stale"
    neutered_source = source.replace(
        target,
        "            p0 = self._mem_read(image, container_addr)\n"
        "            p1 = self._mem_read(image, container_addr + 1)\n"
        "            sig = bytes((p0 & 0xFF, (p0 >> 8) & 0xFF, (p0 >> 16) & 0xFF, p1 & 0xFF))\n",
    )
    assert neutered_source != source

    mod = types.ModuleType("glyph_isa_v2_neutered_0x10_probe")
    mod.__file__ = str(src_path)
    exec(compile(neutered_source, str(src_path), "exec"), mod.__dict__)

    cpu = mod.GlyphCPUv2(mod.OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    cpu._mem_write(image, ADDR, VAC2_SIG_PIXEL0)
    cpu._mem_write(image, ADDR + 1, VAC2_SIG_PIXEL1)
    cpu.registers[1] = ADDR
    cpu.registers[2] = 0x05
    assert cpu._handle_syscall(0x10, image) == 0, (
        "expected the neutered (pre-migration) behavior to reappear - "
        "if this fails, the GREEN legs above aren't actually testing the fix"
    )

    assert src_path.read_text() == source


def test_0x10_boot_linux_wgsl_parity():
    """Cross-engine parity leg (the file's both-engines-per-handler rule):
    WGSL's legacy-table 0x10 branch must read the VAC2 header from the
    `ram` buffer via ram_read - recognizing a RAM-seeded container and
    refusing an image-only one - matching the CPU engine. Runs on real
    GPU hardware, not mocked."""
    wgpu = pytest.importorskip("wgpu")
    from tools.glyph_isa_v2 import GlyphAssemblerV2
    from tools.glyph_gpt.runner import GlyphRunner

    # RAM-seeded: recognized (0). Bytes packed one per word, low byte first.
    b = b"VAC2"
    om = OpcodeMapV2()
    prog = ["LDI r1 2000", "LDI r2 5", "SYSCALL r6 0x10", "HALT"]
    img = GlyphAssemblerV2(om).assemble(prog, width_instrs=8)
    runner = GlyphRunner(image_or_path=img)
    rec = runner.run_wgsl(max_steps=50, ram_seed={
        2000: b[0], 2001: b[1], 2002: b[2], 2003: b[3],
    })
    assert rec.get("error") is None, rec.get("error")
    assert rec.get("halted"), rec
    assert rec["registers_full"][6] == 0, (
        f"WGSL BOOT_LINUX returned {rec['registers_full'][6]}, expected 0 "
        f"for a RAM-seeded VAC2 container - WGSL's 0x10 branch has "
        f"diverged from the CPU engine"
    )

    # Image-seeded only: refused (-1) - ram_read must not fall back to pixels.
    img2 = GlyphAssemblerV2(om).assemble(prog, width_instrs=8)
    runner2 = GlyphRunner(image_or_path=img2)
    rec2 = runner2.run_wgsl(max_steps=50)
    assert rec2.get("error") is None, rec2.get("error")
    assert rec2.get("halted"), rec2
    assert rec2["registers_full"][6] == 0xFFFFFFFF, (
        "WGSL BOOT_LINUX recognized an image-only container - WGSL's "
        "0x10 must read the ram buffer (ram_read), not image pixels"
    )
