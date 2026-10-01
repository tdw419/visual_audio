"""geos_maildrop.py — inter-agent message drop on the glyph spatial substrate.

Design (ruled 2026-09-13, "Go" from Jericho):

  The mailbox POST is the ON-SUBSTRATE SIGNAL: it rides the existing
  GeosEmitter path, so every message lands as a real, human-gated,
  checksummed, atomically-committed spatial write with a DEFECT-20 write_id
  and a WriteRegistry attribution row. The CONTENT lives in a repo file
  (.geos/maildrop/); its sha256 is recorded in the post sidecar and verified
  on read — tamper-evident by construction. The control plane (briefs,
  rulings, code) stays on files/git; the maildrop carries decision receipts,
  not chatter.

  Attribution model: sender names the agent ("hermes" | "claude" | "glyphgpt"),
  written as the emit `writer`, so the registry index answers "who asserted
  this, when, on what write identity" without inference.

Conventions:
  BOX1 (718..735) is the maildrop signal window; op 0x50 = OP_MAILDROP.
  Payload byte = per-sender sequence number (wraps at 256 — the registry
  write_id is the true ordering; the payload is a liveness signal).

  Human gate: identical to the emitter — .geos_emit_ack or GEOS_EMIT_ACK.
  Refusal shape: MaildropRefused("E_ACK: ...") — never silent.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.geos_emit import EmitError, GeosEmitter, encode_mailbox_word  # noqa: E402

OP_MAILDROP = 0x50            # maildrop signal op (0x10/0x20/0x30/0x40 taken)
BOX_SIGNAL = 1                # BOX1 [718..735) — maildrop window
_DEFAULT_DROP = _REPO / ".geos" / "maildrop"
_ACK_FILE = _REPO / ".geos_emit_ack"
_KNOWN_AGENTS = ("hermes", "claude", "glyphgpt", "jericho")

_VALID_KINDS = ("ruling", "claim", "receipt", "handoff", "brief", "status")


class MaildropRefused(Exception):
    """Raised when the human gate (or validation) refuses a post."""


def decode_mailbox_word(word: int) -> tuple[int, int, int]:
    """Inverse of the GH-22 word format: -> (op, payload, checksum)."""
    op = (word >> 8) & 0xFF
    payload = word & 0xFF
    cksum = (word >> 24) & 0xFF
    if cksum != (op + payload) & 0xFF:
        raise ValueError(f"E_CKSUM: word {word:#x} fails its own checksum")
    return op, payload, cksum


def read_signal_word(publish_dir: Path, address: int) -> int:
    """Read the committed memory word at `address` — the substrate truth,
    not the receipt's echo of it."""
    import numpy as np
    mem = np.load(Path(publish_dir) / "kernel_memory.npy")
    return int(mem[address])


