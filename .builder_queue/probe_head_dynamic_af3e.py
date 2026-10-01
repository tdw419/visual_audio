#!/usr/bin/env python3
"""Research probe (af3e, 2026-09-27): root-cause BK-46 finding (4) —
"head in the dynamic path emits NOTHING (empty ring)". Legs:
  A) the REAL dynamic path: shell._shell_native("head", ...) on two
     fixtures (small, big) — verdict from the returned STRING;
  B) compile-chain with stderr surfaced: build the exact dynamic head
     TU (seeds/derived/aliases as glyph_l1_shell.py:952-974 builds
     them, NO _COMMON) and report gcc/ld stderr verbatim;
  C) GREEN-leg control: same TU WITH _COMMON prepended — compiles,
     runs on-glyph, ring collected (does head work at all?).
Verdicts from returned strings + compiler stderr + ring bytes, never
handler stdout. /tmp scratch + engine modules landed at HEAD only."""
import sys, tempfile, subprocess, hashlib, json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "experiments"))

results = {}

# ── Leg A: the real dynamic path ────────────────────────────────────
from glyph_l1_shell import GlyphL1Shell, L1Session  # noqa: E402

with tempfile.TemporaryDirectory(prefix="b9h_") as td:
    td = Path(td)
    session = L1Session(root=td)
    shell = GlyphL1Shell(session=session)
    a = td / "lines.txt"
    a.write_bytes(b"alpha\nbeta\ngamma\ndelta\n")
    b = td / "big.txt"
    b.write_bytes(b"".join(b"line %d\n" % i for i in range(60)))  # 480 B
    for tag, f in (("small", a), ("big", b)):
        try:
            results[f"dyn_head_{tag}"] = shell._shell_native("head", f.name)
        except Exception as exc:  # noqa: BLE001
            results[f"dyn_head_{tag}"] = f"EXC:{type(exc).__name__}:{exc}"
    # host shim reference
    try:
        results["host_head_small"] = shell._head("1 " + a.name)
    except Exception as exc:  # noqa: BLE001
        results["host_head_small"] = f"EXC:{type(exc).__name__}:{exc}"

# ── Leg B: the exact dynamic TU, stderr surfaced ────────────────────
from tools.glyph_gpt.coreutils_port import (  # noqa: E402
    _TOOL_SOURCES, _COMMON, _c_literal)
from tests.test_gh23_libc_runtime import (  # noqa: E402
    _load_posix_program, LIBC_C, SHIM_S)
from tools.glyph_gpt.baker import libc_runtime_kernel_image  # noqa: E402
from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402
from tools.glyph_gpt.libc_runtime import (  # noqa: E402
    GH23_WRITE_CURSOR, GH23_WRITE_RING_BASE)

data = "alpha\nbeta\ngamma\ndelta\n"
# mirror glyph_l1_shell.py:952-974 exactly (head branch)
seeds = [f'static const char *head_data = "{_c_literal(data)}";']
derived = ["static long HEAD_N = 1;"]
aliases = ["#define HEAD_DATA head_data"]


def build_and_run(prepend_common: bool):
    parts = ([_COMMON] if prepend_common else []) + [
        "\n".join(seeds), "\n".join(derived),
        "\n".join(aliases), _TOOL_SOURCES["head"]]
    src_text = "\n".join(p + "\n" for p in parts)
    with tempfile.TemporaryDirectory(prefix="b9h2_") as t2:
        tmp = Path(t2)
        src = tmp / "tool.c"
        src.write_text(src_text)
        libc = tmp / "gh23_libc.c"
        libc.write_text(LIBC_C)
        shim = tmp / "shim.S"
        shim.write_text(SHIM_S)
        gcc = "riscv64-unknown-elf-gcc"
        errs = []
        objs = []
        for i, cf in enumerate((src, libc)):
            obj = tmp / f"tool_{i}.o"
            proc = subprocess.run(
                [gcc, "-march=rv32i", "-mabi=ilp32", "-O1",
                 "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
                 "-ffixed-x31", "-nostdlib", "-fno-builtin",
                 "-ffreestanding", "-w", "-c", str(cf),
                 "-o", str(obj)], capture_output=True, timeout=60)
            errs.append(f"cc{i}.rc={proc.returncode}")
            if proc.returncode != 0:
                errs.append(proc.stderr.decode()[:400])
                return "; ".join(errs), None
            objs.append(obj)
        elf = tmp / "tool.elf"
        proc = subprocess.run(
            [gcc, "-march=rv32i", "-mabi=ilp32",
             "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
             "-ffixed-x31", "-nostdlib", "-Wl,-Ttext=0x0",
             "-Wl,-N", "-Wl,--entry=_start", "-w",
             *map(str, objs), str(shim), "-o", str(elf)],
            capture_output=True, timeout=60)
        errs.append(f"ld.rc={proc.returncode}")
        if proc.returncode != 0:
            errs.append(proc.stderr.decode()[:400])
            return "; ".join(errs), None
        program = _load_posix_program(elf.read_bytes())
        image = tmp / "head.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=image,
                                  user_program=program)
        runner = GlyphRunner(image, ram_words=16384)
        receipt = runner.run(max_instructions=300000, trace=True)
        errs.append(f"halted={receipt.get('halted')} "
                    f"faulted={receipt.get('faulted')}")
        mem = receipt.get("memory", [])
        cursor = mem[GH23_WRITE_CURSOR] if mem else 0
        errs.append(f"cursor={cursor} ring_base={GH23_WRITE_RING_BASE}")
        raw = b"".join(int(mem[w]).to_bytes(4, "little")
                       for w in range(GH23_WRITE_RING_BASE, max(cursor, GH23_WRITE_RING_BASE)))
        return "; ".join(errs), raw.rstrip(b"\x00").decode(
            "ascii", errors="replace").rstrip("\n")


info_b, out_b = build_and_run(prepend_common=False)
results["legB_no_common_info"] = info_b
results["legB_no_common_out"] = out_b

info_c, out_c = build_and_run(prepend_common=True)
results["legC_common_info"] = info_c
results["legC_common_out"] = out_c

blob = json.dumps(results, indent=1, sort_keys=True)
print(blob)
print(f"results_md5={hashlib.md5(blob.encode()).hexdigest()}")
