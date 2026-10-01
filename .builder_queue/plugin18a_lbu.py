"""pytest plugin — load a DEFECT-16c-patched copy of tools/rv64i_to_glyph.py.

Why: the held patch .builder_queue/held_patches/defect16c_lbu_lhu.patch is required
for BK-11's `wc` leg but is NOT committed (it regresses BK-1 leg 2 until preemption
is sound — DEFECT-18). This plugin lets a gate run use the patched transpiler
WITHOUT touching the tracked tree: it copies the working-tree source (asserted clean
against HEAD) into .builder_queue/variant18a/tools/, applies the held patch with GNU
patch, and installs the result in sys.modules before any test imports the real
module.

Enable explicitly:  PYTHONPATH=.builder_queue python3 -m pytest ... -p plugin18a_lbu
Prototype instrumentation for the parked DEFECT-18 decision — not a landed change.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "tools" / "rv64i_to_glyph.py"
HELD = REPO / ".builder_queue" / "held_patches" / "defect16c_lbu_lhu.patch"
VBASE = REPO / ".builder_queue" / "variant18a"
VARIANT = VBASE / "tools" / "rv64i_to_glyph.py"

# The variant copy computes its own sys.path root from __file__, which now points
# into .builder_queue/variant18a — put the real tools/ + repo root on the path first
# so the module's own `from rv64i_decode import ...` resolves to the landed files.
for _p in (str(REPO / "tools"), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

if subprocess.run(["git", "-C", str(REPO), "diff", "--quiet", "HEAD", "--",
                   "tools/rv64i_to_glyph.py"]).returncode != 0:
    sys.exit("plugin18a_lbu: tools/rv64i_to_glyph.py differs from HEAD — refusing to "
             "build a variant from a dirty tree (another session may be mid-edit)")

VBASE.mkdir(parents=True, exist_ok=True)
VARIANT.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(TARGET, VARIANT)
_patch = subprocess.run(["patch", "-p1", "-s", "-F0", "-i", str(HELD)],
                        cwd=VBASE, capture_output=True, text=True)
if _patch.returncode != 0:
    sys.exit(f"plugin18a_lbu: GNU patch failed ({_patch.returncode}): "
             f"{_patch.stdout}{_patch.stderr}")
_lines_before = len(TARGET.read_text().splitlines())
_lines_after = len(VARIANT.read_text().splitlines())

_spec = importlib.util.spec_from_file_location("rv64i_to_glyph", VARIANT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["rv64i_to_glyph"] = _mod
_spec.loader.exec_module(_mod)
sys.modules["tools.rv64i_to_glyph"] = _mod
try:
    import tools  # noqa: F401
    setattr(tools, "rv64i_to_glyph", _mod)
except Exception:
    pass


def pytest_report_header(config):
    return (f"plugin18a_lbu: VARIANT transpiler {VARIANT.relative_to(REPO)} "
            f"({_lines_before} -> {_lines_after} lines; HEAD + DEFECT-16c "
            f"LBU/LHU hunks from held patch; tracked tree untouched)")
