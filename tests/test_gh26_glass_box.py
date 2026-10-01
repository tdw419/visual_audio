"""tests/test_gh26_glass_box.py — GH-26.5 Glass Box Integration Gate.

Spec: systems/GH26_AGENT_IN_THE_LOOP_SPEC.md section 26.5
Gate: All scenario phases verified:
  - Step 0: Frame geometry self-attestation via verify_reference_pixels()
  - Step 1: Session posts intent (@750) -> surface canvas shows '>'
  - Step 2: Preemptive execution by resident daemon -> tick advances, result @ 754 ('@')
  - Step 3: Session proposes new tile via emit_admit() -> oracle proves, table slot lit ('T'),
            and tile captured in tools/glyph_gpt/admitted/
  - Step 4: Re-dispatch runs newly admitted syscall 8 on-die -> result 18
  - Step 5: Canonical replay fixpoint holds bit-identical across independent runs
  - Step 6: Full end-to-end scenario runner + 3-hash receipt generation
  - Extensions: geo-obs MCP server tools (geos_verify_sentinels, geos_read_cell)
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

from tools.glyph_gpt.atlas import build_default_atlas
from tools.glyph_gpt.baker import syscall_abi_kernel_image
from tools.glyph_gpt.agent_resident import resident_image
from tools.glyph_gpt.runner import GlyphRunner
from tools.geos_emit import GeosEmitter, encode_mailbox_word
from tools.geos_hilbert import stamp_reference_pixels, verify_reference_pixels, hilbert_xy2d_true
from tools.geos_ascii_bridge import project, hilbert_d2xy_true
from tools.gh26_glass_box_scenario import GOOD_TILE, run_glass_box_scenario
from tools.geos_observation_server import geos_verify_sentinels, geos_read_cell


# ── Leg 0: Frame Geometry Self-Attestation & Sentinels ──────────────────

def test_gh265_step0_sentinel_attestation():
    surface_frame = np.zeros((128, 128, 3), dtype=np.uint8)
    stamped = stamp_reference_pixels(surface_frame, n=128)
    assert len(stamped) == 5

    diag = verify_reference_pixels(surface_frame, n=128)
    assert diag["ok"] is True
    assert diag["diagnosis"] == "mapping sound: all reference pixels match"
    for name in ("origin", "x_max", "y_max", "far", "center"):
        assert diag["markers"][name]["ok"] is True

    # Corner corruption triggers axis-flip diagnosis
    corrupted_corner = surface_frame.copy()
    corrupted_corner[0, 0] = (0, 0, 0)
    diag_corner = verify_reference_pixels(corrupted_corner, n=128)
    assert diag_corner["ok"] is False
    assert "orientation / axis-flip error" in diag_corner["diagnosis"]

    # Center-only corruption triggers curve variant diagnosis
    corrupted_center = surface_frame.copy()
    corrupted_center[64, 64] = (0, 0, 0)
    diag_center = verify_reference_pixels(corrupted_center, n=128)
    assert diag_center["ok"] is False
    assert "curve variant / scale distortion" in diag_center["diagnosis"]


# ── Leg 1: Session Intent Post (@750) Observable on Surface ─────────────

def test_gh265_step1_intent_post_observed():
    with tempfile.TemporaryDirectory() as d:
        pub_dir = Path(d) / "publish"
        pub_dir.mkdir(parents=True, exist_ok=True)
        np.save(pub_dir / "kernel_memory.npy", np.zeros(16384, dtype=np.uint32))

        os.environ["GEOS_EMIT_ACK"] = "1"
        emitter = GeosEmitter(publish_dir=pub_dir)
        receipt = emitter.emit({
            "kind": "post",
            "box": 2,
            "word": 750,
            "op": 0x11,
            "payload": 0x2A,
        })
        assert receipt["committed"] is True

        mem = np.load(pub_dir / "kernel_memory.npy")
        expected_word = encode_mailbox_word(0x11, 0x2A)
        assert mem[750] == expected_word
        assert expected_word == 0x3B00112A

        canvas = project(mem, w=80, h=25)
        lines = canvas.split("\n")
        assert lines[17][27] == ">"


# ── Leg 2: Preemptive Servicing by Resident Daemon ───────────────────────

def test_gh265_step2_resident_preemption_serviced():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        res_img = root / "resident.npy"
        resident_image(
            build_default_atlas(),
            mode="resident",
            timer_quantum=12,
            out_path=res_img,
        )

        runner = GlyphRunner(res_img, ram_words=16384)
        drive_res = runner.drive(
            seeds={750: encode_mailbox_word(0x11, 0x2A)},
            max_instructions=60000,
        )
        assert drive_res["halted"] is True
        assert not drive_res["faulted"]

        mem = drive_res["memory"]
        ticks = mem[732]
        assert ticks >= 1
        assert mem[754] == 126  # 3 * 42
        assert mem[703] == (0xFEED0000 | 6)

        canvas = project(mem, w=80, h=25)
        lines = canvas.split("\n")
        assert lines[17][27] == ">"
        assert lines[17][29] == "@"
        assert lines[24][31] == "X"


# ── Leg 3: Oracle-Admitted Capability & Corpus Capture ───────────────────

def test_gh265_step3_oracle_admission_and_corpus_capture():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        admit_img = root / "admit.npy"
        syscall_abi_kernel_image(
            build_default_atlas(),
            mode="admit",
            timer_quantum=20,
            out_path=admit_img,
        )

        runner = GlyphRunner(admit_img, ram_words=16384)
        emitter = GeosEmitter(publish_dir=root)
        os.environ["GEOS_EMIT_ACK"] = "1"

        admit_res = emitter.emit_admit(
            runner,
            GOOD_TILE,
            sys_n=8,
            expected=18,
            argv={0: 6},
            source="template",
            receipt_path=root / "admit_receipt.jsonl",
        )
        assert admit_res.ok is True
        assert admit_res.table_word != 0

        tile_sha = hashlib.sha256(GOOD_TILE.encode()).hexdigest()
        assert tile_sha == "d29b29043f6dfa1e24c10db63fc7371c944b88140a9dd3527955769e5cdbdc33"

        admitted_dir = _REPO / "tools" / "glyph_gpt" / "admitted"
        matches = list(admitted_dir.glob(f"*{tile_sha[:12]}*.glyph"))
        assert len(matches) >= 1
        assert matches[0].read_text() == GOOD_TILE


# ── Leg 4: Admitted Capability Runs On-Die ───────────────────────────────

def test_gh265_step4_admitted_capability_runs_on_die():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        admit_img = root / "admit.npy"
        syscall_abi_kernel_image(
            build_default_atlas(),
            mode="admit",
            timer_quantum=20,
            out_path=admit_img,
        )

        runner = GlyphRunner(admit_img, ram_words=16384)
        emitter = GeosEmitter(publish_dir=root)
        os.environ["GEOS_EMIT_ACK"] = "1"

        admit_res = emitter.emit_admit(
            runner,
            GOOD_TILE,
            sys_n=8,
            expected=18,
            argv={0: 6},
        )
        assert admit_res.ok is True

        drive_res = runner.drive(
            seeds={1570: admit_res.table_word},
            max_instructions=60000,
        )
        assert drive_res["halted"] is True
        assert not drive_res["faulted"]
        assert drive_res["memory"][754] == 18

        canvas = project(drive_res["memory"], w=80, h=25)
        lines = canvas.split("\n")
        assert lines[21][53] == "T"


# ── Leg 5: Canonical Replay MD5 Fixpoint ─────────────────────────────────

def test_gh265_step5_canonical_replay_md5_fixpoint():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        admit_img = root / "admit.npy"
        syscall_abi_kernel_image(
            build_default_atlas(),
            mode="admit",
            timer_quantum=20,
            out_path=admit_img,
        )

        runner1 = GlyphRunner(admit_img, ram_words=16384)
        emitter = GeosEmitter(publish_dir=root)
        os.environ["GEOS_EMIT_ACK"] = "1"
        admit_res = emitter.emit_admit(
            runner1,
            GOOD_TILE,
            sys_n=8,
            expected=18,
            argv={0: 6},
        )
        assert admit_res.ok is True

        drive1 = runner1.drive(seeds={1570: admit_res.table_word}, max_instructions=60000)
        assert drive1["halted"] is True

        np.save(admit_img, runner1.image)
        runner2 = GlyphRunner(admit_img, ram_words=16384)
        drive2 = runner2.drive(seeds={1570: admit_res.table_word}, max_instructions=60000)
        assert drive2["halted"] is True

        assert drive1["memory"] == drive2["memory"]
        md5_1 = hashlib.md5(np.array(drive1["memory"], dtype=np.uint32).tobytes()).hexdigest()
        md5_2 = hashlib.md5(np.array(drive2["memory"], dtype=np.uint32).tobytes()).hexdigest()
        assert md5_1 == md5_2
        assert md5_1 == "ab8e4b39afc20d088a001d186c3e2174"


# ── Leg 6: Full End-to-End Scenario & Receipt Generation ─────────────────

def test_gh265_step6_full_scenario_and_receipt_generation():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        receipt_path = root / "TEST_RECEIPT.md"
        res = run_glass_box_scenario(work_dir=root, receipt_out=receipt_path)

        assert res["sentinel_pass"] is True
        assert res["sentinel_diagnosis"] == "mapping sound: all reference pixels match"
        assert res["resident_execution"]["result_word_754"] == 126
        assert res["admitted_call_result"] == 18
        assert res["admitted_tile"]["sha256"] == "d29b29043f6dfa1e24c10db63fc7371c944b88140a9dd3527955769e5cdbdc33"
        assert res["replay_md5"] == "ab8e4b39afc20d088a001d186c3e2174"

        assert receipt_path.exists()
        content = receipt_path.read_text()
        assert "The Three-Hash Provenance Chain" in content
        assert "d29b29043f6dfa1e24c10db63fc7371c944b88140a9dd3527955769e5cdbdc33" in content
        assert "ab8e4b39afc20d088a001d186c3e2174" in content
        assert "mapping sound: all reference pixels match" in content
        assert "[ASCII Canvas" in content


# ── Leg 7: Geo-Obs MCP Extensions (Sentinels & Cell Inspection) ─────────

def test_gh265_geo_obs_extensions():
    with tempfile.TemporaryDirectory() as d:
        os.environ["GEOS_IMAGE_DIR"] = d

        # 1. Stamped surface frame passes sentinel verification
        surface_frame = np.zeros((128, 128, 3), dtype=np.uint8)
        stamp_reference_pixels(surface_frame, n=128)
        np.save(Path(d) / "surface_frame.npy", surface_frame)

        # Also seed kernel_memory
        mem = np.zeros(16384, dtype=np.uint32)
        mem[750] = 0x3B00112A
        mem[754] = 126
        mem[703] = 0xFEED0006
        np.save(Path(d) / "kernel_memory.npy", mem)

        sentinel_diag_str = geos_verify_sentinels()
        sentinel_diag = json.loads(sentinel_diag_str)
        assert sentinel_diag["ok"] is True
        assert sentinel_diag["diagnosis"] == "mapping sound: all reference pixels match"

        # 2. Read cell inspections
        c750 = json.loads(geos_read_cell(750))
        assert c750["word"] == 750
        assert c750["x"] == 27
        assert c750["y"] == 17
        assert c750["region"] == "S"
        assert c750["marker"] == ">"
        assert c750["value"] == 0x3B00112A

        c754 = json.loads(geos_read_cell(754))
        assert c754["word"] == 754
        assert c754["x"] == 29
        assert c754["y"] == 17
        assert c754["region"] == "S"
        assert c754["marker"] == "@"
        assert c754["value"] == 126

        c703 = json.loads(geos_read_cell(703))
        assert c703["word"] == 703
        assert c703["x"] == 31
        assert c703["y"] == 24
        assert c703["marker"] == "X"

        # Out of bounds cell
        c_oob = json.loads(geos_read_cell(20000))
        assert "error" in c_oob
