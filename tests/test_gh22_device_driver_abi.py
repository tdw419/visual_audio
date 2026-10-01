#!/usr/bin/env python3
"""tests/test_gh22_device_driver_abi.py — GH-22 Device Driver ABI gate (RED).

Spec (roadmap row GH-22, systems/GLYPH_SELF_HOSTING_ROADMAP.md):

  Device Driver ABI: spatial microkernel protocol — drivers run as
  unprivileged USER tasks in isolated boxes communicating via non-blocking
  mailboxes (GH-13/14); hardware MMIO bounded per box; no monolithic kernel
  drivers or struct file_operations bloat.

  Gate: simulated block/UART driver in BOX1 services requests from BOX0
  application through kernel mailbox; corrupted packet or out-of-bounds
  MMIO traps cleanly (E-K1) without destabilizing kernel.

SOURCE RULE (roadmap, GPLv2 derivative-work): the driver below is written
from the SIMULATED DEVICE DATASHEET in this header — no Linux source was
read or transcribed. The device is our own fixture; there is no real
silicon, so the trusted-unproven boundary is: the oracle proves the driver
tile emits the correct register sequence against the in-image DEVICE MODEL
(the datasheet table below, mirrored host-side in test 3); the model itself
is trusted fixture code, not proven against hardware. Extend the model as
devices are added.

SIMULATED UART DEVICE DATASHEET (fixture "DEV-U1", our own spec):

  Register map (word offsets inside the driver's box; the box bound IS the
  MMIO bound — an E-K1 store outside [718..735) is the OOB-MMIO trap):

    word 733  DEV_DATA    (R/W)  transmit/receive holding word
    word 734  DEV_STATUS  (R/W)  status/control

  STATUS bits:
    bit 7 (0x80) RX_DONE   set by driver after a full byte lands in DATA
    bit 1 (0x02) TX_BUSY   device busy (reserved; unused by this fixture)
    bit 0 (0x01) TX_ACTIVE driver sets while the transfer is in flight

  PUT sequence (driver-initiated, per datasheet §2):
    1. DEV_STATUS <- 0x01            (TX_ACTIVE; device observes transfer)
    2. DEV_DATA   <- payload byte
    3. DEV_STATUS <- 0x81            (TX_ACTIVE cleared by device semantics,
                                      RX_DONE latched; final quiescent value)

MESSAGE FORMAT (one 32-bit word, matching the engine's word-addressed
mailbox — no multi-word marshaling, so a corrupted packet is one flipped
field):

    bits [31:24] checksum  = (opcode + payload) & 0xFF
    bits [23:16] reserved  = 0
    bits [15:8]  opcode    (1 = DEV_PUT)
    bits [7:0]   payload byte

IMAGE ABI (fixed word indices; GH-13's scheme, 2 boxes + device regs):

  BOX0 = application arena [700..717), BOX1 = driver arena [718..735)
  703        app exit word          0xFEED0000 | 22 on success
  710        app uart receipt       app's request word (in-box copy)
  713        app request scratch    app builds the request here
  714        app read-out           verdict delivered by kernel (SYS 8)
  720        driver read-out        request delivered by kernel (SYS 7)
  723        driver exit word       0xFEED0000 | 23 on success
  724        driver verdict         'V' verified / 'E' corrupted packet
  733 / 734  DEV_DATA / DEV_STATUS  (the datasheet map, inside BOX1)
  754        mailbox request        app->driver, kernel-mediated (SYS 6)
  758        unknown-syscall marker 'E' = 69 on unexpected syscall
  759        fault-leg verdict      0xFA171 (E-K1 handler record)
  950        kernel status word     0xCAFE0000 | 26 after the full pipeline

SCHEDULE (baked round-robin, GH-13 style): app slice 1 (SYS 6 send) ->
driver slice (SYS 7 recv + validate + device PUT + verdict, SYS 8 send
verdict) -> app slice 2 (SYS 9 recv verdict + receipt + exit). Mailboxes
are NON-BLOCKING: every slice copies-and-continues; a slice that finds its
mailbox empty proceeds (the verdict arrives via the round-robin order, so
the happy path never observes an empty copy, and the corrupt leg asserts
the copy still leaves the run stable).

GATE LEGS (one test per leg):

  1. bake         driver_abi_kernel_image() emits one image
  2. pipeline     app request -> driver PUT -> verdict -> app receipt;
                  both exits + status 0xCAFE001A, zero faults
  3. word-exact   DEV_DATA/DEV_STATUS == host device model; request,
                  mailbox, read-outs, verdict all byte-exact; step_trace
                  shows the driver ran in USER mode (unprivileged)
  4. corrupt      flipped checksum -> verdict 'E', driver exit still clean,
                  device regs UNTOUCHED (driver refused the transfer),
                  kernel stable (status still written)
  5. OOB MMIO     fault_leg=True: driver's out-of-box store vectors E-K1,
                  handler records 0xFA171, app words not destabilized

Today this FAILS at import: driver_abi_kernel_image does not exist yet.
"""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import driver_abi_kernel_image        # noqa: E402 (RED: not implemented)

