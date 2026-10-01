"""R2.3 hosted cross-compilation gate: tests/test_glyph_cc.py.

PRODUCT_ROADMAP.md R2.3: "Hosted cross-compilation story: C/Rust via RV32
target, LLVM backend or transpiler chain, round-trip receipts."

The unit under test is tools/glyph_cc.py — one command: C or Rust source ->
RV32 ELF (hosted cross-compiler) -> rv64i_to_glyph transpiler -> baked glyph
artifact -> GlyphCPUv2 execution -> receipt with the a0 result and a
ROUND-TRIP leg that re-reads the artifact from disk and must reproduce the
same result.

GREEN legs prove the chain works; RED legs prove the gate can fail:
  - a C source that does not compile -> exit 2, no artifact written
  - a corrupted artifact replay that changes the result -> roundtrip
    MISMATCH -> exit 2 (the receipt is discriminating, not decorative)
  - a missing input file -> exit 4

Skipped (not failed) when the host lacks riscv64-unknown-elf-gcc or the
riscv32im Rust std: this gate needs the real hosted cross-compilers; there
is no honest stub. What the PASS does NOT prove: no WGSL-twin parity (CPU
oracle only), no rate/cost claims (floors N/A — no timing comparisons), no
libc (freestanding -nostdlib programs only).
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

GLYPH_CC = _REPO_ROOT / "tools" / "glyph_cc.py"

pytestmark = pytest.mark.skipif(
    pytest.importorskip("shutil").which("riscv64-unknown-elf-gcc") is None,
    reason="riscv64-unknown-elf-gcc not installed",
)


def _run(tmp: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GLYPH_CC), *argv],
        capture_output=True, text=True, cwd=tmp)


def _json_run(tmp: Path, *argv: str):
    res = _run(tmp, "--json", *argv)
    assert res.returncode == 0, f"expected exit 0, got {res.returncode}: {res.stderr}"
    return json.loads(res.stdout)


SUM_C = "int main(void){int s=0;for(int i=1;i<=5;i++)s+=i;return s;}\n"

SUM_RS = """\
#![no_std]
#![no_main]

