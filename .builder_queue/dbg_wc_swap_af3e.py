#!/usr/bin/env python3
"""Debug leg: why does _shell_native('wc') return ERR:SHELLNATIVE:wc?
Re-run the internal chain step by step with the loud-refusal sites
instrumented. Verdicts from returned strings/receipts only."""
import sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "experiments"))

import shutil  # noqa: E402
print("gcc present:", shutil.which("riscv64-unknown-elf-gcc") is not None)

from tools.glyph_gpt.coreutils_port import _TOOL_SOURCES, _VOL2_TOOL_SOURCES  # noqa: E402
print("wc in V1:", "wc" in _TOOL_SOURCES, "| wc in VOL2:", "wc" in _VOL2_TOOL_SOURCES)
print("head in V1:", "head" in _TOOL_SOURCES, "| head in VOL2:", "head" in _VOL2_TOOL_SOURCES)

# Now replicate the glyph_l1_shell._shell_native import block exactly:
try:
    from tests.test_gh23_libc_runtime import _load_posix_program, LIBC_C, SHIM_S
    print("libc runtime imports: OK")
except Exception as exc:  # noqa: BLE001
    print(f"libc runtime imports FAILED: {type(exc).__name__}: {exc}")

try:
    from tools.glyph_gpt.baker import libc_runtime_kernel_image
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.runner import GlyphRunner
    print("baker/atlas/runner imports: OK")
except Exception as exc:  # noqa: BLE001
    print(f"baker/atlas/runner imports FAILED: {type(exc).__name__}: {exc}")

# And the shell itself with _SHELL_NATIVE forced on, capturing the exact verb branch:
from glyph_l1_shell import GlyphL1Shell, L1Session  # noqa: E402

with tempfile.TemporaryDirectory(prefix="b9d_") as td:
    td = Path(td)
    a = td / "small.txt"
    a.write_bytes(b"hello world\nsecond line here\n")
    shell = GlyphL1Shell(session=L1Session(root=td))
    print("shell._SHELL_NATIVE:", shell._SHELL_NATIVE)
    # _read_guest first
    try:
        data = shell._read_guest("small.txt")
        print(f"_read_guest OK, len={len(data)}")
    except Exception as exc:  # noqa: BLE001
        print(f"_read_guest FAILED: {type(exc).__name__}: {exc}")
        raise SystemExit(0)
    # try the full native path again with the cache disabled to see fresh-bake leg
    shell._SHELLNATIVE_BAKE_CACHE = False
    out = shell._shell_native("wc", "small.txt")
    print("fresh-bake native wc ->", repr(out))
