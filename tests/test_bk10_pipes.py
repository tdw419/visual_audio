#!/usr/bin/env python3
"""tests/test_bk10_pipes.py — BK-10 gate (RED until SYS 16/17 pipe FS exists).

Roadmap BK-10 (promoted from GLYPH_BACKLOG, commit b379c7a): "stdio beyond
uart: stdin/stdout as FS files (slot aliasing) so shell pipes reduce to file
copy; prog1 | prog2 runs two boxes joined via FS".

Gate legs (the spec's oracle clauses, mapped):
  L1 (pipe end-to-end):  prog1 = task A ("echo") stages the packed word
      'hi' (0x6968) into the shared scratch window and SWIs 16 (pipe write:
      FS create 'PIPE' with a 1-word payload). The kernel dispatches task B
      ("toupper"), which SWIs 17 (pipe read: FS 'PIPE' -> read-out window),
      applies the ASCII lowercase->uppercase mapping IN THE TASK (XOR
      0x2020 — the kernel copy stays byte-pure), and writes the result to
      the stdout alias word. Output must be BYTE-EXACT vs a native shell
      pipe: subprocess `printf 'hi' | tr a-z A-Z` -> b"HI".
  L2 (FS handoff residency): the handoff is genuinely THROUGH THE FS, not
      a register or mailbox shortcut — the FSTAB slot claims 'PIPE'
      (name/start/len/in_use = 1044/2/1), the raw payload word sits in the
      pixel-backed data region, and the read-out window holds the RAW
      lowercase word (the case flip happened in prog2, after the copy).

ABI (extends the GH-8 FS family, same dispatch shape):
  SYS 16 = pipe write:  a0 = file name u32, a1 = byte count (<=4; the
    mailbox word IS the transfer granularity). Payload = scratch[736].
    Claims FSTAB slot 0, sets start = data region, len = a1, in_use = 1,
    copies exactly ONE word scratch -> data.
  SYS 17 = pipe read:   a0 = file name u32, a1 = max bytes. Scans slot 0
    for (name match AND in_use); hit: copies ONE word data -> read-out
    window (752), returns len; miss: 'E' in read-out, returns 0.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.baker import (                                 # noqa: E402
    pipe_kernel_image,
    BK10_FSTAB_WORD, BK10_DATA_WORD, BK10_SCRATCH_WORD,
    BK10_READOUT_WORD, BK10_STDOUT_WORD, BK10_EXIT_A, BK10_EXIT_B,
    BK10_NAME_PIPE, BK10_PAYLOAD_HI,
)
from tools.glyph_gpt.runner import GlyphRunner                     # noqa: E402

KERNEL_OK = 0xCAFE0010
EXIT_OK_A = 0xFEED0010
EXIT_OK_B = 0xFEED0011


def _pack(data: bytes) -> int:
    """Pack a short byte string little-endian (byte i = char i), the same
    packing every GH-10/BK-10 word uses."""
    b = bytes(data[:4]).ljust(4, b"\x00")
    return int.from_bytes(b, "little")


def _bake(tmp: Path, name: str = "bk10.glyph.npy") -> Path:
    out = tmp / name
    pipe_kernel_image(None, min_rows=80, out_path=out)
    return out


def _run(tmp: Path, **kw):
    out = _bake(tmp, **kw)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=80000)
    return runner, receipt


def _pw(img: np.ndarray, word: int) -> int:
    """Read a pix-word from the FS window: 2 px per 32-bit word."""
    h, w, _ = img.shape
    lin = word * 2
    lo = ((int(img[lin // w, lin % w][0]) << 16)
          | (int(img[lin // w, lin % w][1]) << 8)
          | int(img[lin // w, lin % w][2]))
    lin2 = word * 2 + 1
    hi = int(img[lin2 // w, lin2 % w][2])
    return (lo | (hi << 24)) & 0xFFFFFFFF


def test_bk10_pipe_echo_toupper_byte_exact_vs_native():
    """L1: 'echo hi | toupper' via two mailbox tasks joined by the FS.
    The stdout word must be byte-exact against a REAL native pipe."""
    native = subprocess.run("printf 'hi' | tr a-z A-Z", shell=True,
                            capture_output=True, check=True)
    expected = _pack(native.stdout)
    assert native.stdout == b"HI", native.stdout  # oracle sanity
    with tempfile.TemporaryDirectory() as d:
        runner, receipt = _run(Path(d), name="bk10_pipe.npy")
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # both mailbox tasks ran to their exits
        assert mem[BK10_EXIT_A] == EXIT_OK_A, (
            f"prog1 exit 0x{mem[BK10_EXIT_A]:08x} != 0xFEED0010")
        assert mem[BK10_EXIT_B] == EXIT_OK_B, (
            f"prog2 exit 0x{mem[BK10_EXIT_B]:08x} != 0xFEED0011")
        # stdout alias word: byte-exact vs the native pipe
        assert mem[BK10_STDOUT_WORD] == expected, (
            f"stdout 0x{mem[BK10_STDOUT_WORD]:08x} != native pipe "
            f"0x{expected:08x} ({native.stdout!r})")
        assert receipt["status_word_value"] == KERNEL_OK, receipt


def test_bk10_pipe_handoff_is_fs_copy_not_register_shortcut():
    """L2: the pipe genuinely flows THROUGH the FS: FSTAB slot claims
    'PIPE' (start = data region, len = 2, in_use), the raw lowercase word
    sits in the pixel-backed data region, and the read-out window holds
    the RAW lowercase word — prog2 (not the kernel) did the case flip."""
    with tempfile.TemporaryDirectory() as d:
        runner, receipt = _run(Path(d), name="bk10_fsres.npy")
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        img = np.asarray(runner.image)
        # FSTAB slot 0: name 'PIPE', start = data region, len = 2, in_use
        assert _pw(img, BK10_FSTAB_WORD) == BK10_NAME_PIPE
        assert _pw(img, BK10_FSTAB_WORD + 1) == BK10_DATA_WORD
        assert _pw(img, BK10_FSTAB_WORD + 2) == 2
        assert _pw(img, BK10_FSTAB_WORD + 3) == 1
        # the payload lives in the pixel data region ('the screen is the
        # hard drive'): raw 'hi', untouched by the uppercase pass
        assert _pw(img, BK10_DATA_WORD) == BK10_PAYLOAD_HI
        # read-out window: the kernel's copy is BYTE-PURE (still lowercase)
        assert mem[BK10_READOUT_WORD] == BK10_PAYLOAD_HI
        # the case mapping happened in prog2 after the FS copy
        assert mem[BK10_STDOUT_WORD] == _pack(b"HI")
        assert receipt["status_word_value"] == KERNEL_OK, receipt


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
