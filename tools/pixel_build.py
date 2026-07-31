#!/usr/bin/env python3
"""
pixel_build.py — general-purpose "software that lives as pixels" workflow.

Generalizes the one-off pattern proven in wordbase_boot_skeleton.py
(semantic_cpu_emulator.py <-> semantic_cpu_emulator.py.pixel) to any file:

    pixel_build.py add my_tool.py
        -> optionally macro-expands the source (see macro_expand.py)
        -> encodes it byte-level via the wordbase PixelTokenizer
        -> verifies the encoding round-trips before touching the MKV
        -> stores it in visual_audio.mkv as "my_tool.py.pixel" (add or
           update, whichever the entry needs)

    pixel_build.py run my_tool.py [-- program args...]
        -> extracts "my_tool.py.pixel" from the MKV
        -> decodes it back to source bytes
        -> compile-checks it (for .py targets)
        -> executes it, inheriting this terminal

The MKV entry is the artifact of record; the file on disk is a convenience
cache, not the source of truth.
"""

import argparse
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MKV_PATH = REPO_ROOT / "visual_audio.mkv"
SPECIAL_OFFSET = 16  # word IDs 0-15 are reserved special tokens

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).parent))


def _tokenizer():
    from src.pixel_tokenizer import PixelTokenizer
    return PixelTokenizer()


def encode_bytes_to_pixels(raw: bytes) -> bytes:
    tok = _tokenizer()
    try:
        word_ids = [b + SPECIAL_OFFSET for b in raw]
        pixels = tok.ids_to_pixels(word_ids)
        return pixels.tobytes()
    finally:
        tok.close()


def decode_pixels_to_bytes(pixel_data: bytes) -> bytes:
    import numpy as np
    tok = _tokenizer()
    try:
        pixels = np.frombuffer(pixel_data, dtype=np.uint8).reshape(-1, 3)
        word_ids = tok.pixels_to_ids(pixels)
        return bytes([w - SPECIAL_OFFSET for w in word_ids if w >= SPECIAL_OFFSET])
    finally:
        tok.close()


