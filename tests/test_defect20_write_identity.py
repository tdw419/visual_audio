"""DEFECT-20 gate: tests/test_defect20_write_identity.py.

Roadmap: DEFECT-20 publish-path write identity (witness attribution)
(systems/GLYPH_SELF_HOSTING_ROADMAP.md row DEFECT-20, source ticket
.builder_queue/DEFECT-20_snapshot_last_write_wins.md).

Legs:
  L1: monotonic identity — two consecutive publishes produce monotonically
      increasing write_ids (1 then 2), distinguishable artifacts, and the
      archive preserves earlier write state.
  L2: meta exposure — geos_surface_meta exposes write_id, writer, image_md5,
      sidecar_file for served image, and degrades gracefully with nulls
      when no sidecar exists.
  L3: loud attribution — take_witness returns witness attributes when write_id
      matches, and raises WitnessMismatch with WITNESS_MISMATCH and both IDs
      on mismatch.
  L4: per-stage attribution (BK-14 class) — multi-stage writes are attributable
      per stage by identity rather than inferred mtime.
  L5: launcher publish path identity — the BK-14 dual-channel flow (emitter stage
      then GlyphRunner.drive(publish_dir=...)) stays attributably agreeing: every
      artifact carries a unique write_id and a naming writer.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
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
    GeosEmitter, encode_mailbox_word, ACK_SENTINEL,
)
from tools.geos_observation_server import geos_surface_meta       # noqa: E402
from tools.geos_witness import (                                 # noqa: E402
    load_archived_write, take_witness, WitnessMismatch,
)

PUBLISH = "publish"


def _bake(tmp: Path) -> Path:
    out = tmp / "gh26.glyph.npy"
    preemptive_kernel_image(build_default_atlas(), timer_quantum=20,
                            out_path=out)
    return out


def _publish_dir(tmp: Path) -> Path:
    """Run the kernel once with publishing so a committed image exists.
    The launcher's own sidecars are then removed: `GeosEmitter` derives its
    `write_id` from the sidecars present in the dir, so leaving them would seed
    the counter (the emitter-path legs L1..L4 assert a counter starting at 1)."""
    img = _bake(tmp)
    pub = tmp / PUBLISH
    receipt = GlyphRunner(img, ram_words=16384).drive(
        publish_dir=pub, max_instructions=60000)
    assert receipt["halted"] and not receipt["faulted"], receipt
    for meta in pub.glob("*.meta.json"):
        meta.unlink()
    return pub


def _acked(tmp: Path) -> Path:
    """Create the ack marker (human-gate satisfied on disk)."""
    ack = tmp / ".geos_emit_ack"
    ack.write_text(ACK_SENTINEL + " — authorized by Jericho (gate fixture)")
    return ack


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# ── Leg 1: monotonic identity ──────────────────────────────────────────

def test_l1_monotonic_identity(tmp_path: Path):
    pub = _publish_dir(tmp_path)
    ack = _acked(tmp_path)
    em = GeosEmitter(publish_dir=pub, ack_file=ack)

    # Publish 1: word 750, writer "stage-a"
    rc1 = em.emit({"kind": "post", "box": 0, "op": 1, "payload": 2,
                   "word": 750, "writer": "stage-a"})
    assert rc1["committed"] is True
    meta1 = json.loads((pub / "surface.meta.json").read_text())
    assert meta1["write_id"] == 1
    assert meta1["writer"] == "stage-a"
    assert "written_at" in meta1

    # Publish 2: word 754, writer "stage-b"
    rc2 = em.emit({"kind": "post", "box": 0, "op": 1, "payload": 3,
                   "word": 754, "writer": "stage-b"})
    assert rc2["committed"] is True
    meta2 = json.loads((pub / "surface.meta.json").read_text())
    assert meta2["write_id"] == 2
    assert meta2["writer"] == "stage-b"
    assert "written_at" in meta2

    # The two artifacts are distinguishable
    assert meta1["write_id"] != meta2["write_id"]
    assert meta1["writer"] != meta2["writer"]
    assert meta1["source_md5"] != meta2["source_md5"]

    # Archive leg: after publish 2 the words written by publish 1 are STILL
    # retrievable and attributed to write_id 1
    archive_img_1 = pub / "archive" / "kernel_memory.1.npy"
    archive_meta_1 = pub / "archive" / "surface.meta.1.json"
    assert archive_img_1.exists(), "archive image for write_id 1 missing"
    assert archive_meta_1.exists(), "archive meta for write_id 1 missing"

    words1, wid1, writer1, img1, md51 = load_archived_write(1, pub)
    assert wid1 == 1
    assert writer1 == "stage-a"
    assert words1[750] == encode_mailbox_word(1, 2)
    assert img1 == archive_img_1
    assert md51 == _md5(archive_img_1)

    words2, wid2, writer2, img2, md52 = load_archived_write(2, pub)
    assert wid2 == 2
    assert writer2 == "stage-b"
    assert words2[754] == encode_mailbox_word(1, 3)
    assert img2 == (pub / "archive" / "kernel_memory.2.npy")
    assert md52 == _md5(pub / "archive" / "kernel_memory.2.npy")


# ── Leg 2: meta exposure ───────────────────────────────────────────────

def test_l2_meta_exposure(tmp_path: Path):
    pub = _publish_dir(tmp_path)
    ack = _acked(tmp_path)
    em = GeosEmitter(publish_dir=pub, ack_file=ack)
    em.emit({"kind": "post", "box": 0, "op": 1, "payload": 2,
             "word": 750, "writer": "stage-a"})
    em.emit({"kind": "post", "box": 0, "op": 1, "payload": 3,
             "word": 754, "writer": "stage-b"})

    saved_env = os.environ.get("GEOS_IMAGE_DIR")
    try:
        os.environ["GEOS_IMAGE_DIR"] = str(pub)
        raw_meta = geos_surface_meta()
        meta = json.loads(raw_meta)
        source = meta["source"]
        assert source["write_id"] == 2
        assert source["writer"] == "stage-b"
        assert source["sidecar_file"] is not None

        served_npy = pub / "kernel_memory.npy"
        expected_md5 = _md5(served_npy)
        assert source["image_md5"] is not None
        assert source["image_md5"] == expected_md5

        # Second dir holding a bare .npy and NO sidecar:
        # keys exist with null values and no exception
        bare_dir = tmp_path / "bare_dir"
        bare_dir.mkdir()
        bare_npy = bare_dir / "kernel_memory.npy"
        np.save(bare_npy, np.zeros(16384, dtype=np.uint32))

        os.environ["GEOS_IMAGE_DIR"] = str(bare_dir)
        bare_raw = geos_surface_meta()
        bare_meta = json.loads(bare_raw)
        bare_source = bare_meta["source"]
        assert bare_source["write_id"] is None
        assert bare_source["writer"] is None
        assert bare_source["written_at"] is None
        assert bare_source["sidecar_file"] is None
        assert bare_source["image_md5"] is None
    finally:
        if saved_env is not None:
            os.environ["GEOS_IMAGE_DIR"] = saved_env
        else:
            os.environ.pop("GEOS_IMAGE_DIR", None)


# ── Leg 3: loud attribution ────────────────────────────────────────────

def test_l3_loud_attribution(tmp_path: Path):
    pub = _publish_dir(tmp_path)
    ack = _acked(tmp_path)
    em = GeosEmitter(publish_dir=pub, ack_file=ack)

    saved_env = os.environ.get("GEOS_IMAGE_DIR")
    try:
        os.environ["GEOS_IMAGE_DIR"] = str(pub)

        # Write 1: word 750, writer "stage-a"
        em.emit({"kind": "post", "box": 0, "op": 1, "payload": 2,
                 "word": 750, "writer": "stage-a"})

        # While write 1 is current, take_witness(750, expect_write_id=1)
        # returns write_id 1 with its value
        w1 = take_witness(750, expect_write_id=1)
        assert w1["write_id"] == 1
        assert w1["writer"] == "stage-a"
        assert w1["word"] == 750
        assert w1["value"] == encode_mailbox_word(1, 2)
        assert w1["image_file"] == "kernel_memory.npy"
        assert w1["sidecar_file"] == "surface.meta.json"
        assert w1["image_md5"] == _md5(pub / "kernel_memory.npy")

        # After a further publish (write 2)
        em.emit({"kind": "post", "box": 0, "op": 1, "payload": 3,
                 "word": 754, "writer": "stage-b"})

        # take_witness(750, expect_write_id=1) raises WitnessMismatch
        # whose message contains WITNESS_MISMATCH and both ids
        with pytest.raises(WitnessMismatch) as exc_info:
            take_witness(750, expect_write_id=1)
        err_msg = str(exc_info.value)
        assert "WITNESS_MISMATCH" in err_msg
        assert "2" in err_msg
        assert "1" in err_msg

        # take_witness(750, expect_write_id=2) returns write_id 2
        w2 = take_witness(750, expect_write_id=2)
        assert w2["write_id"] == 2
        assert w2["writer"] == "stage-b"
    finally:
        if saved_env is not None:
            os.environ["GEOS_IMAGE_DIR"] = saved_env
        else:
            os.environ.pop("GEOS_IMAGE_DIR", None)


# ── Leg 4: per-stage attribution (BK-14 class) ─────────────────────────

def test_l4_per_stage_attribution(tmp_path: Path):
    pub = _publish_dir(tmp_path)
    ack = _acked(tmp_path)
    em = GeosEmitter(publish_dir=pub, ack_file=ack)

    saved_env = os.environ.get("GEOS_IMAGE_DIR")
    try:
        os.environ["GEOS_IMAGE_DIR"] = str(pub)

        # Stage 1: stage-a writes word 750
        val_a = encode_mailbox_word(0x11, 0x42)
        em.emit({"kind": "post", "box": 0, "op": 0x11, "payload": 0x42,
                 "word": 750, "writer": "stage-a"})

        # Stage 2: stage-b writes word 754 and rewrites word 750 for unrelated purpose
        val_b_750 = encode_mailbox_word(0x22, 0x99)
        em.emit({"kind": "post", "box": 0, "op": 0x22, "payload": 0x99,
                 "word": 750, "writer": "stage-b"})

        # Served meta names stage-b as last writer (write_id 2)
        raw_meta = geos_surface_meta()
        meta = json.loads(raw_meta)
        assert meta["source"]["writer"] == "stage-b"
        assert meta["source"]["write_id"] == 2

        # A witness expecting stage-a's write (write_id 1) fails loudly
        with pytest.raises(WitnessMismatch, match="WITNESS_MISMATCH"):
            take_witness(750, expect_write_id=1)

        # Stage-a's word 750 value is named as write_id 1 via archived write
        words_1, wid_1, writer_1, _, _ = load_archived_write(1, pub)
        assert wid_1 == 1
        assert writer_1 == "stage-a"
        assert words_1[750] == val_a

        # Stage-b's word 750 value is named as write_id 2
        words_2, wid_2, writer_2, _, _ = load_archived_write(2, pub)
        assert wid_2 == 2
        assert writer_2 == "stage-b"
        assert words_2[750] == val_b_750

        # Disagreement is attributable per stage by IDENTITY, not inferred from mtime
        assert words_1[750] != words_2[750]
        assert writer_1 != writer_2
    finally:
        if saved_env is not None:
            os.environ["GEOS_IMAGE_DIR"] = saved_env
        else:
            os.environ.pop("GEOS_IMAGE_DIR", None)


# ── Leg 5: launcher publish path identity (BK-14 dual channel) ─────────

def test_l5_runner_path_identity(tmp_path: Path):
    """Emitter stage + launcher stage into ONE publish dir (the BK-14 flow)."""
    pub = tmp_path / PUBLISH
    pub.mkdir(parents=True, exist_ok=True)
    # glass_box_demo stage-0 seed: a bare image, no sidecar
    np.save(pub / "kernel_memory.npy", np.zeros(16384, dtype=np.uint32))
    em = GeosEmitter(publish_dir=pub, ack_file=_acked(tmp_path))

    # stage-a: the emitter writes word 750 → write_id 1
    rc1 = em.emit({"kind": "post", "box": 0, "op": 1, "payload": 2,
                   "word": 750, "writer": "stage-a"})
    assert rc1["write_id"] == 1 and rc1["writer"] == "stage-a"
    seed_meta = json.loads((pub / "surface.meta.json").read_text())
    assert seed_meta["write_id"] == 1 and seed_meta["writer"] == "stage-a"

    # stage-b: the launcher drives and publishes into the SAME dir
    receipt = GlyphRunner(_bake(tmp_path), ram_words=16384).drive(
        publish_dir=pub, max_instructions=60000)
    assert receipt["halted"] and not receipt["faulted"], receipt

    canon = json.loads((pub / "surface.meta.json").read_text())
    assert canon["writer"] == "canonical"
    assert canon["write_id"] > 1, canon

    tagged = sorted(pub.glob("kernel_memory_tick*.meta.json"))
    assert tagged, "expected per-tick sidecars from the launcher publish path"
    tagged_metas = [json.loads(t.read_text()) for t in tagged]
    assert all(m["write_id"] > 1 and m["writer"].startswith("tick")
               for m in tagged_metas), tagged_metas[:2]
    assert canon["write_id"] > max(m["write_id"] for m in tagged_metas)

    # attributably agreeing: every TOP-LEVEL artifact names a UNIQUE write — the
    # emitter's write 1 no longer has a top-level sidecar (the launcher's canonical
    # publish replaced it), so it survives only in the archive checked below.
    ids = [json.loads(s.read_text())["write_id"] for s in pub.glob("*.meta.json")]
    assert len(ids) == len(set(ids)) and min(ids) >= 2, sorted(ids)

    saved_env = os.environ.get("GEOS_IMAGE_DIR")
    try:
        os.environ["GEOS_IMAGE_DIR"] = str(pub)
        source = json.loads(geos_surface_meta())["source"]
        assert source["write_id"] == canon["write_id"]
        assert source["writer"] == "canonical"
        # stage-a's write is no longer the served snapshot — and it says so
        with pytest.raises(WitnessMismatch, match="WITNESS_MISMATCH"):
            take_witness(750, expect_write_id=1)
        served = take_witness(750, expect_write_id=canon["write_id"])
        assert served["writer"] == "canonical"
    finally:
        if saved_env is not None:
            os.environ["GEOS_IMAGE_DIR"] = saved_env
        else:
            os.environ.pop("GEOS_IMAGE_DIR", None)

    # stage-a's bytes survive the launcher publish and stay attributed to write 1
    words1, wid1, writer1, _, _ = load_archived_write(1, pub)
    assert (wid1, writer1) == (1, "stage-a")
    assert words1[750] == encode_mailbox_word(1, 2)
