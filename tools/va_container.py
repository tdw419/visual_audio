#!/usr/bin/env python3
"""
va_container.py — The Visual Audio single-file container.

One lossless MKV (FFV1, RGB24, 450x450 frames) holds the whole project:
spec docs, codec rules, state, and content. The file grows as the project
grows, and the file IS the product.

Layout (per docs/research/485_visual_audio_to_software123.txt):
  Frame 0:  Directory — self-describing JSON (magic, version, entry table).
            Every entry records name, role, frame span, length, sha256.
  Frame 1+: Entry payload chunks, each wrapped in the dense_encoder frame
            format ([UA][LEN][PAYLOAD][CRC32]) and packed 3 bytes/pixel.

Mutation model is append-only: adding an entry appends payload frames and
rewrites frame 0. FFV1 is intra-only and lossless, so rebuilds are
byte-exact and any historical frame remains seekable forever.

Commands:
  init <file.mkv> [--seed]        create container (--seed embeds this tool)
  add <file.mkv> <payload> --name NAME [--role ROLE] [--note NOTE]
  cat <file.mkv> <name> [-o OUT]  extract an entry's payload
  ls <file.mkv>                   list directory entries
  verify <file.mkv>               CRC + sha256 check every entry
  run <file.mkv> <name> [args]    execute a Python tool stored in the container
  update <file.mkv> <name> <payload>  replace an entry (old frames kept as history)
"""

import argparse
import hashlib
import json
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dense_encoder import frame, unframe, MAGIC

FRAME_SIZE = 450
FRAME_BYTES = FRAME_SIZE * FRAME_SIZE * 3
MAX_PAYLOAD_PER_FRAME = 65531  # uint16 length field minus framing overhead
DIR_MAGIC = "VAC1"
FFMPEG = "ffmpeg"


# ---------------------------------------------------------------- frame I/O

def chunk_to_frame(chunk: bytes) -> np.ndarray:
    framed = frame(chunk)
    padded = framed + b"\x00" * (FRAME_BYTES - len(framed))
    return np.frombuffer(padded, dtype=np.uint8).reshape(FRAME_SIZE, FRAME_SIZE, 3)


def frame_to_chunk(frame_array: np.ndarray) -> bytes:
    """Extract payload from a frame, handling both dense_encoder wrapped and raw data."""
    raw = frame_array.tobytes()
    
    # Check if frame is dense_encoder wrapped
    if raw[:2] == MAGIC:
        (length,) = struct.unpack(">H", raw[2:4])
        # slice exactly by the length field: MAGIC(2) + LEN(2) + payload + CRC(4)
        return unframe(raw[: 4 + length + 4])
    else:
        # Raw data: return as-is (for frame-based development)
        return raw