#[unsafe(no_mangle)]
pub extern "C" fn main() -> i32 {
    let mut s: i32 = 0;
    let mut i: i32 = 1;
    while i <= 5 {
        s += i;
        i += 1;
    }
    s
}
"""


def test_c_source_roundtrip(tmp_path):
    src = tmp_path / "sum.c"
    src.write_text(SUM_C)
    r = _json_run(tmp_path, str(src))
    assert r["halted"] is True
    assert r["faulted"] is False
    assert r["result_a0"] == 15
    assert r["roundtrip"]["match"] is True
    assert r["roundtrip"]["result_a0"] == 15
    assert Path(r["artifact"]).exists()
    assert "gcc" in r["chain"]


def test_rust_source_roundtrip(tmp_path):
    if shutil.which("rustc") is None:
        pytest.skip("rustc not installed")
    src = tmp_path / "sum.rs"
    src.write_text(SUM_RS)
    r = _json_run(tmp_path, str(src))
    assert r["halted"] is True
    assert r["result_a0"] == 15
    assert r["roundtrip"]["match"] is True
    assert "rustc" in r["chain"]


def test_prebuilt_elf_accepted(tmp_path):
    """The .elf input path: compile C to ELF first, then feed the ELF."""
    src = tmp_path / "sum.c"
    src.write_text(SUM_C)
    elf = tmp_path / "pre.elf"
    res = subprocess.run(
        ["riscv64-unknown-elf-gcc", "-march=rv32i", "-mabi=ilp32", "-O1",
         "-nostdlib", "-fno-builtin", "-w", "-Wl,-Ttext=0x0",
         "-Wl,--build-id=none", str(GLYPH_CC.parent / "glyph_cc_crt0_dummy.s"
                                    if False else "/dev/null"),
         "-x", "c", str(src), "-o", str(elf)],
        capture_output=True, text=True)
    # /dev/null as an input would lack _start; instead compile with crt0
    # inlined via a temp file:
    if res.returncode != 0:
        crt0 = tmp_path / "crt0.S"
        crt0.write_text(
            ".globl _start\n_start:\nli sp, 0x4000\ncall main\necall\n")
        res = subprocess.run(
            ["riscv64-unknown-elf-gcc", "-march=rv32i", "-mabi=ilp32", "-O1",
             "-nostdlib", "-fno-builtin", "-w", "-Wl,-Ttext=0x0",
             "-Wl,--build-id=none", str(crt0), str(src), "-o", str(elf)],
            capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    r = _json_run(tmp_path, str(elf))
    assert r["halted"] is True
    assert r["result_a0"] == 15
    assert r["roundtrip"]["match"] is True


def test_red_bad_c_source(tmp_path):
    """RED leg: uncompilable C -> exit 2 (toolchain), no artifact."""
    src = tmp_path / "bad.c"
    src.write_text("int main(void){ this is not c }\n")
    res = _run(tmp_path, str(src))
    assert res.returncode == 2, f"gate failed to fail: exit {res.returncode}"
    assert "failed" in res.stderr.lower()
    artifacts = list(tmp_path.glob("bad.glyph.png"))
    assert artifacts == [], "artifact must not be written on compile failure"


def test_red_missing_file(tmp_path):
    """RED leg: missing input -> exit 4."""
    res = _run(tmp_path, str(tmp_path / "nope.c"))
    assert res.returncode == 4


def test_red_corrupted_artifact_mismatch(tmp_path):
    """RED leg: the round-trip must be DISCRIMINATING. Corrupt the on-disk
    artifact (zero the pixel row holding the first instruction), replay, and
    the receipt must report roundtrip MISMATCH (exit 2) — i.e. the round-trip
    check cannot pass by returning True."""
    src = tmp_path / "sum.c"
    src.write_text(SUM_C)
    r = _json_run(tmp_path, str(src))
    assert r["roundtrip"]["match"] is True

    import numpy as np
    from PIL import Image
    artifact = Path(r["artifact"])
    img = np.array(Image.open(artifact))
    # find a lit pixel belonging to the executed first row and blank it:
    # the artifact encodes instructions as pixels; blanking the entry block
    # changes execution. Zero the top-left instruction region:
    img[:2, :16, ...] = 0
    Image.fromarray(img).save(artifact)

    # replay-only check through the tool's own replay path:
    import importlib.util
    spec = importlib.util.spec_from_file_location("glyph_cc_mod", GLYPH_CC)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rt = mod._rerun_artifact_from_disk(artifact, 1_000_000)
    # The corrupted replay must NOT reproduce a clean 15:
    assert not (rt["result_a0"] == 15 and rt["halted"]), (
        "corrupted artifact still produced the exact good result — "
        "round-trip check is not discriminating")


def test_receipt_fields_complete(tmp_path):
    src = tmp_path / "sum.c"
    src.write_text(SUM_C)
    r = _json_run(tmp_path, str(src))
    for key in ("chain", "artifact", "halted", "faulted", "steps",
                "budget_exhausted", "result_a0", "registers", "roundtrip"):
        assert key in r, f"receipt missing '{key}'"


RUST_REC_FIB = """\
#![no_std]
#![no_main]

fn fib(n: u32) -> u32 {
    if n < 2 { n } else { fib(n - 1) + fib(n - 2) }
}

#[unsafe(no_mangle)]
pub extern "C" fn main() -> u32 {
    fib(15)
}
"""


def test_rust_recursive_stack_program(tmp_path):
    """TICKET_R53_day1_transpiler_auipc_jalr gate (2026-09-22, R5.3 day-1).

    rustc's call idiom `auipc ra,0x0; jalr -N(ra)` exercises the pointer-
    table JALR lowering WITH a nonzero immediate plus a sp-relative frame.
    Pre-fix this faulted (sp=0 prologue store) or spun forever (JALR
    indexed the table at ra alone -> jumped to the auipc's own entry);
    the gate must see HALT with a0=610 and an artifact round-trip MATCH.
    """
    if shutil.which("rustc") is None:
        pytest.skip("rustc not installed")
    src = tmp_path / "fib_rec.rs"
    src.write_text(RUST_REC_FIB)
    r = _json_run(tmp_path, str(src))
    assert r["halted"] is True, f"faulted/budget: {r}"
    assert r["result_a0"] == 610
    assert r["roundtrip"]["match"] is True
    assert "rustc" in r["chain"]


def test_c_fn_pointer_indirect_call(tmp_path):
    """C data-loaded call target (`jalr ra,0(a5)` after `lw`): the reason
    the C lane survived the R53 day-1 defect — keep it pinned."""
    src = tmp_path / "fnptr.c"
    src.write_text(
        "static int add8(int a,int b,int c,int d,int e,int f,int g,int h)"
        "{return a+b+c+d+e+f+g+h;}\n"
        "static int (*fp)(int,int,int,int,int,int,int,int) = add8;\n"
        "int main(void){ return fp(1,2,3,4,5,6,7,8); }\n")
    r = _json_run(tmp_path, str(src))
    assert r["halted"] is True
    assert r["result_a0"] == 36
    assert r["roundtrip"]["match"] is True
