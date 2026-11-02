#!/usr/bin/env python3
"""
mkv_dep_scanner.py -- Trace the transitive local-import closure of one entry
point and report which of those files are (and aren't) already stored in a
va_container.py .mkv, instead of guessing or bulk-injecting tools/ and src/.

Static AST import scanning has real limits: it can't see imports made
conditionally, dynamically (importlib), or behind a try/except fallback,
and it can't tell which of several same-named files (e.g. tools/phonemes.py
vs src/phonemes.py) a given `sys.path` hack actually intends at runtime.
Ambiguous or unresolved names are reported as such, not silently guessed.

Commands:
  scan <entry.py> [--repo-root DIR]              trace closure, print report
  check <entry.py> <container.mkv> [--repo-root DIR]
                                                  scan + cross-reference against
                                                  a container's directory
"""

import argparse
import ast
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", ".venv", "venv", ".venv_test", "test_env", "node_modules", "__pycache__",
    ".va_run_cache", "target", "dist", "build", ".pytest_cache",
    # vendored/bundled Python trees and boot-image build output -- these contain
    # files that shadow real dependency names (scipy, soundfile, typing_extensions,
    # ...) under a vendored copy, not the project's own source.
    "lib", "output", "initramfs-cognitive", "site-packages",
}

STDLIB = set(getattr(sys, "stdlib_module_names", ()))


def build_module_index(repo_root: Path) -> dict:
    """Map every plausible local import name to the repo-relative .py file(s)
    it could refer to: bare basename ('speak') and dotted path ('tools.wordbase').
    """
    index: dict[str, list[Path]] = {}
    for py in repo_root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in py.parts):
            continue
        rel = py.relative_to(repo_root)
        basename = py.stem
        dotted = ".".join(rel.with_suffix("").parts)
        index.setdefault(basename, []).append(rel)
        index.setdefault(dotted, []).append(rel)
    return index


def extract_imports(source: str) -> set:
    """Top-level module names this file imports (first dotted component
    kept whole for 'import x.y' style, and the module part of 'from x.y import z').
    Relative imports (from . import x) are skipped -- they resolve within
    the same package, not against the repo-wide index.
    """
    names = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module)
    return names


def resolve(name: str, index: dict) -> list:
    """Candidate repo-relative paths for an import name, checking the full
    dotted name first, then progressively shorter prefixes, then the bare
    last component (covers 'from tools import wordbase' style access too).
    """
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in index:
            return index[candidate]
    if parts[-1] in index:
        return index[parts[-1]]
    return []


def trace_closure(entry: Path, repo_root: Path, index: dict) -> dict:
    """BFS the local-import graph starting at entry. Returns:
    resolved: {repo_rel_path: [importer paths]}
    ambiguous: {import_name: [candidate paths]}  (>1 match, not auto-picked)
    unresolved: {import_name: [importer paths]}  (looks local, no match)
    """
    resolved, ambiguous, unresolved = {}, {}, {}
    seen = set()
    queue = [entry.resolve()]
    while queue:
        current = queue.pop()
        if current in seen or not current.exists():
            continue
        seen.add(current)
        source = current.read_text(errors="replace")
        importer_rel = str(current.relative_to(repo_root)) if current.is_relative_to(repo_root) else str(current)
        for name in extract_imports(source):
            top = name.split(".")[0]
            if top in STDLIB:
                continue
            candidates = resolve(name, index)
            if not candidates:
                unresolved.setdefault(name, []).append(importer_rel)
                continue
            unique = {repo_root / c for c in candidates}
            if len(unique) > 1:
                ambiguous.setdefault(name, sorted(str(c.relative_to(repo_root)) for c in unique))
                continue
            picked = next(iter(unique))
            resolved.setdefault(str(picked.relative_to(repo_root)), []).append(importer_rel)
            if picked not in seen:
                queue.append(picked)
    return {"resolved": resolved, "ambiguous": ambiguous, "unresolved": unresolved}


def cmd_scan(args):
    repo_root = Path(args.repo_root).resolve()
    entry = Path(args.entry).resolve()
    index = build_module_index(repo_root)
    closure = trace_closure(entry, repo_root, index)
    print(f"local-import closure of {entry.relative_to(repo_root)}:\n")
    for path in sorted(closure["resolved"]):
        print(f"  {path}")
    if closure["ambiguous"]:
        print("\nambiguous (multiple candidates, not auto-picked -- resolve by hand):")
        for name, candidates in closure["ambiguous"].items():
            print(f"  {name!r}: {candidates}")
    if closure["unresolved"]:
        print("\nunresolved (looked local, no matching file in repo):")
        for name, importers in closure["unresolved"].items():
            print(f"  {name!r} (imported by {importers[0]}{', ...' if len(importers) > 1 else ''})")
    return closure


def cmd_check(args):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from va_container import read_directory

    closure = cmd_scan(args)
    container_entries = {e["name"] for e in read_directory(Path(args.container))["entries"]}

    present, missing = [], []
    for path in closure["resolved"]:
        # container entries in this project have been added under varying
        # name conventions (bare basename or repo-relative) -- match either.
        if path in container_entries or Path(path).name in container_entries:
            present.append(path)
        else:
            missing.append(path)

    print(f"\n--- cross-reference against {args.container} ---")
    print(f"present ({len(present)}):")
    for p in sorted(present):
        print(f"  OK   {p}")
    print(f"missing ({len(missing)}):")
    for p in sorted(missing):
        print(f"  MISS {p}")
    if closure["ambiguous"] or closure["unresolved"]:
        print("\n(ambiguous/unresolved imports above are not counted as present or "
              "missing -- they need manual resolution first)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("scan")
    ps.add_argument("entry")
    ps.add_argument("--repo-root", default=".")
    ps.set_defaults(func=cmd_scan)

    pc = sub.add_parser("check")
    pc.add_argument("entry")
    pc.add_argument("container")
    pc.add_argument("--repo-root", default=".")
    pc.set_defaults(func=cmd_check)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
