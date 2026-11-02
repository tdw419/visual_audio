#!/usr/bin/env python3
"""tools/build_workbench_container.py — CLAIM QUEUE item 22b: the standalone
one-file workbench container (round-11 addendum, items 22+23 merged: ONE
staging mechanism, TWO verification contexts).

Context 1 (local dev) is BK-25's stage_workbench(). Context 2 (standalone)
is THIS module: build_container(manifest) emits a SINGLE self-extracting
.py file whose bootstrap is stdlib-only — it unpacks its payload into the
IDENTICAL session-root layout (w.dat + bin/ + scripts/ + tests/ + the
experiments/tools/src import-root contract), verifies every file against
its sha256 BEFORE writing (loud ERR:CHECKSUM refusal, never silent
corruption), and enforces the PATH_CAP layout constraint at unpack time
(loud ERR:PATHCAP refusal) with the cap baked in from
experiments.glyph_l1_shell at BUILD time so the two can never drift.

Format decision at landing (round-11: "PNG-family or self-extracting .py;
final call at landing"): SELF-EXTRACTING .PY. Reasons, measured not
aesthetic: (a) stdlib bootstrap runs on any host CPython with zero deps —
the PNG carrier's decode path needs PIL host-side too, but the .py needs
nothing; (b) programs + data in one file is exactly round-11 doctrine —
the interpreter is explicitly NOT carried; (c) VFS-1's PNG transport
(png_vfs.py) already owns the PNG story for DISKS — the workbench carrier
does not need a second PNG format. Payload files are content COPIES (a
container must not depend on the staging machine's tree — unpack_manifest's
contract, kept).

CLI (mirrors the BK-25 smoke style):
    python3 tools/build_workbench_container.py --emit /tmp/wb_container.py
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_REPO / "experiments") not in sys.path:
    sys.path.insert(0, str(_REPO / "experiments"))

from experiments.glyph_l1_shell import PATH_CAP  # noqa: E402

CONTAINER_TEMPLATE = '''#!/usr/bin/env python3
"""Self-extracting glyph workbench container (item 22b, round-11 format
decision: stdlib-only self-extracting .py; interpreter NOT carried).

Usage:
    python3 workbench_container.py [--base DIR]

Unpacks the workbench session root (w.dat + bin/ + scripts/ + tests/)
under --base (default: a fresh short /tmp/gwb_* dir), verifying every
file's sha256 before writing. Prints WORKBENCH_ROOT=<path> on success.
Loud refusals: ERR:CHECKSUM (corrupt payload), ERR:PATHCAP (base too long
for the engine's PATH_CAP={path_cap}).
"""
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

PATH_CAP = {path_cap}

# PAYLOAD-BEGIN
PAYLOAD = json.loads(r\'\'\'{payload_json}\'\'\')
# PAYLOAD-END


def _fail(msg: str, code: int) -> "NoReturn":  # type: ignore[valid-type]
    sys.stderr.write(msg + "\\n")
    raise SystemExit(code)


def main() -> int:
    args = sys.argv[1:]
    base = None
    if args:
        if args[0] == "--base" and len(args) >= 2:
            base = Path(args[1]).expanduser()
        else:
            _fail("usage: workbench_container.py [--base DIR]", 2)
    if base is None:
        base = Path(tempfile.mkdtemp(prefix="gwb_"))
    base = base.resolve()
    base.mkdir(parents=True, exist_ok=True)

    manifest = PAYLOAD
    root = base / manifest["root_name"]
    seed = str(root / "w.dat")
    if len(seed) > PATH_CAP:
        _fail(f"ERR:PATHCAP seed path {{seed!r}} is {{len(seed)}} bytes, "
              f"cap {{PATH_CAP}} (experiments/glyph_l1_shell.py:85; use a "
              f"SHORTER --base)", 2)

    # Verify EVERY payload file before touching the filesystem — a corrupt
    # container refuses loudly and unpacks nothing (no silent partial root).
    decoded = {{}}
    for rel, rec in manifest["files"].items():
        raw = base64.b64decode(rec["b64"])
        if hashlib.sha256(raw).hexdigest() != rec["sha256"]:
            _fail(f"ERR:CHECKSUM {{rel}}: sha256 mismatch — container "
                  f"payload corrupted; refusing to unpack", 3)
        decoded[rel] = raw

    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / "w.dat").write_bytes(b"\\0" * 8)
    for d in ("bin", "scripts", "tests", "experiments", "tools", "src"):
        (root / d).mkdir(parents=True, exist_ok=True)
    for rel, raw in decoded.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)

    print(f"WORKBENCH_ROOT={{root}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def build_container(manifest: dict, path_cap: int = PATH_CAP) -> str:
    """Emit the standalone container source for `manifest`.

    manifest = {
      "root_name": str,
      "entries": {rel_path: host_path},   # staged as CONTENT COPIES
      "content": {rel_path: str},         # optional literal files
    }
    Every file is recorded with its sha256; the container refuses loudly
    on any mismatch. PATH_CAP is baked from the engine at build time.
    """
    files: dict[str, dict[str, str]] = {}
    for rel, host in manifest.get("entries", {}).items():
        raw = Path(host).read_bytes()
        files[rel] = {"b64": base64.b64encode(raw).decode("ascii"),
                      "sha256": hashlib.sha256(raw).hexdigest()}
    for rel, text in manifest.get("content", {}).items():
        raw = text.encode("utf-8")
        files[rel] = {"b64": base64.b64encode(raw).decode("ascii"),
                      "sha256": hashlib.sha256(raw).hexdigest()}
    if "w.dat" in files:
        raise ValueError("w.dat is the container's own arm — not a payload entry")
    payload = {"root_name": manifest["root_name"], "files": files}
    payload_json = json.dumps(payload, sort_keys=True)
    if "'''" in payload_json:
        # b64+hex+json never produce triple quotes; refuse anyway (loud, not lucky)
        raise ValueError("payload JSON contains ''' — template escape hazard")
    return CONTAINER_TEMPLATE.format(path_cap=path_cap, payload_json=payload_json)


def main() -> int:
    ap = argparse.ArgumentParser(description="build a standalone workbench container")
    ap.add_argument("--emit", required=True, help="output .py path")
    ap.add_argument("--root-name", default="gwb_standalone",
                    help="SHORT: the session root lands under a /tmp base, "
                         "and the L1 shell's FS-window path budget caps the "
                         "FULL file path (measured: root <= ~37 chars; "
                         "longer names ERR:PATH at first cat/argv stamp)")
    args = ap.parse_args()
    manifest = {
        "root_name": args.root_name,
        "entries": {},
        "content": {"bin/README": "glyph workbench container (item 22b)\n"},
    }
    Path(args.emit).write_text(build_container(manifest))
    print(f"container written: {args.emit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