def write_frames(frames: list, out_path: Path) -> None:
    cmd = [
        FFMPEG, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{FRAME_SIZE}x{FRAME_SIZE}", "-r", "1", "-i", "-",
        "-c:v", "ffv1", "-pix_fmt", "rgb24", str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in frames:
        proc.stdin.write(f.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg encode failed")


def read_frames(mkv_path: Path) -> list:
    cmd = [
        FFMPEG, "-loglevel", "error", "-i", str(mkv_path),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    if len(raw) % FRAME_BYTES != 0:
        raise ValueError(f"raw stream {len(raw)} bytes is not a multiple of {FRAME_BYTES}")
    return [
        np.frombuffer(raw[i : i + FRAME_BYTES], dtype=np.uint8).reshape(FRAME_SIZE, FRAME_SIZE, 3)
        for i in range(0, len(raw), FRAME_BYTES)
    ]


# ---------------------------------------------------------------- directory

def new_directory() -> dict:
    return {"magic": DIR_MAGIC, "version": 1, "created": time.time(), "entries": []}


def load_container(mkv_path: Path):
    frames = read_frames(mkv_path)
    directory = json.loads(frame_to_chunk(frames[0]))
    if directory.get("magic") != DIR_MAGIC:
        raise ValueError(f"not a VAC1 container: {mkv_path}")
    return directory, frames


def save_container(directory: dict, payload_frames: list, mkv_path: Path) -> None:
    dir_bytes = json.dumps(directory).encode()
    if len(dir_bytes) > MAX_PAYLOAD_PER_FRAME:
        raise ValueError("directory exceeds one frame; multi-frame directory not yet implemented")
    write_frames([chunk_to_frame(dir_bytes)] + payload_frames, mkv_path)


def add_entry(directory: dict, payload_frames: list, name: str, role: str,
              note: str, payload: bytes) -> None:
    if any(e["name"] == name for e in directory["entries"]):
        raise ValueError(f"entry already exists: {name}")
    chunks = [payload[i : i + MAX_PAYLOAD_PER_FRAME]
              for i in range(0, max(len(payload), 1), MAX_PAYLOAD_PER_FRAME)]
    start = 1 + len(payload_frames)  # frame 0 is the directory
    payload_frames.extend(chunk_to_frame(c) for c in chunks)
    directory["entries"].append({
        "name": name,
        "role": role,
        "note": note,
        "frames": [start, len(chunks)],
        "length": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "ts": time.time(),
    })


def read_entry(directory: dict, frames: list, name: str) -> bytes:
    for e in directory["entries"]:
        if e["name"] == name:
            start, count = e["frames"]
            payload = b"".join(frame_to_chunk(frames[i]) for i in range(start, start + count))
            return payload[: e["length"]]
    raise KeyError(f"no such entry: {name}")


# ---------------------------------------------------------------- commands

def cmd_init(args):
    directory = new_directory()
    payload_frames = []
    if args.seed:
        src = Path(__file__).resolve().read_bytes()
        add_entry(directory, payload_frames, "bootstrap/va_container.py", "bootstrap",
                  "the reader/writer for this container, stored inside it", src)
    save_container(directory, payload_frames, Path(args.container))
    print(f"created {args.container} ({1 + len(payload_frames)} frames)")


def cmd_add(args):
    path = Path(args.container)
    directory, frames = load_container(path)
    payload = sys.stdin.buffer.read() if args.payload == "-" else Path(args.payload).read_bytes()
    payload_frames = frames[1:]
    add_entry(directory, payload_frames, args.name, args.role, args.note or "", payload)
    save_container(directory, payload_frames, path)
    print(f"added {args.name}: {len(payload)} bytes in "
          f"{directory['entries'][-1]['frames'][1]} frame(s); "
          f"container now {1 + len(payload_frames)} frames")


def cmd_cat(args):
    directory, frames = load_container(Path(args.container))
    payload = read_entry(directory, frames, args.name)
    if args.output:
        Path(args.output).write_bytes(payload)
        print(f"wrote {len(payload)} bytes to {args.output}")
    else:
        sys.stdout.buffer.write(payload)


def cmd_ls(args):
    directory, _ = load_container(Path(args.container))
    print(f"{args.container}: VAC1 v{directory['version']}, "
          f"{len(directory['entries'])} entries")
    for e in directory["entries"]:
        start, count = e["frames"]
        print(f"  [{e['role']:>9}] {e['name']:<40} "
              f"frames {start}..{start + count - 1}  {e['length']} bytes")
        if e.get("note"):
            print(f"              {e['note']}")


def cmd_verify(args):
    directory, frames = load_container(Path(args.container))
    failures = 0
    for e in directory["entries"]:
        payload = read_entry(directory, frames, e["name"])  # raises on bad CRC
        ok = hashlib.sha256(payload).hexdigest() == e["sha256"]
        print(f"  {'OK  ' if ok else 'FAIL'} {e['name']} ({e['length']} bytes)")
        failures += not ok
    if failures:
        sys.exit(f"{failures} entries failed verification")
    print(f"all {len(directory['entries'])} entries verified (CRC32 + sha256)")


def cmd_read_frame(args):
    """Read a specific frame from the container, save as PNG."""
    directory, frames = load_container(Path(args.container))
    frame_id = args.frame
    if frame_id >= len(frames):
        sys.exit(f"frame {frame_id} does not exist (container has {len(frames)} frames)")
    
    frame_array = frames[frame_id]
    
    # Save as PNG
    from PIL import Image
    img = Image.fromarray(frame_array, mode='RGB')
    out_path = Path(args.output) if args.output else f"frame_{frame_id}.png"
    img.save(out_path)
    print(f"wrote frame {frame_id} to {out_path}")
    
    # Print metadata if requested
    if args.metadata:
        print(f"  Frame {frame_id}:")
        for e in directory["entries"]:
            start, count = e["frames"]
            if start <= frame_id < start + count:
                offset = frame_id - start
                print(f"    Part of entry: {e['name']} (role={e['role']}, offset={offset}/{count})")
                if e.get("note"):
                    print(f"    Note: {e['note']}")
                break
        else:
            print(f"    Free frame (not part of any entry)")


def cmd_write_frame(args):
    """Append a PNG frame to the container, optionally as part of an entry."""
    from PIL import Image
    
    path = Path(args.container)
    directory, frames = load_container(path)
    payload_frames = frames[1:]
    
    # Load PNG
    img = Image.open(args.frame)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    frame_array = np.array(img)
    
    # Check dimensions
    if frame_array.shape[0] != FRAME_SIZE or frame_array.shape[1] != FRAME_SIZE:
        sys.exit(f"frame must be {FRAME_SIZE}x{FRAME_SIZE}, got {frame_array.shape[0]}x{frame_array.shape[1]}")
    
    # Append frame
    new_frame_id = 1 + len(payload_frames)
    payload_frames.append(frame_array)
    
    # Update directory if named entry
    if args.name:
        entry_name = args.name
        entry_role = args.role or "content"
        entry_note = args.note or ""
        
        # Compute actual sha256 of the raw frame data
        frame_bytes = frame_array.tobytes()
        actual_sha256 = hashlib.sha256(frame_bytes).hexdigest()
        
        # Check if entry exists
        existing = next((e for e in directory["entries"] if e["name"] == entry_name), None)
        if existing:
            # Extend existing entry — only legal if it ends at the current tail,
            # since entry frames must stay contiguous
            start, count = existing["frames"]
            if start + count != new_frame_id:
                sys.exit(f"cannot extend {entry_name}: its frames end at "
                         f"{start + count - 1}, not at the container tail")
            existing["frames"] = [start, count + 1]
            existing["length"] += len(frame_bytes)
            full = b"".join(payload_frames[i - 1].tobytes()
                            for i in range(start, start + count + 1))
            existing["sha256"] = hashlib.sha256(full).hexdigest()
        else:
            # Create new entry
            directory["entries"].append({
                "name": entry_name,
                "role": entry_role,
                "note": entry_note,
                "frames": [new_frame_id, 1],
                "length": len(frame_bytes),
                "sha256": actual_sha256,
                "ts": time.time(),
            })
    
    # Save container
    save_container(directory, payload_frames, path)
    print(f"wrote frame {new_frame_id} to {path} (container now {1 + len(payload_frames)} frames)")
    if args.name:
        print(f"  added to entry: {args.name} (role={args.role or 'content'})")


def cmd_run(args):
    """Execute a Python tool stored inside the container.

    All bootstrap/tools-role entries are extracted (flattened by basename) into
    a temp dir so embedded tools can import each other (e.g. dense_encoder).
    The tool runs with cwd = the caller's cwd, so outputs land where you are,
    and VA_CONTAINER is set to the container's absolute path.
    """
    import os
    import tempfile

    path = Path(args.container).resolve()
    directory, frames = load_container(path)
    names = {e["name"] for e in directory["entries"]}
    if args.name not in names:
        sys.exit(f"no such entry: {args.name}")

    with tempfile.TemporaryDirectory(prefix="va_run_") as tmp:
        for e in directory["entries"]:
            if e["role"] in ("bootstrap", "tools") or e["name"] == args.name:
                dest = Path(tmp) / Path(e["name"]).name
                dest.write_bytes(read_entry(directory, frames, e["name"]))
        script = Path(tmp) / Path(args.name).name
        env = dict(os.environ, VA_CONTAINER=str(path),
                   PYTHONPATH=tmp + os.pathsep + os.environ.get("PYTHONPATH", ""))
        result = subprocess.run([sys.executable, str(script)] + args.args, env=env)
    sys.exit(result.returncode)


def cmd_update(args):
    """Replace an entry's payload. Old frames stay in the file as seekable
    history; the directory entry records where they were."""
    path = Path(args.container)
    directory, frames = load_container(path)
    entry = next((e for e in directory["entries"] if e["name"] == args.name), None)
    if entry is None:
        sys.exit(f"no such entry: {args.name} (use add to create it)")
    payload = sys.stdin.buffer.read() if args.payload == "-" else Path(args.payload).read_bytes()

    payload_frames = frames[1:]
    chunks = [payload[i : i + MAX_PAYLOAD_PER_FRAME]
              for i in range(0, max(len(payload), 1), MAX_PAYLOAD_PER_FRAME)]
    start = 1 + len(payload_frames)
    payload_frames.extend(chunk_to_frame(c) for c in chunks)

    entry.setdefault("history", []).append(
        {"frames": entry["frames"], "length": entry["length"],
         "sha256": entry["sha256"], "ts": entry["ts"]})
    entry.update(frames=[start, len(chunks)], length=len(payload),
                 sha256=hashlib.sha256(payload).hexdigest(), ts=time.time())
    if args.note:
        entry["note"] = args.note
    save_container(directory, payload_frames, path)
    print(f"updated {args.name}: {len(payload)} bytes at frames "
          f"{start}..{start + len(chunks) - 1} "
          f"(v{len(entry['history'])} archived; container now {1 + len(payload_frames)} frames)")


def cmd_list_frames(args):
    """List all frames with entry mappings."""
    directory, frames = load_container(Path(args.container))
    
    print(f"{args.container}: {len(frames)} frames total")
    print()
    
    # Build frame -> entry mapping (Frame 0 is always the directory)
    frame_to_entry = {}
    frame_to_entry[0] = {"name": "<directory>", "role": "directory", "frames": [0, 1]}
    for e in directory["entries"]:
        start, count = e["frames"]
        for i in range(count):
            frame_to_entry[start + i] = e
    
    # List frames
    for frame_id in range(len(frames)):
        if args.limit and frame_id >= args.limit:
            print(f"  ... ({len(frames) - args.limit} more frames)")
            break
        
        entry = frame_to_entry.get(frame_id)
        if entry:
            start, count = entry["frames"]
            offset = frame_id - start
            entry_name = entry["name"]
            if frame_id == 0:
                print(f"  Frame {frame_id:4d}: [{entry['role']:>9}] {entry_name}")
            else:
                print(f"  Frame {frame_id:4d}: [{entry['role']:>9}] {entry_name} (chunk {offset+1}/{count})")
        else:
            print(f"  Frame {frame_id:4d}: [   free] (not part of any entry)")
    
    # Summary
    print()
    free_frames = sum(1 for i in range(len(frames)) if i not in frame_to_entry)
    print(f"Summary: {len(frames)} frames, {free_frames} free, {len(frames) - free_frames} in entries")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="create a new container")
    sp.add_argument("container")
    sp.add_argument("--seed", action="store_true",
                    help="embed this tool's own source as the bootstrap entry")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("add", help="append an entry")
    sp.add_argument("container")
    sp.add_argument("payload", help="payload file, or - for stdin")
    sp.add_argument("--name", required=True)
    sp.add_argument("--role", default="content")
    sp.add_argument("--note")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("cat", help="extract an entry")
    sp.add_argument("container")
    sp.add_argument("name")
    sp.add_argument("-o", "--output")
    sp.set_defaults(func=cmd_cat)

    sp = sub.add_parser("ls", help="list entries")
    sp.add_argument("container")
    sp.set_defaults(func=cmd_ls)

    sp = sub.add_parser("verify", help="verify all entries")
    sp.add_argument("container")
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("read-frame", help="read a specific frame as PNG")
    sp.add_argument("container")
    sp.add_argument("frame", type=int, help="frame ID (0 = directory, 1+ = data)")
    sp.add_argument("-o", "--output", help="output PNG path (default: frame_<ID>.png)")
    sp.add_argument("--metadata", action="store_true", help="print entry metadata for this frame")
    sp.set_defaults(func=cmd_read_frame)

    sp = sub.add_parser("write-frame", help="append a PNG frame to container")
    sp.add_argument("container")
    sp.add_argument("frame", help="PNG file to append (must be 450x450 RGB24)")
    sp.add_argument("--name", help="add frame to named entry (creates or extends entry)")
    sp.add_argument("--role", help="entry role (default: content)")
    sp.add_argument("--note", help="entry note")
    sp.set_defaults(func=cmd_write_frame)

    sp = sub.add_parser("run", help="execute a Python tool stored in the container")
    sp.add_argument("container")
    sp.add_argument("name", help="entry name of the tool to run")
    sp.add_argument("args", nargs=argparse.REMAINDER, help="arguments passed to the tool")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("update", help="replace an entry's payload (old frames kept as history)")
    sp.add_argument("container")
    sp.add_argument("name")
    sp.add_argument("payload", help="payload file, or - for stdin")
    sp.add_argument("--note")
    sp.set_defaults(func=cmd_update)

    sp = sub.add_parser("list-frames", help="list all frames with entry mappings")
    sp.add_argument("container")
    sp.add_argument("--limit", type=int, help="limit output to N frames (default: all)")
    sp.set_defaults(func=cmd_list_frames)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