def _mkv_ls() -> str:
    result = subprocess.run(
        ["python3", "tools/va_container.py", "ls", str(MKV_PATH)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"failed to list MKV: {result.stderr}")
    return result.stdout


def cmd_add(args):
    src_path = Path(args.path)
    if not src_path.exists():
        sys.exit(f"ERROR: no such file: {src_path}")

    raw = src_path.read_bytes()

    if not args.no_macros:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            pass
        else:
            from macro_expand import expand
            expanded = expand(text)
            if expanded != text:
                print(f"[macros] expanded {len(text)} -> {len(expanded)} chars")
            raw = expanded.encode("utf-8")

    name = args.name or src_path.name
    pixel_name = f"{name}.pixel"

    print(f"Encoding {name} ({len(raw)} bytes) via wordbase...")
    pixel_bytes = encode_bytes_to_pixels(raw)
    print(f"  -> {len(pixel_bytes)} pixel bytes")

    # Verify round-trip before writing anything to the MKV.
    recovered = decode_pixels_to_bytes(pixel_bytes)
    if recovered != raw:
        sys.exit("ERROR: round-trip verification FAILED, refusing to store")
    print("  round-trip verified locally: PASS")

    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pixels") as f:
        f.write(pixel_bytes)
        tmp_path = f.name

    try:
        exists = pixel_name in _mkv_ls()
        subcmd = "update" if exists else "add"
        cmd = ["python3", "tools/va_container.py", subcmd, str(MKV_PATH)]
        if subcmd == "add":
            cmd += [tmp_path, "--name", pixel_name, "--role", "pixel_software"]
        else:
            cmd += [pixel_name, tmp_path]
        cmd += ["--note", args.note or f"pixel-encoded {name}"]

        print(f"Storing in MKV ({subcmd})...")
        result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        if result.returncode != 0:
            sys.exit(f"ERROR: MKV {subcmd} failed: {result.stderr}")
        print(f"  {result.stdout.strip()}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    print(f"\n✓ Stored '{name}' as '{pixel_name}' in {MKV_PATH.name}")


def cmd_run(args):
    name = args.name
    pixel_name = f"{name}.pixel"

    if pixel_name not in _mkv_ls():
        sys.exit(f"ERROR: no such entry: {pixel_name} (use 'add' first)")

    tmp_pixel_path = Path(tempfile.mktemp(suffix=".pixels"))
    result = subprocess.run(
        ["python3", "tools/va_container.py", "cat", str(MKV_PATH),
         pixel_name, "-o", str(tmp_pixel_path)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"ERROR: extract failed: {result.stderr}")

    try:
        pixel_data = tmp_pixel_path.read_bytes()
        source_bytes = decode_pixels_to_bytes(pixel_data)
    finally:
        tmp_pixel_path.unlink(missing_ok=True)

    out_path = Path(tempfile.mktemp(suffix=Path(name).suffix or ".out"))
    out_path.write_bytes(source_bytes)
    print(f"Decoded {len(source_bytes)} bytes -> {out_path}")

    if out_path.suffix == ".py":
        try:
            py_compile.compile(str(out_path), doraise=True)
            print("  compiles: OK")
        except py_compile.PyCompileError as e:
            sys.exit(f"ERROR: decoded source does not compile: {e}")
        exec_cmd = ["python3", str(out_path)] + args.program_args
    else:
        out_path.chmod(0o755)
        exec_cmd = [str(out_path)] + args.program_args

    print(f"Running: {' '.join(exec_cmd)}")
    return subprocess.call(exec_cmd)


def cmd_list(args):
    """List pixel entries and their relationships."""
    import re
    from collections import defaultdict

    print(f"\n{MKV_PATH.name} pixel entries:\n")
    print("=" * 70)

    ls_output = _mkv_ls()
    # Parse entries, accounting for role prefix: "[role] name"
    pixel_entries = []
    for line in ls_output.split('\n'):
        line = line.strip()
        if not line or '.pixel' not in line:
            continue
        # Extract name after role prefix: "[role] name                    frames X..Y..."
        # Split on whitespace, skip the role prefix [role], take next token(s) until "frames"
        parts = line.split()
        if len(parts) >= 2:
            # parts[0] is "[role]", parts[1+] is name followed by metadata
            name_parts = []
            for part in parts[1:]:
                if part == 'frames':
                    break
                name_parts.append(part)
            name = ' '.join(name_parts)
            pixel_entries.append(name)

    if not pixel_entries:
        print("No pixel entries found.")
        return 0

    # Group entries by base name (strip .pixel, .pixel_vN suffixes)
    groups = defaultdict(dict)  # base_name -> {suffix: entry}

    for entry in pixel_entries:
        # Match patterns: name.pixel, name.pixel_v1, name.pixel_v2, etc.
        match = re.match(r'^(.+?)\.pixel(_v\d+)?$', entry)
        if match:
            base_name = match.group(1)
            version_suffix = match.group(2) or ''  # '' for current, '_vN' for versions
            groups[base_name][version_suffix] = entry

    # Check which entries have live source files on disk
    live_sources = set()
    for path in REPO_ROOT.rglob('*.py'):
        if path.is_file():
            live_sources.add(path.name)
            # Also check tools/ subdir
            if 'tools/' in str(path):
                relative = path.relative_to(REPO_ROOT)
                live_sources.add(str(relative))
            if 'test_batch_tools/' in str(path):
                relative = path.relative_to(REPO_ROOT)
                live_sources.add(str(relative))

    # Display organized by base name
    for base_name in sorted(groups.keys()):
        versions = groups[base_name]

        # Determine status
        has_current = '' in versions
        has_versions = any(v for v in versions if v != '')
        live_on_disk = (base_name in live_sources or
                       f'tools/{base_name}' in live_sources or
                       f'test_batch_tools/{base_name}' in live_sources)

        status = []
        if has_current:
            status.append("current")
        if has_versions:
            status.append(f"{len(versions)-1} version(s)")
        if live_on_disk:
            status.append("disk OK")
        else:
            status.append("disk STALE")

        print(f"\n{base_name}")
        print(f"  Status: {', '.join(status)}")

        for suffix in sorted(versions.keys(), reverse=True):  # Show highest version first
            entry = versions[suffix]
            display = f"  {entry}"
            if suffix == '':
                display += " ← current"
            print(display)

    print("\n" + "=" * 70)
    print(f"Total: {len(pixel_entries)} pixel entries, {len(groups)} unique software items")
    return 0


def cmd_diff(args):
    """Compare a source file on disk against its pixel-encoded version in the MKV."""
    name = args.name
    pixel_name = f"{name}.pixel"

    if pixel_name not in _mkv_ls():
        sys.exit(f"ERROR: no such pixel entry: {pixel_name}")

    # Extract pixel data from MKV
    tmp_pixel_path = Path(tempfile.mktemp(suffix=".pixels"))
    result = subprocess.run(
        ["python3", "tools/va_container.py", "cat", str(MKV_PATH),
         pixel_name, "-o", str(tmp_pixel_path)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"ERROR: extract failed: {result.stderr}")

    try:
        pixel_data = tmp_pixel_path.read_bytes()
        source_bytes = decode_pixels_to_bytes(pixel_data)
    finally:
        tmp_pixel_path.unlink(missing_ok=True)

    # Read source from disk
    src_path = Path(args.path or name)
    if not src_path.exists():
        sys.exit(f"ERROR: no such file on disk: {src_path}")

    disk_bytes = src_path.read_bytes()

    # Compare
    if source_bytes == disk_bytes:
        print(f"✓ {name}: pixel entry matches disk file")
        print(f"  Size: {len(source_bytes)} bytes")
        return 0
    else:
        print(f"✗ {name}: pixel entry differs from disk file")
        print(f"  Pixel size: {len(source_bytes)} bytes")
        print(f"  Disk size: {len(disk_bytes)} bytes")

        if args.detailed:
            import difflib
            try:
                disk_text = disk_bytes.decode('utf-8')
                pixel_text = source_bytes.decode('utf-8')
                diff = difflib.unified_diff(
                    disk_text.splitlines(keepends=True),
                    pixel_text.splitlines(keepends=True),
                    fromfile=f"{src_path}",
                    tofile=f"{MKV_PATH.name}::{pixel_name}",
                )
                print()
                print(''.join(diff))
            except UnicodeDecodeError:
                print("  (binary content - cannot show detailed diff)")

        return 1


def cmd_verify(args):
    """Verify pixel entry round-trip (extract, decode, validate)."""
    name = args.name
    pixel_name = f"{name}.pixel"

    if pixel_name not in _mkv_ls():
        sys.exit(f"ERROR: no such pixel entry: {pixel_name}")

    print(f"Verifying '{pixel_name}'...")

    # Extract pixel data from MKV
    tmp_pixel_path = Path(tempfile.mktemp(suffix=".pixels"))
    result = subprocess.run(
        ["python3", "tools/va_container.py", "cat", str(MKV_PATH),
         pixel_name, "-o", str(tmp_pixel_path)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"ERROR: extract failed: {result.stderr}")

    try:
        pixel_data = tmp_pixel_path.read_bytes()
        source_bytes = decode_pixels_to_bytes(pixel_data)
    finally:
        tmp_pixel_path.unlink(missing_ok=True)

    print(f"  Extracted {len(source_bytes)} bytes")

    # Round-trip verification
    reencoded = encode_bytes_to_pixels(source_bytes)
    if reencoded != pixel_data:
        print(f"✗ Round-trip verification FAILED")
        print(f"  Original pixel data: {len(pixel_data)} bytes")
        print(f"  Re-encoded pixel data: {len(reencoded)} bytes")
        return 1

    # Compile-check for Python files (unless --no-compile)
    compile_check = not getattr(args, 'no_compile', False)
    if compile_check and (name.endswith('.py') or not name.endswith('.')):
        try:
            # Write to temp file for py_compile (it needs a file path)
            tmp_py_path = Path(tempfile.mktemp(suffix=".py"))
            tmp_py_path.write_bytes(source_bytes)
            try:
                py_compile.compile(str(tmp_py_path), doraise=True)
                print(f"  compiles: OK")
            finally:
                tmp_py_path.unlink(missing_ok=True)
        except py_compile.PyCompileError as e:
            print(f"✗ Compile check FAILED")
            print(f"  {e}")
            return 1

    print(f"✓ All checks passed")
    return 0


def _get_next_version_name(base_name: str) -> str:
    """Find the next available version number for a base name."""
    import re
    result = subprocess.run(
        ["python3", "tools/va_container.py", "ls", str(MKV_PATH)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"failed to list MKV: {result.stderr}")

    max_v = 0
    pixel_name = f"{base_name}.pixel"
    for line in result.stdout.split('\n'):
        match = re.search(rf'{re.escape(pixel_name)}_v(\d+)', line)
        if match:
            v = int(match.group(1))
            if v > max_v:
                max_v = v

    return f"{base_name}.pixel_v{max_v + 1}"


def cmd_version(args):
    """Manage version history of pixel-stored entries."""
    import re

    base_name = args.name
    pixel_name = f"{base_name}.pixel"

    if pixel_name not in _mkv_ls():
        sys.exit(f"ERROR: no such pixel entry: {pixel_name}")

    if args.create:
        # Create a version snapshot: rename current .pixel to .pixel_vN
        new_version_name = _get_next_version_name(base_name)
        print(f"Creating version snapshot: {new_version_name}")

        # Extract current pixel data
        tmp_pixel_path = Path(tempfile.mktemp(suffix=".pixels"))
        result = subprocess.run(
            ["python3", "tools/va_container.py", "cat", str(MKV_PATH),
             pixel_name, "-o", str(tmp_pixel_path)],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        if result.returncode != 0:
            sys.exit(f"ERROR: extract failed: {result.stderr}")

        try:
            pixel_data = tmp_pixel_path.read_bytes()
        finally:
            tmp_pixel_path.unlink(missing_ok=True)

        # Add as new version entry
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pixels") as f:
            f.write(pixel_data)
            tmp_path = f.name

        try:
            # Add version entry
            cmd = ["python3", "tools/va_container.py", "add", str(MKV_PATH),
                   tmp_path, "--name", new_version_name, "--role", "pixel_software",
                   "--note", f"Version snapshot of {base_name}"]
            result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
            if result.returncode != 0:
                sys.exit(f"ERROR: add version failed: {result.stderr}")

            # Get metadata (frame range) from current entry
            result = subprocess.run(
                ["python3", "tools/va_container.py", "ls", str(MKV_PATH)],
                cwd=str(REPO_ROOT), capture_output=True, text=True,
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if pixel_name in line:
                        print(f"  Original: {line.strip()}")
                        break
            for line in result.stdout.split('\n'):
                if new_version_name in line:
                    print(f"  Created:  {line.strip()}")
                    break

            print(f"✓ Version snapshot created: {new_version_name}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    elif args.restore:
        # Restore a version: rename .pixel_vN to .pixel (overwrites current)
        version_name = f"{base_name}.pixel_v{args.restore}"
        if version_name not in _mkv_ls():
            sys.exit(f"ERROR: no such version: {version_name}")

        print(f"Restoring from version: {version_name}")

        # Extract version pixel data
        tmp_pixel_path = Path(tempfile.mktemp(suffix=".pixels"))
        result = subprocess.run(
            ["python3", "tools/va_container.py", "cat", str(MKV_PATH),
             version_name, "-o", str(tmp_pixel_path)],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        if result.returncode != 0:
            sys.exit(f"ERROR: extract failed: {result.stderr}")

        try:
            pixel_data = tmp_pixel_path.read_bytes()
        finally:
            tmp_pixel_path.unlink(missing_ok=True)

        # Update current entry with version data
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pixels") as f:
            f.write(pixel_data)
            tmp_path = f.name

        try:
            cmd = ["python3", "tools/va_container.py", "update", str(MKV_PATH),
                   pixel_name, tmp_path,
                   "--note", f"Restored from {version_name}"]
            result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
            if result.returncode != 0:
                sys.exit(f"ERROR: update failed: {result.stderr}")

            print(f"✓ Restored {base_name} from {version_name}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    elif args.prune:
        # Remove old versions
        result = subprocess.run(
            ["python3", "tools/va_container.py", "ls", str(MKV_PATH)],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"failed to list MKV: {result.stderr}")

        versions_to_remove = []
        for line in result.stdout.split('\n'):
            match = re.search(rf'{re.escape(base_name)}\.pixel_v(\d+)', line)
            if match:
                v = int(match.group(1))
                if args.keep and v > args.keep:
                    versions_to_remove.append((v, match.group(0)))
                elif not args.keep:
                    versions_to_remove.append((v, match.group(0)))

        if not versions_to_remove:
            print("No versions to remove.")
            return 0

        print(f"Found {len(versions_to_remove)} versions to remove:")
        for v, name in sorted(versions_to_remove, reverse=True):
            print(f"  v{v}: {name}")

        if not args.force:
            answer = input("Remove these versions? [y/N] ")
            if answer.lower() != 'y':
                print("Cancelled.")
                return 0

        for v, name in sorted(versions_to_remove, reverse=True):
            cmd = ["python3", "tools/va_container.py", "rm", str(MKV_PATH), name]
            result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  WARNING: failed to remove {name}: {result.stderr}")
            else:
                print(f"  Removed v{v}: {name}")

        print(f"✓ Removed {len([v for v,_ in versions_to_remove if result.returncode == 0])} versions")

    else:
        # Show version history
        result = subprocess.run(
            ["python3", "tools/va_container.py", "ls", str(MKV_PATH)],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"failed to list MKV: {result.stderr}")

        print(f"\nVersion history for '{base_name}':")
        print("=" * 70)

        # Find current entry
        current_info = None
        for line in result.stdout.split('\n'):
            if pixel_name in line:
                current_info = line.strip()
                break

        if current_info:
            print(f"Current (v0): {current_info}")
        else:
            print("Current (v0): NOT FOUND")

        # Find version entries
        versions = []
        for line in result.stdout.split('\n'):
            match = re.search(rf'{re.escape(base_name)}\.pixel_v(\d+)\s+(.+)', line)
            if match:
                v = int(match.group(1))
                versions.append((v, line.strip()))

        if versions:
            print(f"\nVersions ({len(versions)}):")
            for v, info in sorted(versions, reverse=True):
                print(f"  v{v}: {info}")
        else:
            print("\nNo versions found.")

        return 0


def main():
    parser = argparse.ArgumentParser(description="Pixel-encoded software workflow over visual_audio.mkv")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("add", help="encode a file and store/update it in the MKV as pixels")
    sp.add_argument("path", help="source file to encode")
    sp.add_argument("--name", help="entry name (default: source file's basename)")
    sp.add_argument("--note", help="note to store with the entry")
    sp.add_argument("--no-macros", action="store_true", help="skip macro expansion")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("run", help="extract, decode, and execute a pixel-stored entry")
    sp.add_argument("name", help="entry name as originally added (without .pixel suffix)")
    sp.add_argument("program_args", nargs=argparse.REMAINDER, help="args passed to the program")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("list", aliases=["ls"], help="list pixel entries and their version history")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("diff", help="compare disk file against pixel entry in MKV")
    sp.add_argument("name", help="entry name (without .pixel suffix)")
    sp.add_argument("--path", help="source file path on disk (default: <name>)")
    sp.add_argument("-d", "--detailed", action="store_true", help="show detailed line-by-line diff")
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("verify", help="verify pixel entry round-trip (extract, decode, validate)")
    sp.add_argument("name", help="entry name (without .pixel suffix)")
    sp.add_argument("--no-compile", action="store_true", dest="no_compile", help="skip Python compile check")
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("version", help="manage version history of pixel-stored entries")
    sp.add_argument("name", help="entry name (without .pixel suffix)")
    sp.add_argument("--create", action="store_true", help="create a new version snapshot")
    sp.add_argument("--restore", type=int, metavar="N", help="restore from version N")
    sp.add_argument("--prune", action="store_true", help="remove old versions")
    sp.add_argument("--keep", type=int, metavar="N", help="when pruning, keep N most recent versions")
    sp.add_argument("--force", action="store_true", help="skip confirmation when pruning")
    sp.set_defaults(func=cmd_version)

    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