# ── GH-22 image ABI (fixed word indices — see module docstring) ──────────
GH22_EXIT_APP = 703
GH22_UART_APP = 710
GH22_REQ_SCRATCH = 713
GH22_READOUT_APP = 714
GH22_READOUT_DRV = 720
GH22_EXIT_DRV = 723
GH22_VERDICT_DRV = 724
GH22_DEV_DATA = 733
GH22_DEV_STATUS = 734
GH22_MAILBOX_WORD = 754
GH22_BADSYS_WORD = 758
GH22_FAULT_WORD = 759

GH22_EXIT_OK_APP = 0xFEED0000 | 22
GH22_EXIT_OK_DRV = 0xFEED0000 | 23
GH22_FAULT_SEEN = 0xFA171
KERNEL_OK = 0xCAFE0000 | 26      # 0xCAFE001A

GH22_OPCODE_PUT = 1
VERIFIED = ord('V')
ERRORED = ord('E')

GH22_PAYLOAD = 0x5A
GH22_REQ_GOOD = (
    (((GH22_OPCODE_PUT + GH22_PAYLOAD) & 0xFF) << 24)
    | (GH22_OPCODE_PUT << 8)
    | GH22_PAYLOAD
)
GH22_REQ_CORRUPT = GH22_REQ_GOOD ^ (1 << 24)   # flipped checksum bit


def _device_model(request_word: int) -> dict:
    """Host-side DEVICE MODEL (the trusted fixture; datasheet §2 PUT)."""
    opcode = (request_word >> 8) & 0xFF
    payload = request_word & 0xFF
    checksum = (request_word >> 24) & 0xFF
    valid = checksum == ((opcode + payload) & 0xFF)
    if valid and opcode == GH22_OPCODE_PUT:
        return {"data": payload, "status": 0x81, "verified": True}
    return {"data": 0, "status": 0, "verified": False}


def _bake(tmp: Path, name: str = "gh22.glyph.npy", fault_leg: bool = False,
          corrupt_leg: bool = False) -> Path:
    atlas = build_default_atlas()
    out = tmp / name
    driver_abi_kernel_image(atlas, fault_leg=fault_leg, corrupt_leg=corrupt_leg,
                            out_path=out)
    return out


def _run(tmp: Path, fault_leg: bool = False, corrupt_leg: bool = False):
    out = _bake(tmp, fault_leg=fault_leg, corrupt_leg=corrupt_leg)
    # Kernel stores into the isolation MMIO block (words 8192+), so the
    # runner must size RAM past the MMIO top word (GH-13 rule).
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=80000, trace=True)
    return receipt


def test_gh22_driver_abi_image_bakes():
    """Leg 1: driver_abi_kernel_image() emits one image."""
    with tempfile.TemporaryDirectory() as d:
        assert _bake(Path(d)).exists(), (
            "driver_abi_kernel_image must emit one image")


