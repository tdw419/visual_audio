"""nbdkit Python plugin: serve a boot sector by decoding it from a PNG.

This is the standalone, minimal relative of systems/virtio_pixel_rs: the
virtual disk's bytes exist ONLY as pixels; nothing pre-decodes the PNG to a
file on disk. PXC1-convention packing (RGBA, row-major) + sha256 gates,
per docs/PIXEL_CONTAINER_SPEC_V1.md.

Run:
    nbdkit -U <socket> --foreground python pxc1_nbd_plugin.py png=boot_sector.png
Point QEMU's NBD client straight at that unix socket.
The per-request trace goes to $PXC1_NBD_TRACE; unset, it goes to a fresh temp dir.
"""
import atexit
import hashlib
import io
import json
import os
import shutil
import tempfile

import numpy as np
from PIL import Image

MAGIC = "PXC1_BOOT_V1"
FRAME = 4096

png_path = None      # set via png=/path key
trace_path = os.environ.get("PXC1_NBD_TRACE") or None
_px = None           # (FRAME, FRAME, 4) uint8
_payload = None      # first payload_bytes of the flattened RGBA stream
_payload_len = 0
_digest = None       # sha256 hex of _payload, from the PNG header
_rw = None           # live disk view: base payload + COW journal writes


def config(key, value):
    global png_path
    if key == "png":
        png_path = value


def config_complete():
    if not png_path:
        raise RuntimeError("missing png=/path/to/frame.png")
    if not os.path.exists(png_path):
        raise RuntimeError(f"no such file: {png_path}")
    global _px, _payload, _payload_len, _digest

    img = Image.open(png_path)
    meta = json.loads(img.info[MAGIC])       # KeyError if absent = reject
    if meta["format"] != MAGIC:
        raise RuntimeError(f"bad format tag {meta['format']!r}")
    px = np.asarray(img.convert("RGBA"))
    if px.shape != (FRAME, FRAME, 4):
        raise RuntimeError(f"bad frame geometry {px.shape}")
    if hashlib.sha256(px.tobytes()).hexdigest() != meta["rgba_sha256"]:
        raise RuntimeError("FATAL: RGBA stream sha256 mismatch (corruption)")
    n = int(meta["payload_bytes"])
    payload = px.reshape(-1)[:n].tobytes()
    if hashlib.sha256(payload).hexdigest() != meta["payload_sha256"]:
        raise RuntimeError("FATAL: payload sha256 mismatch (corruption)")

    _px, _payload, _payload_len, _digest = px, payload, n, meta["payload_sha256"]
    # live disk view starts as the decoded pixels; writes journal here and
    # NEVER touch the PNG (same base+jar model as the production backend)
    global _rw
    _rw = bytearray(_payload)


def open(readonly):
    return 0  # single-export handle


def get_size(handle):
    return _payload_len


def _trace(msg):
    # NOTE: module-level `open` is the nbdkit callback, so use io.open here.
    global trace_path
    if trace_path is None:
        run_dir = tempfile.mkdtemp(prefix="pxc1_nbd_")
        atexit.register(shutil.rmtree, run_dir, ignore_errors=True)
        trace_path = os.path.join(run_dir, "pxc1_trace.log")
    with io.open(trace_path, "a") as f:
        f.write(msg + "\n")


def pread(handle, count, offset, flags=0):
    if _rw is None:
        raise RuntimeError("plugin not configured (no config_complete?)")
    if offset + count > _payload_len:
        raise RuntimeError(f"read beyond end: {offset}+{count} > {_payload_len}")
    chunk = bytes(_rw[offset:offset + count])
    _trace(f"pread off={offset} n={count} data={chunk[:16].hex()}")
    return chunk


def pwrite(handle, buf, offset, flags=0):
    # COW journal: update the live view only; base PNG stays immutable.
    if _rw is None:
        raise RuntimeError("plugin not configured (no config_complete?)")
    if offset + len(buf) > _payload_len:
        raise RuntimeError(f"write beyond end: {offset}+{len(buf)} > {_payload_len}")
    _trace(f"pwrite off={offset} n={len(buf)} data={bytes(buf[:16]).hex()} "
           f"last={bytes(buf[-8:]).hex()}")
    _rw[offset:offset + len(buf)] = buf
