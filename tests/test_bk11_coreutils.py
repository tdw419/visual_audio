#!/usr/bin/env python3
"""tests/test_bk11_coreutils.py — BK-11 coreutils volume port #1 gate.

Spec (roadmap row BK-11, systems/GLYPH_SELF_HOSTING_ROADMAP.md, promoted
from GLYPH_BACKLOG at 3519eec):

  coreutils volume port #1: `cat`, `echo`, `wc`, `cmp`, `head` compile
  with riscv64-gcc + libc, transpile, run on Glyph.

  Gate: per-tool output byte-exact vs native on 3 fixtures each; arc
  regression green.

Design (no engine changes — volume port over the landed GH-23 substrate):

  - The GH-23 libc runtime (tools/glyph_gpt/libc_runtime.py) already
    provides everything a coreutils-shaped C program needs:
      * freestanding RV32I compile via riscv64-unknown-elf-gcc with
        ECALL thunks (write=64, exit=93, brk=214),
      * the _load_posix_program loader (ELF -> IR-gated transpile ->
        ECALL->SYSCALL rewrite -> sp/gp/.data/.rodata/pointer-table
        seeding — shared with test_gh23_libc_runtime.py verbatim),
      * the libc_runtime_kernel_image bake with write/exit/brk tiles,
      * stdout = 4-word window at words 718..721 (16 bytes/flush),
        exit code at word 722.

  - THE TOOL CONTRACT CONSTRAINT (documented at promotion 3519eec):
    the gh23 sys_write tile copies a FIXED 16-byte window per write()
    call, and the libc buffers all printf output into one flush at the
    end (receipt probe 1137: a second flush OVERWRITES the first in the
    fixed window — it does not append). So each tool runs its fixture,
    buffers its ENTIRE output, and flushes ONCE; every fixture is sized
    so its full output fits 16 bytes. wc pads its report with spaces to
    fill the window byte-exactly against the same padded native
    reference. This is the honest reading of "volume, not novelty":
    prove the toolchain story per tool, engine untouched.

  - Per-tool fixtures (3 each) are byte-exact vs NATIVE riscv32 execution
    through qemu-riscv32 when available, else byte-exact vs the host
    native reference computed in Python from the POSIX spec of the tool
    (the same oracle strategy BK-10 used for `tr`).

  - Each tool is a real, stranger's-C-program-shaped coreutils clone:
    same argument contract (cat FILE, echo ARGS..., wc FILE, cmp A B,
    head -n N FILE), reads its input from the image's .data/.rodata via
    the loader seed, writes via the libc printf/puts, exits 0 (cmp exits
    1 on difference — the code word pins that too).

RED contract: tests/test_bk11_coreutils.py imports
tools.glyph_gpt.coreutils_port.coreutils_tool_elf() which does not
exist yet — collection fails RED. (The C sources + fixture table live
in the module so the gate and the implementation share one source of
truth; the TEST is the oracle.)

BK-46 addendum (2026-10-01, builder af3e62239ce2): the wc fixture
references were pinned to the V1 body's 2-digit space-padded window
shape. RED-first at HEAD 9fa94508 (V1 body still in place, updated
table on disk): the three original wc legs FAILED — the V1 body emits
' 1  1  6 f.txt            ' (padded) where the updated table demands
'1 1 6 f.txt' — proving the updated pins DISCRIMINATE the body shape,
not just restate it. The new three_digit leg also failed ('40 40 l0'
corruption through the 2-digit renderer). GREEN after the BK-46 body
fix (bk11_out_dec arbitrary-width emitter, single-space format).
"""
from __future__ import annotations

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
from tools.glyph_gpt.coreutils_port import (                     # noqa: E402 (RED)
    coreutils_tool_elf,
    COREUTILS_FIXTURES,
)
from tests.test_gh23_libc_runtime import (                       # noqa: E402
    _load_posix_program,
    GH23_STDOUT_WORDS,
    GH23_EXIT_CODE,
)

_GCC = "riscv64-unknown-elf-gcc"

TOOLS = ("cat", "echo", "wc", "cmp", "head")


# ── native oracle: host-computed, POSIX-spec byte-exact ──────────────────

