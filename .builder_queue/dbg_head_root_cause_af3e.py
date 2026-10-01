#!/usr/bin/env python3
"""Research probe (af3e, 2026-09-27): ROOT-CAUSE the 'head emits NOTHING'
leg from RESEARCH_wc_swap_refusal_af3e.md (4). Hypothesis: dbg3's alias
shape (#define HEAD_N head_n with NO head_n seed) makes the body read an
unseeded BSS 0; bk11_flush() then delivers a 16-NUL pad frame and the
collect-side .rstrip(b"\\x00") renders the ring LOOK empty.

Legs (raw cursor + ring words dumped BEFORE any strip):
  A: dbg3 shape verbatim        -> predict cursor=772, ring words all 0
  B: fixture-builder shape      -> predict real bytes ("word word word w")
     (seed static long head_n=1; alias HEAD_N->head_n; coreutils_port :350)
  C: _shell_native fix shape    -> predict real bytes (derived HEAD_N=1,
     NO alias; glyph_l1_shell :972-974)
  D: leg-B harness on a short file (one line <16B) -> byte-exact single
     frame vs host head reference.
Verdicts from raw word values, never handler stdout."""
import sys, tempfile, subprocess, hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "experiments"))

from tools.glyph_gpt.coreutils_port import _TOOL_SOURCES, _COMMON  # noqa: E402
from tests.test_gh23_libc_runtime import (  # noqa: E402
    _load_posix_program, LIBC_C, SHIM_S)
from tools.glyph_gpt.baker import libc_runtime_kernel_image  # noqa: E402
from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402
from tools.glyph_gpt.libc_runtime import (  # noqa: E402
    GH23_WRITE_CURSOR, GH23_WRITE_RING_BASE)


def run_raw(seeds, derived, aliases, max_instructions=300000):
    """Compile+transpile+bake+run; return (halted, faulted, cursor, ring_words)."""
    body = _TOOL_SOURCES["head"]
    src_text = (_COMMON + "\n" + "\n".join(seeds) + "\n"
                + "\n".join(derived) + "\n" + "\n".join(aliases) + "\n" + body)
    with tempfile.TemporaryDirectory(prefix="b9h_") as td:
        tmp = Path(td)
        (tmp / "tool.c").write_text(src_text)
        (tmp / "gh23_libc.c").write_text(LIBC_C)
        (tmp / "shim.S").write_text(SHIM_S)
        gcc = "riscv64-unknown-elf-gcc"
        objs = []
        for i, cfile in enumerate(("tool.c", "gh23_libc.c")):
            obj = tmp / f"tool_{i}.o"
            proc = subprocess.run(
                [gcc, "-march=rv32i", "-mabi=ilp32", "-O1",
                 "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
                 "-ffixed-x31", "-nostdlib", "-fno-builtin",
                 "-ffreestanding", "-w", "-c", str(tmp / cfile),
                 "-o", str(obj)], capture_output=True, timeout=60)
            if proc.returncode != 0:
                return ("COMPILE_FAIL", proc.stderr.decode()[:200], None, ())
            objs.append(obj)
        elf = tmp / "tool.elf"
        proc = subprocess.run(
            [gcc, "-march=rv32i", "-mabi=ilp32",
             "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
             "-ffixed-x31", "-nostdlib", "-Wl,-Ttext=0x0",
             "-Wl,-N", "-Wl,--entry=_start", "-w",
             *map(str, objs), str(tmp / "shim.S"), "-o", str(elf)],
            capture_output=True, timeout=60)
        if proc.returncode != 0:
            return ("LINK_FAIL", proc.stderr.decode()[:200], None, ())
        program = _load_posix_program(elf.read_bytes())
        image = tmp / "shell_native.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=image,
                                  user_program=program)
        runner = GlyphRunner(image, ram_words=16384)
        receipt = runner.run(max_instructions=max_instructions, trace=True)
        if not receipt.get("halted") or receipt.get("faulted"):
            return ("RUN_FAIL",
                    f"halted={receipt.get('halted')} faulted={receipt.get('faulted')}",
                    None, ())
        mem = receipt["memory"]
        cursor = mem[GH23_WRITE_CURSOR]
        ring = tuple(int(mem[w]) for w in range(
            GH23_WRITE_RING_BASE, min(cursor, GH23_WRITE_RING_BASE + 16)))
        return ("OK", "", cursor, ring)


def lit(s):
    return s.replace("\\", "\\\\").replace('"', '\\"') \
            .replace("\n", "\\n").replace("\t", "\\t")


results = {}

data_big = ("word " * 80) + "\n"          # 401 bytes, ONE line
data_small = "hi\n"                        # 3 bytes, one line < 16B

# Leg A — dbg3 shape verbatim (HEAD_N seeded pre-#define; head_n unseeded)
rA = run_raw(
    [f'static const char *head_data = "{lit(data_big)}";'],
    ["static long HEAD_N = 1;"],
    ["#define HEAD_DATA head_data", "#define HEAD_N head_n"])
results["A_dbg3_shape"] = {"status": rA[0], "detail": rA[1], "cursor": rA[2],
                           "ring_words": rA[3]}

# Leg B — fixture-builder shape: seed head_n directly, alias after
rB = run_raw(
    [f'static const char *head_data = "{lit(data_big)}";',
     "static long head_n = 1;"],
    [],
    ["#define HEAD_DATA head_data", "#define HEAD_N head_n"])
results["B_fixture_shape"] = {"status": rB[0], "detail": rB[1], "cursor": rB[2],
                              "ring_words": rB[3]}
if rB[0] == "OK":
    raw = b"".join(w.to_bytes(4, "little") for w in rB[3])
    results["B_fixture_shape"]["decoded_first32"] = raw[:32].decode(
        "ascii", errors="replace")
    results["B_fixture_shape"]["host_head_first16"] = data_big[:16]

# Leg C — _shell_native fix shape: derived HEAD_N=1, NO HEAD_N alias
rC = run_raw(
    [f'static const char *head_data = "{lit(data_big)}";'],
    ["static long HEAD_N = 1;"],
    ["#define HEAD_DATA head_data"])
results["C_shellnative_shape"] = {"status": rC[0], "detail": rC[1],
                                  "cursor": rC[2], "ring_words": rC[3]}
if rC[0] == "OK":
    raw = b"".join(w.to_bytes(4, "little") for w in rC[3])
    results["C_shellnative_shape"]["decoded_first32"] = raw[:32].decode(
        "ascii", errors="replace")

# Leg D — correct shape, short file: single frame byte-exact vs host
rD = run_raw(
    [f'static const char *head_data = "{lit(data_small)}";',
     "static long head_n = 1;"],
    [],
    ["#define HEAD_DATA head_data", "#define HEAD_N head_n"])
results["D_short_file"] = {"status": rD[0], "detail": rD[1], "cursor": rD[2],
                           "ring_words": rD[3]}
if rD[0] == "OK":
    raw = b"".join(w.to_bytes(4, "little") for w in rD[3])
    results["D_short_file"]["decoded"] = raw.decode("ascii", errors="replace")
    results["D_short_file"]["host_head"] = data_small[:1] + "\n"  # head -n1 "hi\n" -> "hi\n"

blob = repr(results)
print(blob)
print("results_md5=", hashlib.md5(blob.encode()).hexdigest())