def test_gh22_app_driver_mailbox_pipeline():
    """Leg 2: app sends PUT request -> driver services it via the datasheet
    sequence -> verdict -> app receipt. Clean run end to end."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d))
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # app built + kept its request
        assert mem[GH22_REQ_SCRATCH] == GH22_REQ_GOOD, (
            f"app scratch 0x{mem[GH22_REQ_SCRATCH]:08x} != 0x{GH22_REQ_GOOD:08x}")
        assert mem[GH22_UART_APP] == GH22_REQ_GOOD
        # kernel delivered the request to the driver (mailbox + read-out)
        assert mem[GH22_MAILBOX_WORD] == GH22_REQ_GOOD
        assert mem[GH22_READOUT_DRV] == GH22_REQ_GOOD
        # driver verified and answered
        assert mem[GH22_VERDICT_DRV] == VERIFIED, (
            f"driver verdict {mem[GH22_VERDICT_DRV]!r} != 'V'")
        assert mem[GH22_READOUT_APP] == VERIFIED
        # unknown-syscall marker untouched
        assert mem[GH22_BADSYS_WORD] == 0
        # both tasks completed
        assert mem[GH22_EXIT_APP] == GH22_EXIT_OK_APP, (
            f"app exit 0x{mem[GH22_EXIT_APP]:08x}")
        assert mem[GH22_EXIT_DRV] == GH22_EXIT_OK_DRV, (
            f"driver exit 0x{mem[GH22_EXIT_DRV]:08x}")
        # kernel survived the whole pipeline
        assert receipt["status_word_value"] == KERNEL_OK, receipt


def test_gh22_device_model_word_exact():
    """Leg 3: device registers match the host DEVICE MODEL word-exact, and
    the step trace proves the driver ran UNPRIVILEGED (USER mode) — no
    monolithic kernel driver."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d))
        mem = receipt["memory"]
        model = _device_model(GH22_REQ_GOOD)
        assert model["verified"] is True  # model sanity
        assert mem[GH22_DEV_DATA] == model["data"], (
            f"DEV_DATA 0x{mem[GH22_DEV_DATA]:08x} != model 0x{model['data']:08x}")
        assert mem[GH22_DEV_STATUS] == model["status"], (
            f"DEV_STATUS 0x{mem[GH22_DEV_STATUS]:08x} != model "
            f"0x{model['status']:08x}")
        # unprivileged-driver proof: every phase the driver's PC range
        # appears in must be USER mode. We assert the trace contains USER
        # phases in BOX1's PC region AFTER the app's first USER phase
        # (round-robin app -> driver -> app), i.e. the driver is scheduled
        # as a task, not inlined into a SUPER slice.
        trace = receipt.get("step_trace") or []
        assert trace, "runner receipt must carry a step_trace"
        user_phases = []
        cur = None
        for pc, mode in trace:
            if mode == "USER":
                if cur is None:
                    cur = [pc, pc]
                else:
                    cur[1] = pc
            else:
                if cur is not None:
                    user_phases.append(tuple(cur))
                    cur = None
        if cur is not None:
            user_phases.append(tuple(cur))
        assert len(user_phases) >= 3, (
            f"expected >=3 USER phases (app-pre, driver, app-post), got "
            f"{len(user_phases)}: {user_phases}")
        assert all(p2[0] > p1[1] for p1, p2
                   in zip(user_phases, user_phases[1:])), (
            f"USER phases must be strictly ordered (round-robin): {user_phases}")


def test_gh22_corrupted_packet_clean_fail():
    """Leg 4: flipped checksum -> verdict 'E'; the driver REFUSES the
    transfer (device regs untouched), still exits clean, kernel stable."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d), corrupt_leg=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, (
            "a corrupted PACKET is a clean-fail verdict, not a box fault")
        mem = receipt["memory"]
        assert mem[GH22_MAILBOX_WORD] == GH22_REQ_CORRUPT
        assert mem[GH22_READOUT_DRV] == GH22_REQ_CORRUPT
        assert mem[GH22_VERDICT_DRV] == ERRORED, (
            f"driver verdict {mem[GH22_VERDICT_DRV]!r} != 'E'")
        # refused transfer: the device never saw the datasheet sequence
        model = _device_model(GH22_REQ_CORRUPT)
        assert model["verified"] is False  # model agrees the packet is bad
        assert mem[GH22_DEV_DATA] == 0 and mem[GH22_DEV_STATUS] == 0, (
            f"device regs must stay untouched on a corrupt packet: "
            f"data=0x{mem[GH22_DEV_DATA]:08x} status=0x{mem[GH22_DEV_STATUS]:08x}")
        # driver still completes cleanly
        assert mem[GH22_EXIT_DRV] == GH22_EXIT_OK_DRV, (
            f"driver exit 0x{mem[GH22_EXIT_DRV]:08x}")
        # kernel not destabilized
        assert receipt["status_word_value"] == KERNEL_OK, receipt


def test_gh22_oob_mmio_traps_cleanly():
    """Leg 5: driver's out-of-bounds MMIO store (outside its box) vectors
    E-K1; the handler records 0xFA171 and the app/kernel are NOT
    destabilized."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d), fault_leg=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is True, "OOB MMIO store must fault"
        mem = receipt["memory"]
        assert mem[GH22_FAULT_WORD] == GH22_FAULT_SEEN, (
            f"fault word 0x{mem[GH22_FAULT_WORD]:08x} != "
            f"0x{GH22_FAULT_SEEN:08x}")
        # app got its request out before the driver faulted: slice 1 is
        # fully complete (including its own exit write), but slice 2 never
        # runs (the driver faulted before :__dispatch_app2)
        assert mem[GH22_REQ_SCRATCH] == GH22_REQ_GOOD
        assert mem[GH22_MAILBOX_WORD] == GH22_REQ_GOOD
        assert mem[GH22_EXIT_APP] == GH22_EXIT_OK_APP
        assert mem[GH22_READOUT_APP] == 0
        assert mem[GH22_EXIT_DRV] == 0
        assert mem[GH22_VERDICT_DRV] == 0
        # device untouched (driver faulted before the PUT sequence)
        assert mem[GH22_DEV_DATA] == 0 and mem[GH22_DEV_STATUS] == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
