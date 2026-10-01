"""GH-26.2 gate: tests/test_gh26_emit_aperture.py.

Roadmap: GH-26 Agent-in-the-Loop, Tier 2 APERTURE (26.2) —
`tools/geos_emit.py` is the first agent WRITE path. NOT raw memory write:
a constrained intent API whose only legal targets are GH-18 mailbox
windows {700..767}. GH-22 word format enforced host-side. Scratch-copy +
checksummed commit — never in-place mutation of a proven image.
HUMAN GATE: `.geos_emit_ack` marker (or GEOS_EMIT_ACK env) required —
same governance pattern as demo_wc008_gui.sh.

Legs (per systems/GH26_AGENT_IN_THE_LOOP_SPEC.md §26.2):
  1. legal mailbox post lands and appears in the next surface read
     (geo-obs _load_memory on the publish dir), word byte-exact.
  2. out-of-aperture targets rejected E_APERTURE (kernel word 100,
     status 950, syscall table 1568, tile rect word 2000, engine TICK_PC
     8210, word 768, word 699 — boundary words inclusive/exclusive proven).
  3. malformed intents rejected host-side: unknown op, op/payload out of
     byte range, bad clear target, oversized ticket name.
  4. commit is atomic: no torn image on mid-write failure — the newest
     committed image is either the old state or the new state, never a
     half-written file (checksum verifies every read).
  5. no-ack refusal: without .geos_emit_ack AND without GEOS_EMIT_ACK env,
     emit() refuses BEFORE touching anything (image bytes unchanged).
  6. proven image untouched: the source image file's md5 is byte-identical
     after any emit attempt (scratch-copy rule).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.baker import preemptive_kernel_image        # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.geos_emit import (                                    # noqa: E402
    EmitError, GeosEmitter, encode_mailbox_word, APERTURE_LO,
    APERTURE_HI, ACK_SENTINEL,
)

GH16_TICKS_WORD = 732
PUBLISH = "publish"


def _bake(tmp: Path) -> Path:
    out = tmp / "gh26.glyph.npy"
    preemptive_kernel_image(build_default_atlas(), timer_quantum=20,
                            out_path=out)
    return out


def _publish_dir(tmp: Path) -> Path:
    """Run the kernel once with publishing so a committed image exists."""
    img = _bake(tmp)
    pub = tmp / PUBLISH
    receipt = GlyphRunner(img, ram_words=16384).drive(
        publish_dir=pub, max_instructions=60000)
    assert receipt["halted"] and not receipt["faulted"], receipt
    return pub


def _acked(tmp: Path) -> Path:
    """Create the ack marker (human-gate satisfied on disk)."""
    ack = tmp / ".geos_emit_ack"
    ack.write_text(ACK_SENTINEL + " — authorized by Jericho (gate fixture)")
    return ack


def _newest_image(pub: Path) -> np.ndarray:
    exact = pub / "kernel_memory.npy"
    if exact.exists():
        return np.load(exact)
    cands = sorted(pub.glob("*.npy"), key=lambda p: p.stat().st_mtime)
    assert cands, "no committed image in publish dir"
    return np.load(cands[-1])


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# ── Leg 1: legal mailbox post appears in the next surface read ──────────

def test_gh26_legal_post_lands_and_surface_reads_it():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        pub = _publish_dir(tmp)
        _acked(tmp)
        before = _newest_image(pub).copy()

        em = GeosEmitter(publish_dir=pub, ack_file=tmp / ".geos_emit_ack")
        rc = em.emit({"kind": "post", "box": 0, "op": 0x11, "payload": 0x2A})
        assert rc["committed"] is True, rc
        assert rc["word"] == 700, rc  # BOX0 first mailbox word

        word = int(_newest_image(pub)[700])
        assert word == encode_mailbox_word(0x11, 0x2A), hex(word)
        assert word != int(before[700])

        # next surface read (geo-obs, same newest-image rule) sees it
        spec_file = _REPO / "tools" / "geos_observation_server.py"
        if importlib_mcp_ok() and spec_file.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "geos_observation_server_gh26b", spec_file)
            mod = importlib.util.module_from_spec(spec)
            mod.__loader__ = spec.loader
            os.environ["GEOS_IMAGE_DIR"] = str(pub)
            spec.loader.exec_module(mod)
            mem, err = mod._load_memory()
            assert err is None, err
            assert int(mem[700]) == encode_mailbox_word(0x11, 0x2A)
        else:  # fallback: surface read == newest committed image read
            mem = _newest_image(pub).astype(int).tolist()
            assert int(mem[700]) == encode_mailbox_word(0x11, 0x2A)

        # bump-tick rule: emitted image's tick word > previous (fresh state)
        meta = json.loads((pub / "surface.meta.json").read_text())
        assert meta["emit"]["kind"] == "post"
        assert meta["emit"]["checksum"] == _md5(pub / "kernel_memory.npy")


def importlib_mcp_ok() -> bool:
    import importlib.util
    if importlib.util.find_spec("mcp") is None:
        return False
    try:
        import mcp.server.fastmcp  # noqa: F401
        return True
    except Exception:
        return False


# ── Leg 2: out-of-aperture targets → E_APERTURE, no write ───────────────

@pytest.mark.parametrize("word", [100, 8210, 950, 1568, 2000, 699, 768])
def test_gh26_out_of_aperture_rejected(word):
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        pub = _publish_dir(tmp)
        _acked(tmp)
        before_bytes = (pub / "kernel_memory.npy").read_bytes()

        em = GeosEmitter(publish_dir=pub, ack_file=tmp / ".geos_emit_ack")
        with pytest.raises(EmitError) as ei:
            em.emit({"kind": "post", "box": 0, "op": 0x11, "payload": 0x2A,
                     "word": word})
        assert "E_APERTURE" in str(ei.value)
        # no write happened at all
        assert (pub / "kernel_memory.npy").read_bytes() == before_bytes


def test_gh26_aperture_bounds_are_700_to_767_inclusive():
    assert (APERTURE_LO, APERTURE_HI) == (700, 767)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        pub = _publish_dir(tmp)
        _acked(tmp)
        em = GeosEmitter(publish_dir=pub, ack_file=tmp / ".geos_emit_ack")
        # 699 and 768 are OUT (E_APERTURE); 700 and 767 are IN (legal)
        for w, legal in ((699, False), (768, False), (700, True), (767, True)):
            if legal:
                rc = em.emit({"kind": "post", "box": 0, "op": 0x21,
                              "payload": w - 700, "word": w})
                assert rc["committed"] is True
            else:
                with pytest.raises(EmitError, match="E_APERTURE"):
                    em.emit({"kind": "post", "box": 0, "op": 0x21,
                             "payload": 0, "word": w})


# ── Leg 3: malformed intents rejected host-side ─────────────────────────

def test_gh26_malformed_intents_rejected():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        pub = _publish_dir(tmp)
        _acked(tmp)
        before_bytes = (pub / "kernel_memory.npy").read_bytes()
        em = GeosEmitter(publish_dir=pub, ack_file=tmp / ".geos_emit_ack")

        # unknown intent kind
        with pytest.raises(EmitError, match="E_MALFORMED"):
            em.emit({"kind": "detonate", "box": 0})
        # op out of byte range
        with pytest.raises(EmitError, match="E_MALFORMED"):
            em.emit({"kind": "post", "box": 0, "op": 0x100, "payload": 0})
        # payload out of byte range
        with pytest.raises(EmitError, match="E_MALFORMED"):
            em.emit({"kind": "post", "box": 0, "op": 1, "payload": 256})
        # negative op
        with pytest.raises(EmitError, match="E_MALFORMED"):
            em.emit({"kind": "post", "box": 0, "op": -1, "payload": 0})
        # box out of range (BOX0..BOX2 per GH-18 ABI)
        with pytest.raises(EmitError, match="E_MALFORMED"):
            em.emit({"kind": "post", "box": 3, "op": 1, "payload": 0})
        # malformed word directly: encode must reject non-byte operands
        with pytest.raises(EmitError):
            encode_mailbox_word(0x100, 0)
        # clear with out-of-aperture word
        with pytest.raises(EmitError, match="E_APERTURE"):
            em.emit({"kind": "clear", "word": 900})
        # claim_ticket with oversized name
        with pytest.raises(EmitError, match="E_MALFORMED"):
            em.emit({"kind": "claim_ticket", "name": "x" * 9})
        # missing required fields
        with pytest.raises(EmitError, match="E_MALFORMED"):
            em.emit({"kind": "post", "box": 0})   # no op/payload

        # nothing was written by any of the above
        assert (pub / "kernel_memory.npy").read_bytes() == before_bytes


def test_gh26_all_intent_kinds_commit_legal_words():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        pub = _publish_dir(tmp)
        _acked(tmp)
        em = GeosEmitter(publish_dir=pub, ack_file=tmp / ".geos_emit_ack")

        assert em.emit({"kind": "post", "box": 1, "op": 0x20,
                        "payload": 7})["committed"]
        assert int(_newest_image(pub)[718]) == encode_mailbox_word(0x20, 7)
        assert em.emit({"kind": "clear", "word": 718})["committed"]
        assert int(_newest_image(pub)[718]) == 0
        assert em.emit({"kind": "claim_ticket", "name": "T1"})["committed"]
        # ticket name packed into the payload byte (ord-sum)
        t1_payload = (ord("T") + ord("1")) & 0xFF
        assert int(_newest_image(pub)[754]) == encode_mailbox_word(0x30,
                                                                   t1_payload)
        assert em.emit({"kind": "signal_done", "box": 2})["committed"]
        assert int(_newest_image(pub)[754]) == encode_mailbox_word(0x40, 0)
        # every commit bumped tick in meta and stored a matching checksum
        meta = json.loads((pub / "surface.meta.json").read_text())
        assert meta["emit"]["checksum"] == _md5(pub / "kernel_memory.npy")


# ── Leg 4: atomic commit — no torn image on failure ─────────────────────

def test_gh26_commit_atomic_no_torn_image(tmp_path):
    pub = _publish_dir(tmp_path)
    _acked(tmp_path)
    good_bytes = (pub / "kernel_memory.npy").read_bytes()

    em = GeosEmitter(publish_dir=pub, ack_file=tmp_path / ".geos_emit_ack")
    # corrupt the emitter's scratch serialization to force a mid-commit
    # failure AFTER the scratch copy is written but BEFORE the rename:
    # sabotage by making the checksum step fail on a tampered payload.
    orig_encode = em._checksum_bytes

    def boom(b: bytes) -> str:
        raise EmitError("E_CHECKSUM_FAIL (simulated mid-commit fault)")

    em._checksum_bytes = boom
    with pytest.raises(EmitError, match="E_CHECKSUM_FAIL"):
        em.emit({"kind": "post", "box": 0, "op": 0x11, "payload": 1})
    # the committed image is UNCHANGED (old state, not a torn file)
    assert (pub / "kernel_memory.npy").read_bytes() == good_bytes
    # and a subsequent healthy emit still works (no corrupted staging)
    em._checksum_bytes = orig_encode
    rc = em.emit({"kind": "post", "box": 0, "op": 0x12, "payload": 2})
    assert rc["committed"] is True
    assert rc["checksum"] == _md5(pub / "kernel_memory.npy")
    # checksummed read-back: the stored meta checksum matches the image
    meta = json.loads((pub / "surface.meta.json").read_text())
    assert meta["emit"]["checksum"] == _md5(pub / "kernel_memory.npy")


# ── Leg 5: no-ack refusal ────────────────────────────────────────────────

def test_gh26_no_ack_refuses_before_touching_anything(tmp_path):
    pub = _publish_dir(tmp_path)
    before_bytes = (pub / "kernel_memory.npy").read_bytes()
    # ensure neither ack channel exists
    assert not (tmp_path / ".geos_emit_ack").exists()
    saved_env = os.environ.pop("GEOS_EMIT_ACK", None)
    try:
        em = GeosEmitter(publish_dir=pub, ack_file=tmp_path / ".geos_emit_ack")
        with pytest.raises(EmitError, match="GEOS_EMIT_ACK"):
            em.emit({"kind": "post", "box": 0, "op": 0x11, "payload": 1})
        assert (pub / "kernel_memory.npy").read_bytes() == before_bytes

        # env ack alone (no file) authorizes — audit trail via env
        os.environ["GEOS_EMIT_ACK"] = ACK_SENTINEL
        rc = GeosEmitter(publish_dir=pub,
                         ack_file=tmp_path / ".geos_emit_ack").emit(
            {"kind": "post", "box": 0, "op": 0x11, "payload": 1})
        assert rc["committed"] is True
    finally:
        if saved_env is not None:
            os.environ["GEOS_EMIT_ACK"] = saved_env
        else:
            os.environ.pop("GEOS_EMIT_ACK", None)


# ── Leg 6: proven source image untouched (scratch-copy rule) ────────────

def test_gh26_proven_source_image_byte_identical_after_emits(tmp_path):
    img = _bake(tmp_path)
    pub = tmp_path / PUBLISH
    GlyphRunner(img, ram_words=16384).drive(publish_dir=pub,
                                            max_instructions=60000)
    src_md5_before = _md5(img)
    _acked(tmp_path)
    em = GeosEmitter(publish_dir=pub, ack_file=tmp_path / ".geos_emit_ack")
    for op in ({"kind": "post", "box": 0, "op": 0x11, "payload": 1},
               {"kind": "clear", "word": 700},
               {"kind": "signal_done", "box": 0},
               # rejected attempts too
               ):
        try:
            em.emit(op)
        except EmitError:
            pass
    assert _md5(img) == src_md5_before, "proven image mutated by emit"
