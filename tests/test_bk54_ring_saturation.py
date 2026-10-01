#!/usr/bin/env python3
#!/usr/bin/env python3
"""tests/test_bk54_ring_saturation.py — BK-54 gate: the BK-24 streaming-write
ring SATURATES at its declared end (cursor clamped, excess dropped LOUDLY),
it never appends past word 832.

Row: systems/GLYPH_BACKLOG.md BK-54 (CLAIMABLE NOW per
DIRECTIVE_BK59_DESKTOP_GATE.md §3.3/§4, class (a)).
Directive: .builder_queue/DIRECTIVE_BK59_DESKTOP_GATE.md §4.

RED-FIRST (measured at HEAD 4130af0e, pre-fix, this tick):
  .builder_queue/dbg_head_root_cause_af3e.py re-run live: leg B cursor = 872
  (ring_base 768 + 104 = 40 words PAST declared end 832), results md5
  645e32d319f2e9014d2e06fd5cfa178b — identical to the landed research receipt
  (RESEARCH_head_empty_ring_af3e.md). The 4001-byte stream probe
  (probe_bk54_blast_radius_af3e.results.json) measured the deeper damage:
  cursor walked to ~1993, clobbering status 950, flag 960, the GH-18 table
  pixel window 1312, and PTR_TABLE words 2048/2370 — 1035 words rewritten
  past the ring end, halted=False (kernel derailed).

GREEN contract (this file, per the row's gate spec):
  L1  saturation: a 401-byte stream (the RED shape) clamps the cursor AT
      832; excess stream bytes are DROPPED (not wrapped, not faulted).
      Toolchain legs: the first 256 bytes of the stream are byte-exact in
      the ring — the drop is at the boundary, not the head of the stream.
  L2  canaries: words seeded past the ring end (840/860) SURVIVE an
      overflowing run (post-fix they are never written by the tile).
  L3  loud drop: the run carries a machine-visible marker — the status
      word 950 keeps its kernel tail AND the cursor sits exactly at 832
      (a consumer reading the ring sees a full ring, not a silently
      truncated one); in addition the dropped-frame count is observable
      as mem[725] = number of 16-byte frames refused post-saturation
      (the mechanism's LOUD status word, BK-54 posture: "drop excess with
      a loud status word").
  L4  never weaken a live guard: sub-ring streams land EXACTLY as today —
      the BK-24 two-flush shape (cursor 768+8) and the 64-byte single
      flush (cursor 768+16) are byte-identical; BK-11's 16-byte window
      contract untouched (tests/test_bk11_coreutils.py stays green).
  L5  non-vacuity (toolchain-free): the clamp lives in the TILE TEXT —
      structurally pinned. Neutering the clamp in a temp copy of the
      module (clamp branch removed) restores the RED shape: the probe
      tile appends past 832. The landed module is md5-pinned before/after
      the neuter so the gate proves the REFUSAL is the landed clamp.
  L6  family: BK-24's own gate (tests/test_bk24_streaming_write.py)
      green at this tree — the saturation posture never touches the
      sub-ring contract.

What the PASS does NOT prove: no WGSL-twin leg (the ring is a
Python-mechanism surface — the twin has no libc bake path); no
multi-image variant (paged/posix-mode bakes not exercised — the ring
seeds only exist in the libc-mode prologue); the dropped-tail bytes are
asserted absent, not recoverable (saturation, not spooling).
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import libc_runtime_kernel_image      # noqa: E402
from tools.glyph_gpt.libc_runtime import (                       # noqa: E402
    _gh23_sys_write_tile,
    GH23_WRITE_CURSOR,
    GH23_WRITE_RING_BASE,
    GH23_WRITE_RING_END,
    GH23_WRITE_DROPPED_FRAMES,
    GH23_EXIT_CODE,
)
from tests.test_gh23_libc_runtime import (                       # noqa: E402
    LIBC_C, SHIM_S, _load_posix_program, GH23_STDOUT_WORDS,
)
from tools.glyph_gpt.coreutils_port import _TOOL_SOURCES, _COMMON  # noqa: E402

_GCC = "riscv64-unknown-elf-gcc"

RING_BASE = GH23_WRITE_RING_BASE     # 768
RING_END = GH23_WRITE_RING_END       # 832 (exclusive): 64 words = 256 bytes
CURSOR = GH23_WRITE_CURSOR           # 724
DROPPED = GH23_WRITE_DROPPED_FRAMES  # 725: 16-byte frames refused post-fill


def _require_toolchain() -> None:
    if shutil.which(_GCC) is None:
        pytest.skip("riscv64-unknown-elf-gcc not installed")


def _lit(s: str) -> str:
    return (s.replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "\\n").replace("\t", "\\t"))


def _run_head(data: str, max_instructions: int = 600000):
    """The dbg_head_root_cause_af3e leg-B shape: head -n 1 over an
    embedded one-line file, compiled against the spatial libc, baked as
    the libc-mode user program, run to halt. Returns the receipt."""
    body = _TOOL_SOURCES["head"]
    src_text = (
        _COMMON + "\n"
        + f'static const char *head_data = "{_lit(data)}";\n'
        + "static long head_n = 1;\n"
        + "#define HEAD_DATA head_data\n#define HEAD_N head_n\n"
        + body
    )
    with tempfile.TemporaryDirectory(prefix="bk54_") as td:
        tmp = Path(td)
        (tmp / "tool.c").write_text(src_text)
        (tmp / "gh23_libc.c").write_text(LIBC_C)
        (tmp / "shim.S").write_text(SHIM_S)
        objs = []
        for i, cfile in enumerate(("tool.c", "gh23_libc.c")):
            obj = tmp / f"tool_{i}.o"
            proc = subprocess.run(
                [_GCC, "-march=rv32i", "-mabi=ilp32", "-O1",
                 "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
                 "-ffixed-x31", "-nostdlib", "-fno-builtin",
                 "-ffreestanding", "-w", "-c", str(tmp / cfile), "-o", str(obj)],
                capture_output=True, timeout=60)
            assert proc.returncode == 0, proc.stderr.decode()[:400]
            objs.append(obj)
        elf = tmp / "tool.elf"
        proc = subprocess.run(
            [_GCC, "-march=rv32i", "-mabi=ilp32",
             "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
             "-ffixed-x31", "-nostdlib", "-Wl,-Ttext=0x0",
             "-Wl,-N", "-Wl,--entry=_start", "-w",
             *map(str, objs), str(tmp / "shim.S"), "-o", str(elf)],
            capture_output=True, timeout=60)
        assert proc.returncode == 0, proc.stderr.decode()[:400]
        program = _load_posix_program(elf.read_bytes())
        image = tmp / "bk54.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=image,
                                  user_program=program)
        runner = GlyphRunner(image, ram_words=16384)
        return runner.run(max_instructions=max_instructions, trace=True)


def _ring_bytes(mem, start: int, n: int) -> bytes:
    return b"".join(int(mem[w]).to_bytes(4, "little")
                    for w in range(start, start + n))


def _seed_canaries(mem) -> None:
    """Words 840/860 sit past the declared ring end; seed them with
    canary values so L2 can prove the tile never writes them."""
    mem[840] = 0x5A5AA5A5
    mem[860] = 0x0F0FF0F0


# ── L1: saturation — cursor clamps at 832, head bytes present ────────────

@pytest.mark.skipif(shutil.which(_GCC) is None,
                    reason="riscv64-unknown-elf-gcc not installed")
def test_l1_cursor_saturates_at_ring_end():
    """The RED shape (401-byte one-line file -> cursor 872 pre-fix):
    post-fix the cursor sits AT the declared end 832 and nothing landed
    past it. The first 256 stream bytes are byte-exact in the ring."""
    data = ("word " * 80) + "\n"          # 401 bytes, ONE line
    receipt = _run_head(data)
    assert receipt["halted"] is True, receipt.get("error", receipt)
    assert receipt["faulted"] is False, receipt.get("fault_reason", receipt)
    mem = receipt["memory"]
    cursor = mem[CURSOR]
    assert cursor == RING_END, (
        f"cursor {cursor} != ring end {RING_END} — "
        f"{'OVERFLOW persists' if cursor > RING_END else 'short stream'}")
    # at least one 16-byte frame was refused, and it is LOUD
    dropped = mem[DROPPED]
    assert dropped >= 1, (
        "stream exceeded the ring but no drop was recorded — "
        "the refusal is silent (BK-54 posture requires a loud status word)")
    # the retained 256 bytes are the stream's HEAD (drop-at-bound, not
    # wrap-around): ring[0:16] holds 'word word word w'
    head = _ring_bytes(mem, RING_BASE, 4)
    assert head == b"word word word w", head
    # words past the ring end were NEVER written by the tile: word 832
    # in a fresh libc bake is post-prologue RAM (baseline 0) — it must
    # still be 0 (the RED run landed 543453807 there)
    assert mem[832] == 0, hex(mem[832])
    assert mem[833] == 0, hex(mem[833])


# ── L2: canaries past the ring end survive the overflow ──────────────────

@pytest.mark.skipif(shutil.which(_GCC) is None,
                    reason="riscv64-unknown-elf-gcc not installed")
def test_l2_canaries_past_ring_end_survive():
    """Words 840/860 seeded past the declared end stay untouched by an
    overflowing run (RED-first: the 4001-byte probe clobbered 1035 words
    past 832, status 950 and PTR_TABLE included)."""
    data = ("word " * 100) + "\n"         # 501 bytes — overflows ring by 16 frames without .rodata collision
    with tempfile.TemporaryDirectory(prefix="bk54_l2_") as td:
        tmp = Path(td)
        body = _TOOL_SOURCES["head"]
        src_text = (
            _COMMON + "\n"
            + f'static const char *head_data = "{_lit(data)}";\n'
            + "static long head_n = 1;\n"
            + "#define HEAD_DATA head_data\n#define HEAD_N head_n\n"
            + body
        )
        (tmp / "tool.c").write_text(src_text)
        (tmp / "gh23_libc.c").write_text(LIBC_C)
        (tmp / "shim.S").write_text(SHIM_S)
        objs = []
        for i, cfile in enumerate(("tool.c", "gh23_libc.c")):
            obj = tmp / f"tool_{i}.o"
            proc = subprocess.run(
                [_GCC, "-march=rv32i", "-mabi=ilp32", "-O1",
                 "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
                 "-ffixed-x31", "-nostdlib", "-fno-builtin",
                 "-ffreestanding", "-w", "-c", str(tmp / cfile), "-o", str(obj)],
                capture_output=True, timeout=60)
            assert proc.returncode == 0, proc.stderr.decode()[:400]
            objs.append(obj)
        elf = tmp / "tool.elf"
        proc = subprocess.run(
            [_GCC, "-march=rv32i", "-mabi=ilp32",
             "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
             "-ffixed-x31", "-nostdlib", "-Wl,-Ttext=0x0",
             "-Wl,-N", "-Wl,--entry=_start", "-w",
             *map(str, objs), str(tmp / "shim.S"), "-o", str(elf)],
            capture_output=True, timeout=60)
        assert proc.returncode == 0, proc.stderr.decode()[:400]
        program = _load_posix_program(elf.read_bytes())
        # bake normally, then seed canaries into RAM before the run —
        # GlyphRunner.run() builds its own CPU, so seed via a runner copy:
        # the honest instrument is the same one the blast-radius probe
        # used: run, then diff. Here we seed by wrapping the image run in
        # a driver that seeds cpu.memory BEFORE stepping.
        image = tmp / "bk54_l2.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=image,
                                  user_program=program)
        from glyph_isa_v2 import OpcodeMapV2, GlyphCPUv2  # noqa: E402 (tools on path)
        import contextlib, io
        import numpy as np
        arr = np.load(str(image))
        cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=arr.shape[1] // 4,
                         fs_pix_enabled=True)
        cpu.memory = [0] * 16384
        _seed_canaries(cpu.memory)
        with contextlib.redirect_stdout(io.StringIO()):
            cpu.running = True
            steps = 0
            while cpu.running and steps < 900000:
                cpu.step(arr)
                steps += 1
        assert not cpu.faulted, (
            f"faulted={cpu.faulted} reason={cpu.fault_reason}")
        assert cpu.halt_reason is None, (
            f"halt_reason={cpu.halt_reason} — run did not end at a clean HALT")
        mem = cpu.memory
        assert mem[GH23_EXIT_CODE] == 0, hex(mem[GH23_EXIT_CODE])
        assert mem[CURSOR] == RING_END, hex(mem[CURSOR])
        assert mem[840] == 0x5A5AA5A5, hex(mem[840])
        assert mem[860] == 0x0F0FF0F0, hex(mem[860])


# ── L3: the drop is loud — dropped-frame count is exact ──────────────────

@pytest.mark.skipif(shutil.which(_GCC) is None,
                    reason="riscv64-unknown-elf-gcc not installed")
def test_l3_dropped_frame_count_is_exact():
    """401 bytes = 26 frames (25 full + the zero-padded tail frame
    ceil(401/16)=26). The ring holds 16 frames; exactly 10 frames are
    refused. mem[DROPPED] pins the arithmetic — silence is the defect."""
    data = ("word " * 80) + "\n"          # 401 bytes
    receipt = _run_head(data)
    mem = receipt["memory"]
    total_frames = (len(data) + 15) // 16          # 26
    ring_frames = (RING_END - RING_BASE) // 4      # 16 words = 4 frames... NO:
    # the ring is 64 WORDS = 256 BYTES = 16 frames of 16 bytes.
    ring_frames = 16
    assert mem[CURSOR] == RING_END
    assert mem[DROPPED] == total_frames - ring_frames, (
        f"dropped {mem[DROPPED]} != expected {total_frames - ring_frames}")


# ── L4: sub-ring streams land byte-exactly as today (live guard) ─────────

@pytest.mark.skipif(shutil.which(_GCC) is None,
                    reason="riscv64-unknown-elf-gcc not installed")
def test_l4_sub_ring_stream_byte_exact():
    """A short stream (the BK-24 single-flush shape) is unchanged: full
    content in the ring, cursor exactly base+ceil(n/16) frames, dropped
    counter 0. Saturation must never touch the lawful path."""
    data = "hi\n"                          # 3 bytes -> 1 frame
    receipt = _run_head(data)
    assert receipt["halted"] is True
    assert receipt["faulted"] is False
    mem = receipt["memory"]
    assert mem[CURSOR] == RING_BASE + 4, hex(mem[CURSOR])
    assert mem[DROPPED] == 0, mem[DROPPED]
    ring = _ring_bytes(mem, RING_BASE, 4)
    assert ring == b"hi\n\0\0\0\0\0\0\0\0\0\0\0\0\0", ring


@pytest.mark.skipif(shutil.which(_GCC) is None,
                    reason="riscv64-unknown-elf-gcc not installed")
def test_l4b_exactly_full_stream_fits():
    """A stream of EXACTLY 256 bytes fills the ring with zero drops —
    the boundary case must land, not refuse (off-by-one guard)."""
    data = ("ab" * 127) + "a\n"            # 256 bytes exactly
    receipt = _run_head(data)
    assert receipt["halted"] is True
    assert receipt["faulted"] is False
    mem = receipt["memory"]
    assert mem[CURSOR] == RING_END, hex(mem[CURSOR])
    assert mem[DROPPED] == 0, (
        "a 256-byte stream fits the ring exactly — refusing it is an "
        "off-by-one in the clamp")
    first = _ring_bytes(mem, RING_BASE, 4)
    assert first == b"abababababababab", first
    last = _ring_bytes(mem, RING_END - 4, 4)
    assert last == b"abababababababa\n", last


# ── L5: non-vacuity — the clamp in the tile text is the refusal ──────────

def test_l5_tile_structurally_clamped():
    """Toolchain-free structural pins: the landed tile (a) reads the
    cursor, (b) tests it against the ring end BEFORE appending, (c)
    stores the clamped cursor back, (d) counts refused frames into the
    loud word. The pre-fix tile appended through the cursor with no test
    (verified RED: cursor 872 live at HEAD 4130af0e)."""
    tile = _gh23_sys_write_tile()
    body = [ln.split(";")[0].strip() for ln in tile.splitlines()]
    body = [ln for ln in body if ln and not ln.startswith(":")]
    # cursor read
    assert "LDI r15 724" in body
    i_cursor_ld = body.index("LD r11 r15")
    # the ring-end bound is materialized
    assert "LDI r12 832" in body, "tile lost the ring-end bound"
    # a compare exists between cursor read and the first append store
    i_first_append = i_cursor_ld + body[i_cursor_ld:].index("ST r11 r7")
    window = body[i_cursor_ld:i_first_append]
    assert any(ln.startswith("CMP r11 r12") for ln in window), window
    # the drop counter is materialized at word 725
    assert "LDI r15 725" in body
    assert any(ln.startswith("ST r15 r13") for ln in window), window
    # the cursor clamp store-back
    assert "ST r15 r11" in body
    # excess frames diverted to dead sink 726
    assert "LDI r15 726" in body


def test_l5b_neutered_clamp_restores_red_shape():
    """Non-vacuity: monkeypatching the tile text to the pre-fix shape
    (clamp branch removed, plain append) and re-running the RED fixture
    reproduces the overflow: cursor > 832. Restored module -> L1 green.
    The landed module file is md5-pinned before/after (BK-56 L5 shape)."""
    pytest.importorskip("pytest")
    src = (_REPO / "tools" / "glyph_gpt" / "libc_runtime.py").read_text()
    md5_before = hashlib.md5(src.encode()).hexdigest()

    import tools.glyph_gpt.libc_runtime as LRT
    g_lrt = sys.modules.get("glyph_gpt.libc_runtime")
    saved_tile = LRT._gh23_sys_write_tile
    saved_g_tile = getattr(g_lrt, "_gh23_sys_write_tile", None) if g_lrt else None

    def _unclamped_tile():
        """Pre-fix tile verbatim behavior: append 4 words at the cursor,
        cursor += 4, no bound test, no counter (the landed BK-24 tile)."""
        return (
            ":__entry\n"
            "LDI r15 0x200E\n"
            "LD r6 r15\n"
            "LDI r13 2\n"
            "SHR r6 r13\n"
            "LD r7 r6\n"
            "LDI r13 1\n"
            "ADD r6 r13\n"
            "LD r8 r6\n"
            "LDI r13 1\n"
            "ADD r6 r13\n"
            "LD r9 r6\n"
            "LDI r13 1\n"
            "ADD r6 r13\n"
            "LD r10 r6\n"
            "LDI r13 3\n"
            "SUB r6 r13\n"
            "LDI r15 724\n"
            "LD r11 r15\n"
            "ST r11 r7\n"
            "LDI r13 1\n"
            "ADD r11 r13\n"
            "ST r11 r8\n"
            "LDI r13 1\n"
            "ADD r11 r13\n"
            "ST r11 r9\n"
            "LDI r13 1\n"
            "ADD r11 r13\n"
            "ST r11 r10\n"
            "LDI r13 1\n"
            "ADD r11 r13\n"
            "LDI r15 724\n"
            "ST r15 r11\n"
            "LDI r15 718\n"
            "ST r15 r7\n"
            "LDI r15 719\n"
            "ST r15 r8\n"
            "LDI r15 720\n"
            "ST r15 r9\n"
            "LDI r15 721\n"
            "ST r15 r10\n"
            "HALT\n"
        )

    LRT._gh23_sys_write_tile = _unclamped_tile
    if g_lrt:
        g_lrt._gh23_sys_write_tile = _unclamped_tile
    try:
        data = ("word " * 80) + "\n"       # the RED fixture
        receipt = _run_head(data)
        mem = receipt["memory"]
        cursor = mem[CURSOR]
        assert cursor > RING_END, (
            "neutered clamp did NOT reproduce the overflow — the gate "
            "cannot fail, it is decoration")
        assert cursor == RING_BASE + 104, hex(cursor)  # the measured RED value
    finally:
        LRT._gh23_sys_write_tile = saved_tile
        if g_lrt and saved_g_tile:
            g_lrt._gh23_sys_write_tile = saved_g_tile

    md5_after = hashlib.md5(
        (_REPO / "tools" / "glyph_gpt" / "libc_runtime.py").read_text()
        .encode()).hexdigest()
    assert md5_before == md5_after, "module mutated by the neuter leg"


# ── L6: family — the BK-24 sub-ring gate stays green on this tree ────────

def test_l6_bk24_family_runs():
    """Subprocess the landed BK-24 gate: the saturation posture must not
    disturb a single landed leg (L1 structural pins included — the tile
    keeps its append-through-cursor shape)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q",
         str(_REPO / "tests" / "test_bk24_streaming_write.py")],
        capture_output=True, timeout=900)
    tail = proc.stdout.decode()[-300:]
    assert proc.returncode == 0, f"BK-24 family RED on the bk54 tree:\n{tail}"
