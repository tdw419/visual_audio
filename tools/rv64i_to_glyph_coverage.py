#!/usr/bin/env python3
"""
G5: generate the RV64I/RV32I opcode coverage table for rv64i_to_glyph.py
FROM THE CODE, not hand-maintained prose.

Parses transpile_rv32i_to_glyph()'s AST to find every OP_* name compared
against `op` (in `op == OP_X` or `op in (OP_X, OP_Y, ...)`), cross-references
against every OP_* constant rv64i_decode.py defines, and prints a table of
handled vs. unhandled opcodes. Run directly; also importable (get_coverage()).
"""
import ast
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tools"))
sys.path.insert(0, str(_REPO_ROOT))

import rv64i_decode as decode_mod  # noqa: E402


def _handled_op_names(source_path: Path) -> set:
    """AST-walk transpile_rv32i_to_glyph, collecting every OP_* identifier
    compared against the `op` variable in an `if`/`elif` condition."""
    tree = ast.parse(source_path.read_text())
    func = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "transpile_rv32i_to_glyph"
    )

    handled = set()

    def collect_names(node):
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and n.id.startswith("OP_"):
                handled.add(n.id)

    def walk_ifs(node):
        for n in ast.walk(node):
            if isinstance(n, ast.Compare):
                # op == OP_X  or  op in (OP_X, OP_Y)
                if any(isinstance(c, (ast.Eq, ast.In)) for c in n.ops):
                    collect_names(n)

    walk_ifs(func)
    return handled


def get_coverage():
    all_ops = {
        name: val for name in dir(decode_mod)
        if name.startswith("OP_") and name != "OP_INVALID"
        for val in [getattr(decode_mod, name)]
    }
    handled = _handled_op_names(_REPO_ROOT / "tools" / "rv64i_to_glyph.py")
    covered = {n: v for n, v in all_ops.items() if n in handled}
    uncovered = {n: v for n, v in all_ops.items() if n not in handled}
    return covered, uncovered


def main():
    covered, uncovered = get_coverage()
    print(f"# rv64i_to_glyph.py opcode coverage\n")
    print(f"Generated from `transpile_rv32i_to_glyph`'s own AST against every "
          f"`OP_*` constant in `rv64i_decode.py` -- not hand-maintained. "
          f"Regenerate with `python3 tools/rv64i_to_glyph_coverage.py > "
          f"tools/GLYPH_TRANSPILER_OPCODE_COVERAGE.md` whenever the transpiler "
          f"gains a new opcode case; this file will silently rot otherwise "
          f"(it is not auto-checked).\n")
    print(f"**{len(covered)}/{len(covered) + len(uncovered)} opcodes handled.**\n")
    print("## Handled\n")
    for name in sorted(covered):
        print(f"- `{name}`")
    print("\n## NOT handled (raises ValueError if encountered)\n")
    for name in sorted(uncovered):
        print(f"- `{name}`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