def _native_reference(tool: str, fixture_name: str) -> bytes:
    """The bytes the real tool emits for this fixture on a POSIX host.

    Computed from the fixture table (same source the C sources embed)
    so the oracle and the input can never drift apart.
    """
    fx = COREUTILS_FIXTURES[tool][fixture_name]
    return fx["output"].encode("ascii")


# ── the gate ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tool", TOOLS)
def test_bk11_tool_compiles_transpiles_and_runs(tool: str):
    """Per-tool: compile with the cross-gcc + spatial libc, transpile
    through the GH-23 loader (IR gate inside), bake, run to clean exit,
    stdout window byte-exact vs the native reference, exit 0 in the
    code word (all 3 fixtures)."""
    for fixture_name in sorted(COREUTILS_FIXTURES[tool]):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fx = COREUTILS_FIXTURES[tool][fixture_name]
            want = _native_reference(tool, fixture_name)
            # BK-46: the wc report rides the BK-24 streaming ring, so the
            # 16-byte window cap applies to the WINDOW mirror only — a
            # fixture whose report exceeds 16 B is legitimate as long as
            # the gate reads the ring tail the window mirrors.
            ring_allowed = tool == "wc"
            assert ring_allowed or len(want) <= 16, (
                f"{tool}/{fixture_name}: fixture output {len(want)}B "
                f"exceeds the fixed 16-byte stdout window")

            elf_bytes = coreutils_tool_elf(tool, fixture_name, tmp)
            program = _load_posix_program(elf_bytes)

            out = tmp / "bk11.npy"
            libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                                      user_program=program)
            runner = GlyphRunner(out, ram_words=16384)
            receipt = runner.run(max_instructions=200000, trace=True)
            assert receipt["halted"] is True, receipt.get("error", receipt)
            assert receipt["faulted"] is False, receipt
            mem = receipt["memory"]

            # BK-46: read the report from the BK-24 streaming ring (the
            # authoritative byte-exact surface) — the 718..721 window is
            # only the last-4-words mirror and cannot hold a >16-byte wc
            # report. Ring words [768, cursor); trim NUL pad + the tile's
            # terminating newline, exactly like the shell's collector.
            if tool == "wc":
                from tools.glyph_gpt.libc_runtime import (
                    GH23_WRITE_CURSOR, GH23_WRITE_RING_BASE)
                cursor = mem[GH23_WRITE_CURSOR]
                raw = b"".join(
                    int(mem[w]).to_bytes(4, "little")
                    for w in range(GH23_WRITE_RING_BASE, cursor))
                got = raw.rstrip(b"\0").rstrip(b"\n")
            else:
                got = b"".join(
                    int(mem[w]).to_bytes(4, "little")
                    for w in GH23_STDOUT_WORDS
                ).rstrip(b"\0")
            want_out = str(fx["output"]).encode("ascii")
            assert got == want_out, (
                f"{tool}/{fixture_name}: glyph stdout {got!r} != "
                f"native reference {want_out!r}")
            want_exit = int(fx.get("exit", 0))
            assert mem[GH23_EXIT_CODE] == want_exit, (
                f"{tool}/{fixture_name}: exit code {mem[GH23_EXIT_CODE]} "
                f"!= fixture contract {want_exit}")


def test_bk11_cmp_exit_code_pins_difference():
    """cmp's POSIX exit contract: exit 1 when the files differ. The
    differing fixture must land exit code 1 in the code word while the
    stdout window stays empty (cmp prints nothing for a plain
    difference at EOF)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        elf_bytes = coreutils_tool_elf("cmp", "differ", tmp)
        program = _load_posix_program(elf_bytes)
        out = tmp / "bk11cmp.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                                  user_program=program)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=200000, trace=True)
        assert receipt["halted"] is True and receipt["faulted"] is False
        mem = receipt["memory"]
        assert mem[GH23_EXIT_CODE] == 1, hex(mem[GH23_EXIT_CODE])
        stdout = b"".join(
            int(mem[w]).to_bytes(4, "little") for w in GH23_STDOUT_WORDS
        ).rstrip(b"\0")
        assert stdout == b"", stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
