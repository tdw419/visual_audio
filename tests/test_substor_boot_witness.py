"""tests/test_substor_boot_witness.py — Acceptance gate for SUBSTOR-1.

SUBSTOR-1: Substrate storage oracle — boot a real guest from substrate-backed memory.
Roadmap row: systems/GLYPH_SELF_HOSTING_ROADMAP.md:350

LEGS:
  L1 bounded boot:
    A bounded guest sequence reaches a named first-instruction/progress marker,
    with the emulator's RAM reads and writes served from the substrate-backed surface
    (no host-side shadow buffer in the path: mutating the surface between chunks
    is reflected in the guest's next chunk execution).
  L2 substrate witness:
    After the boot, a witness reads the surface and asserts:
    (a) Zero clobbered words outside writer's declared regions.
    (b) Writer attribution for every written word (writer + monotonic write_id).
    (c) Survival across a writeback: memory image after writeback is byte-identical
        to the pre-writeback image (no dropped writes).
  L3 negative leg:
    Deliberately injected clobber (wrong word written by a second writer) MUST report
    RED through the same checker, and a dropped write on writeback MUST report RED.
  L4 non-vacuity:
    Neutering the attribution check turns L2 red (monkeypatched probe in-test,
    with live module restored byte-identical).
  L5 no regression:
    tests/test_spatial_rv32i_cpu.py stays green (subprocess leg with exit 0 and
    >0 tests collected).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "tools") not in sys.path:
    sys.path.insert(0, str(_REPO / "tools"))

from substor_surface_ram import (
    SubstorSurfaceRAM,
    SubstorWitness,
    WitnessError,
    verify_substrate_witness,
)
from substor_boot import (
    PROGRESS_MARKER_BYTE,
    PROGRESS_MARKER_PC,
    PROGRESS_MARKER_STEPS,
    RAM_BASE,
    RAM_DATA_OFFSET,
    SubstorBootDriver,
    create_booted_substrate_guest,
)


# ── Leg 1: Bounded Boot with Substrate Authority ─────────────────────────

def test_l1_bounded_boot(tmp_path: Path) -> None:
    """L1: Guest reaches named progress marker; surface is sole memory authority."""
    surface_file = tmp_path / "l1_surface.png"
    initial_val = 100
    driver, surface_ram = create_booted_substrate_guest(
        surface_path=surface_file, initial_ram_val=initial_val
    )

    data_word_idx = RAM_DATA_OFFSET // 4

    # Chunk 1: Run 2 steps (lui + addi: sets x1 = 0x80000100)
    info1 = driver.step_chunk(steps=2)
    assert info1["pc"] == 0x80000008, f"Expected PC 0x80000008, got {hex(info1['pc'])}"
    assert info1["regs"][1] == RAM_BASE + RAM_DATA_OFFSET

    # Demonstrate substrate surface authority (no host shadow buffer):
    # Mutate word directly on the substrate surface between chunks.
    mutated_val = 0xCAFE1234
    surface_ram.write_word(data_word_idx, mutated_val, writer="guest_boot")
    assert surface_ram.read_word(data_word_idx) == mutated_val

    # Chunk 2: Run remaining steps to reach progress marker
    info2 = driver.step_chunk(steps=6)

    # Assert progress marker reached
    assert PROGRESS_MARKER_BYTE in driver.accumulated_uart, (
        f"Expected UART marker {PROGRESS_MARKER_BYTE}, got {driver.accumulated_uart}"
    )
    assert info2["pc"] == PROGRESS_MARKER_PC, (
        f"Expected PC {hex(PROGRESS_MARKER_PC)}, got {hex(info2['pc'])}"
    )
    assert driver.total_steps == PROGRESS_MARKER_STEPS

    # Assert memory load reflected the surface mutation (mutated_val + 1)
    expected_written_val = (mutated_val + 1) & 0xFFFFFFFF
    assert info2["regs"][2] == expected_written_val, (
        f"Expected reg x2 == {hex(expected_written_val)}, got {hex(info2['regs'][2])}"
    )

    # Assert memory writeback to surface succeeded and persisted
    assert surface_ram.read_word(data_word_idx) == expected_written_val
    assert surface_file.exists(), "Surface PNG was not committed to disk"


# ── Leg 2: Substrate Witness ─────────────────────────────────────────────

def _run_l2_contract(driver: SubstorBootDriver) -> Dict[str, Any]:
    """Execute the L2 substrate witness contract on a driver instance."""
    result = driver.check_witness()
    assert result["status"] == "PASS"
    assert result["clobbers"] == 0
    assert result["attribution_verified"] is True
    assert result["attributed_words"] > 0
    return result


def test_l2_substrate_witness(tmp_path: Path) -> None:
    """L2: Witness asserts zero clobbers, full attribution, and writeback survival."""
    surface_file = tmp_path / "l2_surface.png"
    driver, surface_ram = create_booted_substrate_guest(
        surface_path=surface_file, initial_ram_val=41
    )

    # Boot to progress marker
    info = driver.run_to_progress_marker(max_steps=20, chunk_size=4)
    assert PROGRESS_MARKER_BYTE in driver.accumulated_uart
    assert info["pc"] == PROGRESS_MARKER_PC

    witness = SubstorWitness(surface_ram)

    # (a) Zero clobbered words outside declared regions
    assert len(surface_ram.clobbers) == 0
    assert len(surface_ram.clobbered_words) == 0
    witness.verify_zero_clobbers()

    # (b) Writer attribution for every written word
    attr_info = witness.verify_attribution()
    assert attr_info["verified"] is True
    assert attr_info["count"] > 0

    # Ensure every written word is attributed to loader or guest_boot with valid write_id
    for word_idx, attr in surface_ram.word_attribution.items():
        assert attr["writer"] in ("loader", "guest_boot")
        assert isinstance(attr["write_id"], int) and attr["write_id"] > 0

    # (c) Survival across a writeback (pre == post)
    assert driver.last_pre_writeback is not None
    assert driver.last_post_writeback is not None
    assert driver.last_pre_writeback == driver.last_post_writeback
    witness.verify_writeback_survival(
        driver.last_pre_writeback, driver.last_post_writeback
    )

    # Run overall L2 contract
    res = _run_l2_contract(driver)
    assert res["status"] == "PASS"


# ── Leg 3: Negative Leg (Injected Clobber and Dropped Write) ──────────────

def test_l3_negative_leg(tmp_path: Path) -> None:
    """L3: Injected clobber and dropped write MUST report RED through same checker."""
    surface_file = tmp_path / "l3_surface.png"
    driver, surface_ram = create_booted_substrate_guest(
        surface_path=surface_file, initial_ram_val=41
    )
    driver.run_to_progress_marker()

    # Prior to injection, witness check passes cleanly
    assert driver.check_witness()["status"] == "PASS"

    # Part 1: Deliberately injected clobber (one wrong word written by second writer)
    # Writer "second_rogue_writer" has no declared region covering word 55
    surface_ram.write_word(55, 0xBADF00D, writer="second_rogue_writer")
    assert len(surface_ram.clobbers) == 1

    # The SAME checker MUST report RED (raise WitnessError)
    with pytest.raises(WitnessError) as exc_clobber:
        driver.check_witness()
    err_msg1 = str(exc_clobber.value)
    assert "WITNESS_CLOBBER_DETECTED" in err_msg1

    # Part 2: Dropped write on writeback MUST report RED
    surface_file2 = tmp_path / "l3_surface_drop.png"
    driver2, surface_ram2 = create_booted_substrate_guest(
        surface_path=surface_file2, initial_ram_val=41
    )
    driver2.run_to_progress_marker()
    assert driver2.check_witness()["status"] == "PASS"

    # Simulate a dropped write where post-writeback lost the written word
    tampered_post = list(driver2.last_post_writeback)
    tampered_post[RAM_DATA_OFFSET // 4] = 0x00000000

    with pytest.raises(WitnessError) as exc_drop:
        verify_substrate_witness(
            surface_ram2,
            pre_words=driver2.last_pre_writeback,
            post_words=tampered_post,
        )
    err_msg2 = str(exc_drop.value)
    assert "WITNESS_DROPPED_WRITE" in err_msg2


# ── Leg 4: Non-vacuity Probes ────────────────────────────────────────────

def test_l4_non_vacuity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """L4: Prove attribution check is load-bearing; neutering turns L2 red."""
    surface_file = tmp_path / "l4_surface.png"
    driver, surface_ram = create_booted_substrate_guest(
        surface_path=surface_file, initial_ram_val=41
    )
    driver.run_to_progress_marker()

    # Baseline: unmodified L2 contract passes
    res = _run_l2_contract(driver)
    assert res["status"] == "PASS"

    # Probe 1: An unattributed write trips the attribution check
    orig_attr = dict(surface_ram.word_attribution[0])
    surface_ram.word_attribution[0]["writer"] = "unattributed"
    witness = SubstorWitness(surface_ram)
    with pytest.raises(WitnessError) as exc_unattr:
        witness.verify_attribution()
    assert "WITNESS_ATTRIBUTION_MISSING" in str(exc_unattr.value)

    # Also trips driver.check_witness() (which refuses unattributed writes)
    with pytest.raises(WitnessError):
        driver.check_witness()

    # Restore attribution
    surface_ram.word_attribution[0] = orig_attr
    assert driver.check_witness()["status"] == "PASS"

    # Probe 2: Neutering the attribution check turns L2 RED
    # When verify_attribution is neutered to not verify attribution,
    # the L2 contract assertion (assert res["attribution_verified"] is True) FAILS.
    monkeypatch.setattr(
        SubstorWitness,
        "verify_attribution",
        lambda self: {"verified": False, "count": 0},
    )

    with pytest.raises(AssertionError):
        _run_l2_contract(driver)

    # Probe 3: Monkeypatch cleanup verified (live module restored byte-identical)
    monkeypatch.undo()
    res_restored = _run_l2_contract(driver)
    assert res_restored["attribution_verified"] is True


# ── Leg 5: No Regression on Spatial RV32I Emulator ───────────────────────

def test_l5_no_regression() -> None:
    """L5: tests/test_spatial_rv32i_cpu.py stays green (>0 collected, exit 0)."""
    # Run pytest without -q so the summary line ('N passed') is printed
    cmd = [sys.executable, "-m", "pytest", "tests/test_spatial_rv32i_cpu.py"]
    proc = subprocess.run(
        cmd,
        cwd=str(_REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"Regression test failed with exit code {proc.returncode}:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )

    # Assert >0 tests collected and passed
    match = re.search(r"(\d+)\s+passed", proc.stdout)
    assert match is not None, f"Could not find passed test count in output:\n{proc.stdout}"
    passed_count = int(match.group(1))
    assert passed_count > 0, f"Expected >0 passed tests, got {passed_count}"
