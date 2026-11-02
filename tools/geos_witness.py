#!/usr/bin/env python3
"""geos_witness.py — DEFECT-20: Substrate witness attribution and write-identity loader.

Provides loud witness attribution with write-identity enforcement so substrate
witnesses cannot corroborate the wrong write.

Functions:
  take_witness(word, expect_write_id=None, image_dir=None)
    Inspects a word in the currently served kernel memory, returning a dictionary
    of witness attributes. Raises WitnessMismatch if expect_write_id does not match
    the served write_id.

  load_archived_write(write_id, publish_dir=None)
    Loads an archived write artifact (<publish_dir>/archive/kernel_memory.<write_id>.npy)
    and its sidecar, returning (words, write_id, writer, image_path, md5).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "tools") not in sys.path:
    sys.path.insert(0, str(_REPO / "tools"))

from geos_observation_server import _get_source_info, _load_memory  # noqa: E402


class WitnessMismatch(Exception):
    """Raised when the served write_id does not match the expected write_id."""
    pass


def take_witness(
    word: int,
    expect_write_id: Optional[int] = None,
    image_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Take a witness for a specific word in the served kernel memory image.

    Args:
        word: Word index in memory [0..16383].
        expect_write_id: Expected write ID. If provided and does not match
            the served image's write_id, raises WitnessMismatch.
        image_dir: Optional directory containing kernel memory image and sidecar.
            Defaults to GEOS_IMAGE_DIR or /tmp/geos_observation.

    Returns:
        dict with {word, value, write_id, writer, image_file, sidecar_file,
                   image_md5, age_seconds}

    Raises:
        WitnessMismatch: If expect_write_id does not match served write_id.
        RuntimeError: If memory image cannot be loaded.
        IndexError: If word is outside memory bounds.
    """
    dir_str = str(image_dir) if image_dir is not None else None
    memory, err = _load_memory(dir_str)
    if memory is None:
        raise RuntimeError(f"Cannot take witness: {err}")
    if not (0 <= word < len(memory)):
        raise IndexError(f"Word {word} out of bounds [0, {len(memory)})")

    source = _get_source_info(dir_str)
    served_write_id = source.get("write_id")

    if expect_write_id is not None and served_write_id != expect_write_id:
        raise WitnessMismatch(
            f"WITNESS_MISMATCH: served write_id {served_write_id} != expected {expect_write_id}"
        )

    return {
        "word": word,
        "value": int(memory[word]),
        "write_id": served_write_id,
        "writer": source.get("writer"),
        "image_file": source.get("image_file"),
        "sidecar_file": source.get("sidecar_file"),
        "image_md5": source.get("image_md5"),
        "age_seconds": source.get("age_seconds"),
    }


def load_archived_write(
    write_id: int,
    publish_dir: Optional[Union[str, Path]] = None,
) -> Tuple[List[int], int, str, Path, str]:
    """Load an archived write by its write_id.

    Args:
        write_id: Monotonically increasing write identifier.
        publish_dir: Directory where the emitter published and archived artifacts.

    Returns:
        (words, write_id, writer, image_path, md5)
        - words: list of memory words (integers)
        - write_id: integer write ID
        - writer: writer name string
        - image_path: Path to the archived .npy image
        - md5: MD5 checksum of the archived .npy file

    Raises:
        FileNotFoundError: If the archived image does not exist.
    """
    pub = Path(publish_dir or os.environ.get("GEOS_IMAGE_DIR", "/tmp/geos_observation"))
    archive_dir = pub / "archive"
    img_path = archive_dir / f"kernel_memory.{write_id}.npy"
    meta_path = archive_dir / f"surface.meta.{write_id}.json"

    if not img_path.exists():
        raise FileNotFoundError(f"Archived image not found: {img_path}")

    arr = np.load(img_path)
    words = arr.astype(int).tolist()
    data = img_path.read_bytes()
    md5_hash = hashlib.md5(data).hexdigest()

    writer = "unattributed"
    if meta_path.exists():
        try:
            m = json.loads(meta_path.read_text())
            writer = m.get("writer", "unattributed")
        except Exception:
            pass

    return (words, write_id, writer, img_path, md5_hash)


# Documented aliases
load_write_archive = load_archived_write
load_write = load_archived_write
