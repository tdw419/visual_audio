#!/usr/bin/env python3
"""geos_emit.py — GH-26.2 APERTURE: the first agent write path.

NOT a raw memory write: a constrained intent API whose ONLY legal targets
are GH-18 mailbox windows {700..767} (E_APERTURE otherwise). GH-22 mailbox
word format enforced host-side. Scratch-copy + checksummed atomic commit —
a proven image is never mutated in place.

HUMAN GATE: refuses to run unless the repo-root `.geos_emit_ack` marker
(or GEOS_EMIT_ACK env) is present — demo_wc008_gui.sh governance pattern.

Intents (spec §26.2):
  post(box, op, payload)      encode GH-22 word, write at box's mailbox base
  clear(box | word)           zero a mailbox word
  claim_ticket(name)          op 0x30 post at word 754
  signal_done(box)            op 0x40 post at the box result word
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

import numpy as np

_REPO = Path(__file__).resolve().parent.parent

# APERTURE RULE (GH-18 ABI facts): BOX0 [700..717), BOX1 [718..735),
# BOX2 [736..768). The union is the entire legal write space.
APERTURE_LO, APERTURE_HI = 700, 767
BOX_BASE = {0: 700, 1: 718, 2: 736}
BOX_LIMIT = {0: 717, 1: 735, 2: 768}   # exclusive upper bounds
RESULT_WORD = 754                       # BOX2 result word (GH-18)
TICKET_WORD = 754
OP_POST, OP_CLEAR, OP_CLAIM, OP_DONE = 0x10, 0x20, 0x30, 0x40
ACK_SENTINEL = "GEOS_EMIT_ACK=1"
MAX_TICKET_NAME = 8                     # name packed into one payload byte
IMAGE_NAME = "kernel_memory.npy"
META_NAME = "surface.meta.json"


class EmitError(Exception):
    """Agent emission rejected. Message starts with an E_* code."""


def encode_mailbox_word(op: int, payload: int) -> int:
    """GH-22 mailbox word: cksum[31:24]=(op+payload)&0xFF | op[15:8] |
    payload[7:0]. Malformed operands rejected host-side."""
    if not (0 <= op <= 0xFF):
        raise EmitError(f"E_MALFORMED: op {op!r} outside byte range")
    if not (0 <= payload <= 0xFF):
        raise EmitError(f"E_MALFORMED: payload {payload!r} outside byte range")
    cksum = (op + payload) & 0xFF
    return (cksum << 24) | (op << 8) | payload


def _in_aperture(word: int) -> bool:
    return APERTURE_LO <= word <= APERTURE_HI


class GeosEmitter:
    """Agent write path onto the newest committed kernel-memory image.

    Writes land on a scratch copy; the mutated copy becomes the newest
    committed publish image only after a checksummed atomic rename.
    """

    def __init__(self, publish_dir: Optional[Path] = None,
                 ack_file: Optional[Path] = None,
                 image_dir: Optional[Path] = None,
                 registry_path: Optional[Union[Path, str]] = None,
                 origin_id: Optional[str] = None) -> None:
        self.publish_dir = Path(publish_dir or image_dir
                                or os.environ.get("GEOS_IMAGE_DIR",
                                                  "/tmp/geos_observation"))
        self.ack_file = Path(ack_file) if ack_file else _REPO / ".geos_emit_ack"
        if registry_path is not None:
            self.registry_path = Path(registry_path)
        elif "GEOS_REGISTRY_PATH" in os.environ:
            self.registry_path = Path(os.environ["GEOS_REGISTRY_PATH"])
        else:
            self.registry_path = Path("/tmp/glyph_spine_index.jsonl")
        self.origin_id = str(origin_id or os.environ.get("GEOS_ORIGIN_ID", str(self.publish_dir)))

    # ── human gate ───────────────────────────────────────────────────────

    def _ack_ok(self) -> bool:
        if os.environ.get("GEOS_EMIT_ACK", "").startswith("GEOS_EMIT_ACK"):
            return True
        return self.ack_file.exists()

    # ── image I/O ────────────────────────────────────────────────────────

    def _load_state(self) -> np.ndarray:
        exact = self.publish_dir / IMAGE_NAME
        if exact.exists():
            return np.load(exact)
        cands = sorted(self.publish_dir.glob("*.npy"),
                       key=lambda p: p.stat().st_mtime)
        if not cands:
            raise EmitError(f"E_NO_IMAGE: no committed image under "
                            f"{self.publish_dir}")
        return np.load(cands[-1])

    def _checksum_bytes(self, data: bytes) -> str:
        return hashlib.md5(data).hexdigest()

    def _commit(self, mem: np.ndarray,
                emit_meta: Dict[str, Any],
                writer: Optional[str] = None) -> Dict[str, Any]:
        """Scratch-copy → checksum → atomic rename. The publish image is
        either the old state or the fully verified new state, never torn.
        Also archives each write under <publish_dir>/archive/ for write identity."""
        if writer is None:
            writer = emit_meta.get("writer", "unattributed")
        if not writer or not isinstance(writer, str):
            writer = "unattributed"
        emit_meta["writer"] = writer

        self.publish_dir.mkdir(parents=True, exist_ok=True)
        scratch = self.publish_dir / (IMAGE_NAME + ".emit_scratch")
        with open(scratch, "wb") as fh:
            np.save(fh, mem)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            data = scratch.read_bytes()
            checksum = self._checksum_bytes(data)
            os.replace(scratch, self.publish_dir / IMAGE_NAME)
        except Exception:
            scratch.unlink(missing_ok=True)
            raise

        # Monotonically increasing write_id (DEFECT-20)
        meta_file = self.publish_dir / META_NAME
        last_write_id = 0
        if meta_file.exists():
            try:
                prev = json.loads(meta_file.read_text())
                last_write_id = int(prev.get("write_id", 0) or 0)
            except Exception:
                last_write_id = 0
        write_id = last_write_id + 1
        written_at = datetime.now(timezone.utc).isoformat()

        emit_meta["checksum"] = checksum
        emit_meta["word"] = emit_meta.get("word")
        meta = {
            "tick": int(mem[732]) + 1,
            "step": None,
            "source_md5": checksum,
            "canonical": True,
            "emit": emit_meta,
            "write_id": write_id,
            "writer": writer,
            "written_at": written_at,
            "bytes_len": len(data),
        }

        # Best-effort append to WriteRegistry (SPINE-R2-WIREIN)
        reg_path = emit_meta.get("registry_path") or getattr(self, "registry_path", None)
        if reg_path is None:
            reg_path = os.environ.get("GEOS_REGISTRY_PATH", "/tmp/glyph_spine_index.jsonl")
        reg_path = str(reg_path)

        orig_id = emit_meta.get("origin_id") or getattr(self, "origin_id", None)
        if not orig_id:
            orig_id = os.environ.get("GEOS_ORIGIN_ID") or str(self.publish_dir)
        orig_id = str(orig_id)

        try:
            from tools.geos_archive import ArchiveRecord
            from tools.geos_registry import WriteRegistry

            rec = ArchiveRecord(
                write_id=write_id,
                writer=writer,
                image_path=str(self.publish_dir / IMAGE_NAME),
                sidecar_path=str(self.publish_dir / META_NAME),
                bytes_len=len(data),
                written_at=written_at,
            )
            reg = WriteRegistry(index_path=reg_path)
            reg.register(rec, origin_id=orig_id)
        except Exception as exc:
            meta["unattributed"] = True
            meta["unattributed_reason"] = f"{type(exc).__name__}: {exc}"

        tmp_meta = self.publish_dir / (META_NAME + ".emit_scratch")
        tmp_meta.write_text(json.dumps(meta))
        os.replace(tmp_meta, self.publish_dir / META_NAME)

        # Per-write archive (DEFECT-20 fix (a))
        archive_dir = self.publish_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_img = archive_dir / f"kernel_memory.{write_id}.npy"
        archive_img_scratch = archive_dir / f"kernel_memory.{write_id}.npy.scratch"
        archive_img_scratch.write_bytes(data)
        os.replace(archive_img_scratch, archive_img)

        archive_meta = archive_dir / f"surface.meta.{write_id}.json"
        archive_meta_scratch = archive_dir / f"surface.meta.{write_id}.json.scratch"
        archive_meta_scratch.write_text(json.dumps(meta))
        os.replace(archive_meta_scratch, archive_meta)

        return {
            "committed": True,
            "word": emit_meta.get("word"),
            "checksum": checksum,
            "tick": meta["tick"],
            "write_id": write_id,
            "writer": writer,
            "written_at": written_at,
        }

    # ── intent dispatch ──────────────────────────────────────────────────

    def emit(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(intent, dict) or "kind" not in intent:
            raise EmitError("E_MALFORMED: intent must be a dict with 'kind'")
        if not self._ack_ok():
            raise EmitError(
                "E_ACK: emit is HUMAN-GATED — create .geos_emit_ack or set "
                "GEOS_EMIT_ACK env (demo_wc008 governance pattern)")
        kind = intent["kind"]
        if kind == "post":
            return self._post(intent)
        if kind == "clear":
            return self._clear(intent)
        if kind == "claim_ticket":
            return self._claim_ticket(intent)
        if kind == "signal_done":
            return self._signal_done(intent)
        raise EmitError(f"E_MALFORMED: unknown intent kind {kind!r}")

    def _resolve_target(self, intent: Dict[str, Any],
                        default_word: Optional[int]) -> int:
        word = intent.get("word", default_word)
        if not isinstance(word, int) or isinstance(word, bool):
            raise EmitError(f"E_MALFORMED: word {word!r} not an integer")
        if not _in_aperture(word):
            raise EmitError(
                f"E_APERTURE: word {word} outside legal mailbox window "
                f"[{APERTURE_LO}..{APERTURE_HI}]")
        return word

    def _require(self, intent: Dict[str, Any], *names: str) -> None:
        for n in names:
            if n not in intent:
                raise EmitError(f"E_MALFORMED: intent missing '{n}'")

    def _post(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        self._require(intent, "box", "op", "payload")
        box = intent["box"]
        if box not in BOX_BASE:
            raise EmitError(f"E_MALFORMED: box {box!r} not in "
                            f"{sorted(BOX_BASE)} (BOX0..BOX2)")
        word = self._resolve_target(intent, BOX_BASE[box])
        value = encode_mailbox_word(intent["op"], intent["payload"])
        mem = self._load_state()
        mem[word] = value & 0xFFFFFFFF
        emit_meta = {"kind": "post", "box": box, "word": word,
                     "op": intent["op"], "payload": intent["payload"]}
        return self._commit(mem, emit_meta, writer=intent.get("writer"))

    def _clear(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        if "box" in intent and "word" not in intent:
            box = intent["box"]
            if box not in BOX_BASE:
                raise EmitError(f"E_MALFORMED: box {box!r} not in "
                                f"{sorted(BOX_BASE)}")
            intent = dict(intent, word=BOX_BASE[box])
        self._require(intent, "word")
        word = self._resolve_target(intent, None)
        mem = self._load_state()
        mem[word] = 0
        return self._commit(mem, {"kind": "clear", "word": word},
                            writer=intent.get("writer"))

    def _claim_ticket(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        self._require(intent, "name")
        name = intent["name"]
        if not isinstance(name, str) or not (0 < len(name) <= MAX_TICKET_NAME):
            raise EmitError(f"E_MALFORMED: ticket name must be a string of "
                            f"1..{MAX_TICKET_NAME} chars")
        payload = sum(ord(c) & 0xFF for c in name) & 0xFF
        mem = self._load_state()
        mem[TICKET_WORD] = encode_mailbox_word(OP_CLAIM, payload)
        return self._commit(mem, {"kind": "claim_ticket", "name": name,
                                  "word": TICKET_WORD},
                            writer=intent.get("writer"))

    def _signal_done(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        self._require(intent, "box")
        box = intent["box"]
        if box not in BOX_BASE:
            raise EmitError(f"E_MALFORMED: box {box!r} not in "
                            f"{sorted(BOX_BASE)}")
        word = RESULT_WORD if box == 2 else BOX_BASE[box] + 16
        if not _in_aperture(word):
            raise EmitError(f"E_APERTURE: computed result word {word} "
                            f"outside mailbox window")
        mem = self._load_state()
        mem[word] = encode_mailbox_word(OP_DONE, 0)
        return self._commit(mem, {"kind": "signal_done", "box": box,
                                  "word": word},
                            writer=intent.get("writer"))

    # ── GH-26.3 EMIT→ADMIT: thin delegate, NO admission logic here ──────
    # Agent tile proposals route ONLY through autoatlas.emit_admit (IR
    # StaticVerifier → oracle word-exact → table stamp). The emitter has
    # no raw-word write surface and never touches the syscall table or
    # the tile rect itself — the oracle is the SOLE admission path.

    def emit_admit(self, runner, tile_text: str, sys_n: int, expected: int,
                   argv: Optional[Dict[int, int]] = None,
                   source: str = "template",
                   receipt_path: Optional[Path] = None):
        """Delegate the proposal to the autoatlas admission pipeline.

        The human gate applies BEFORE anything moves: emit_admit is an
        emit-path verb and refuses without .geos_emit_ack / GEOS_EMIT_ACK,
        exactly like every other intent."""
        if not self._ack_ok():
            raise EmitError(
                "E_ACK: emit_admit is HUMAN-GATED — create .geos_emit_ack "
                "or set GEOS_EMIT_ACK env (demo_wc008 governance pattern)")
        from tools.glyph_gpt.autoatlas import emit_admit as _admit
        return _admit(runner, tile_text, sys_n, expected, argv=argv,
                      source=source, receipt_path=receipt_path)

    def publish(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Publish intent: alias for emit(intent)."""
        return self.emit(intent)


def publish(intent: Dict[str, Any],
            publish_dir: Optional[Union[str, Path]] = None,
            ack_file: Optional[Union[str, Path]] = None,
            image_dir: Optional[Union[str, Path]] = None,
            registry_path: Optional[Union[str, Path]] = None,
            origin_id: Optional[str] = None) -> Dict[str, Any]:
    """Publish an intent via GeosEmitter."""
    emitter = GeosEmitter(
        publish_dir=Path(publish_dir) if publish_dir else None,
        ack_file=Path(ack_file) if ack_file else None,
        image_dir=Path(image_dir) if image_dir else None,
        registry_path=registry_path,
        origin_id=origin_id,
    )
    return emitter.emit(intent)


if __name__ == "__main__":
    import sys
    print("Usage: from tools.geos_emit import GeosEmitter; "
          "GeosEmitter().emit({...})  — see GH26 spec §26.2")
    sys.exit(2)