@dataclass
class Maildrop:
    publish_dir: Path
    registry_path: Path
    ack_file: Optional[Path] = None  # None -> repo default (.geos_emit_ack)

    def __post_init__(self) -> None:
        self.publish_dir = Path(self.publish_dir)
        self.registry_path = Path(self.registry_path)
        self.content_dir = self.publish_dir / "content"
        self.content_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_base_image()

    def _ensure_base_image(self) -> None:
        """The emitter commits onto a kernel image; seed a zeroed one if the
        maildrop's publish dir has none (isolated drops start from zero state,
        exactly like a freshly-observed kernel before its first agent write)."""
        image = self.publish_dir / "kernel_memory.npy"
        if not image.exists():
            import numpy as np
            self.publish_dir.mkdir(parents=True, exist_ok=True)
            np.save(image, np.zeros(1000, dtype=np.uint32))

    # ── post ─────────────────────────────────────────────────────────────

    def post(self, sender: str, recipient: str, kind: str,
             text: str, *, registry_path: Optional[Path] = None) -> Dict[str, Any]:
        """Post one message: content file + sha256, then the substrate signal.

        Returns the emit receipt (write_id, writer, word, content_path, sha256).
        """
        if sender not in _KNOWN_AGENTS:
            raise MaildropRefused(
                f"E_SENDER: {sender!r} not among {_KNOWN_AGENTS} — "
                "attribution is the whole point; no anonymous posts")
        if kind not in _VALID_KINDS:
            raise MaildropRefused(
                f"E_KIND: {kind!r} not among {_VALID_KINDS}")
        if not text or not isinstance(text, str):
            raise MaildropRefused("E_MALFORMED: text must be a non-empty string")

        # Seq per sender, from the registry's own count (no separate state).
        seq = self._count(sender)

        content_rel = f"{sender}.{seq:04d}.{kind}.md"
        content_path = self.content_dir / content_rel
        body = (f"from: {sender}\nto: {recipient}\nkind: {kind}\n\n{text}\n")
        digest = hashlib.sha256(body.encode()).hexdigest()

        # Signal FIRST (it can refuse); content only lands once accepted.
        emitter = GeosEmitter(
            publish_dir=self.publish_dir,
            registry_path=self.registry_path,
            origin_id=f"maildrop:{sender}",
            ack_file=self.ack_file,
        )
        receipt = emitter.emit({
            "kind": "post",
            "box": BOX_SIGNAL,
            "op": OP_MAILDROP,
            "payload": seq & 0xFF,
            "writer": sender,
        })
        content_path.write_text(body)

        # Stamp the message envelope onto BOTH sidecars: the live surface.meta.json
        # (latest write) and the immutable per-write archive copy — the archive
        # copies are what reads recover envelopes from, so enriching only the
        # live sidecar would orphan every message but the newest.
        envelope = {
            "sender": sender, "recipient": recipient, "kind": kind,
            "content": str(content_path), "sha256": digest, "seq": seq,
        }
        for meta_path in (
            self.publish_dir / "surface.meta.json",
            self.publish_dir / "archive" / f"surface.meta.{receipt.get('write_id')}.json",
        ):
            try:
                meta = json.loads(meta_path.read_text())
                meta["maildrop"] = envelope
                tmp = meta_path.with_suffix(".json.scratch")
                tmp.write_text(json.dumps(meta))
                os.replace(tmp, meta_path)
            except Exception:
                pass  # signal already landed; envelope stamping is best-effort

        return {
            "write_id": receipt.get("write_id"),
            "writer": sender,
            "seq": seq,
            "word": receipt.get("word"),
            "content_path": str(content_path),
            "sha256": digest,
        }

    # ── read ─────────────────────────────────────────────────────────────

    def read(self, recipient: str, sender: Optional[str] = None) -> List[Dict[str, Any]]:
        """Read messages addressed to `recipient`, hash-verified. Never raises."""
        out: List[Dict[str, Any]] = []
        for p in sorted(self.content_dir.glob("*.md")):
            meta = self._meta_for(p)
            if meta is None:
                continue
            if meta.get("recipient") != recipient:
                continue
            if sender is not None and meta.get("sender") != sender:
                continue
            body = p.read_bytes()
            verified = hashlib.sha256(body).hexdigest() == meta.get("sha256")
            out.append({
                "sender": meta.get("sender"),
                "recipient": meta.get("recipient"),
                "kind": meta.get("kind"),
                "text": body.decode(errors="replace").split("\n\n", 1)[-1].rstrip("\n"),
                "content_path": str(p),
                "sha256": meta.get("sha256"),
                "verified": verified,
                "write_id": meta.get("write_id"),
            })
        return out

    # ── internals ────────────────────────────────────────────────────────

    def _count(self, sender: str) -> int:
        return len(list(self.content_dir.glob(f"{sender}.*.md")))

    def _meta_for(self, content_path: Path) -> Optional[Dict[str, Any]]:
        """Recover the envelope for a content file from the per-write archive
        sidecars (archive/surface.meta.{write_id}.json). The live
        surface.meta.json only reflects the LATEST write, so it cannot be the
        source of truth for a multi-message drop."""
        archive_dir = self.publish_dir / "archive"
        candidates = sorted(archive_dir.glob("surface.meta.*.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        for meta_path in candidates:
            try:
                meta = json.loads(meta_path.read_text())
            except Exception:
                continue
            md = meta.get("maildrop") or {}
            if md.get("content") == str(content_path):
                md["write_id"] = meta.get("write_id")
                return md
        return None


def verify_all(drop: Maildrop, recipient: str) -> int:
    """Verify every message for `recipient`. rc 0 = all verified, 1 = tamper."""
    bad = [m for m in drop.read(recipient=recipient) if not m["verified"]]
    return 1 if bad else 0


if __name__ == "__main__":
    print("usage: from tools.geos_maildrop import Maildrop; see tests/test_maildrop.py")
    sys.exit(2)
