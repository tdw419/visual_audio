"""RED-first gate for the agent maildrop (tools/geos_maildrop.py).

Contract under test (RULING-style, four legs, each discriminating):

  L1 round-trip+attribution : post() from a named agent -> read() returns the
                              message with the RIGHT writer and matching sha256.
  L2 tamper-evidence        : flip one byte in the content file -> read() reports
                              TAMPER (rc != 0). A read that cannot fail is not a
                              verification.
  L3 human gate             : with no .geos_emit_ack and no GEOS_EMIT_ACK env,
                              post() refuses (E_ACK). The refusal path must be
                              live, not documented.
  L4 byte-band identity     : the mailbox word decodes back to (op, payload)
                              exactly, checksum included.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools import geos_maildrop as M  # noqa: E402


@pytest.fixture()
def drop(tmp_path, monkeypatch):
    """Isolated maildrop; emit gate OPEN via the sanctioned env bypass
    (the repo's .geos_emit_ack must not leak into test expectations —
    L3 proves the refusal path separately)."""
    monkeypatch.setenv("GEOS_EMIT_ACK", "GEOS_EMIT_ACK")
    return M.Maildrop(
        publish_dir=tmp_path / "maildrop",
        registry_path=tmp_path / "index.jsonl",
        ack_file=tmp_path / "no_such_ack",
    )


def test_l1_round_trip_attribution(drop):
    """L1: post -> read gives back writer, kind, and byte-exact content."""
    msg = drop.post(sender="hermes", recipient="claude",
                    kind="ruling", text="run syscall: default-deny allowlist")
    got = drop.read(recipient="claude")
    assert len(got) == 1, f"expected exactly one message, got {len(got)}"
    m = got[0]
    assert m["sender"] == "hermes" and m["recipient"] == "claude"
    assert m["kind"] == "ruling"
    assert m["text"] == "run syscall: default-deny allowlist"
    assert m["verified"] is True, "sha256 must match on a clean read"
    assert msg["write_id"] >= 1 and msg["writer"] == "hermes"


def test_l2_tamper_detected(drop):
    """L2: one flipped byte in the content file must turn the read RED."""
    drop.post(sender="glyphgpt", recipient="all", kind="claim", text="tile ok")
    got = drop.read(recipient="all")
    path = Path(got[0]["content_path"])
    data = bytearray(path.read_bytes())
    data[0] ^= 0x01
    path.write_bytes(bytes(data))
    got2 = drop.read(recipient="all")
    assert got2[0]["verified"] is False, "tampered content must fail the hash"
    rc = M.verify_all(drop, recipient="all")
    assert rc != 0, "verify_all must exit non-zero when anything fails"


def test_l3_human_gate_refuses(tmp_path, monkeypatch):
    """L3: no ack -> post refuses with E_ACK (the gate is LIVE)."""
    monkeypatch.delenv("GEOS_EMIT_ACK", raising=False)
    drop = M.Maildrop(publish_dir=tmp_path / "md",
                      registry_path=tmp_path / "idx.jsonl",
                      ack_file=tmp_path / "absent_ack")
    with pytest.raises((M.MaildropRefused, M.EmitError)) as exc:
        drop.post(sender="hermes", recipient="claude", kind="receipt",
                  text="should not land")
    assert "E_ACK" in str(exc.value)
    # ...and nothing landed: no content file, no archive write.
    assert list((tmp_path / "md" / "content").glob("*")) == []


def test_l4_byte_band_word_identity(drop):
    """L4: the word IN COMMITTED MEMORY at the receipt's address decodes to
    exactly (op, payload) with a good checksum — read from the .npy image,
    not from the API's echo of the address."""
    msg = drop.post(sender="claude", recipient="glyphgpt",
                    kind="handoff", text="x")
    raw = M.read_signal_word(drop.publish_dir, msg["word"])
    op, payload, cksum = M.decode_mailbox_word(raw)
    assert op == M.OP_MAILDROP and payload == (msg["seq"] & 0xFF)
    assert cksum == (op + payload) & 0xFF


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:randomly"]))
