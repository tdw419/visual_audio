"""
tests/test_osskel_devtab_register.py — Gate for OS-SKEL-R2 Phase 3 Step 6:
`Devtab.register_device` (identity discipline) + `grant_words` (exact window).

Gate clause (round brief `.builder_queue/brief_osskel_r2_phase3.md`, step 6):
  duplicate device name raises; `grant_words` returns the descriptor's exact
  `(lo,hi)`; out-of-aperture descriptor is rejected at construction (not clamped).

Mechanism under test:
  I1/I2 window + double-bind guards are ALREADY live in `Devtab.bind` and are
  re-asserted here (never weakened). Step 6 adds identity discipline to the
  table: a device is identified by its row key `name` (INSTANCE identity), so a
  second registration cannot silently replace the first. `dev_id` is a MODEL id
  (vendor<<16|class) — drivers MATCH on it (I3) — so two devices of the same
  model at different windows are legal and stage L2 pins that: policing
  `dev_id` would break `tools/geos_os_skel_verify.py`, which registers exactly
  such a set. `grant_words` is the I4 aperture gate: it emits the descriptor's
  own word bounds, and refuses a range outside the aperture rather than
  clamping.

  No new injection idiom: step 6 binds nothing at module level (the step-2
  MMIO sink and the step-3 asid allocator stay in `tools/geos_aspace.py`).
"""

from __future__ import annotations

import inspect

import pytest

import tools.geos_aspace as geos_aspace
import tools.geos_devtab as geos_devtab
from tools.geos_devtab import (
    MMIO_APERTURE_WORDS,
    Binding,
    DeviceConflict,
    DeviceDescriptor,
    Devtab,
    Driver,
    device_id,
    window_ok,
)

# A refusal may be the table's own conflict error or a plain ValueError: the
# clause is "raises rather than silently replacing/aliasing", so both are
# accepted, but a silent success (the stub behaviour) fails either way.
REFUSAL = (DeviceConflict, ValueError)


def _desc(name: str, vendor: int, dev_class: int, lo: int, hi: int, irq: int = 0) -> DeviceDescriptor:
    return DeviceDescriptor(device_id(vendor, dev_class), name, lo, hi, irq_word=irq)


def test_l1_duplicate_device_name_is_refused_and_non_mutating() -> None:
    """L1: registering a second device under a NAME already in the table raises,
    and the original descriptor is still the one the table hands out."""
    tab = Devtab()
    first = _desc("uart0", 0x1001, 0x0003, 0x40, 0x48, irq=0x48)
    tab.register_device(first)

    impostor = _desc("uart0", 0x2002, 0x0005, 0x100, 0x108)  # same name, other id/window
    with pytest.raises(REFUSAL):
        tab.register_device(impostor)

    assert len(tab.devices) == 1
    assert tab.devices["uart0"] is first
    assert tab.devices["uart0"].dev_id == first.dev_id
    assert tab.devices["uart0"].window == (0x40, 0x48)
    assert tab.bindings == []


def test_l2_two_instances_of_one_model_are_legal_and_independent() -> None:
    """L2: identity in the table is INSTANCE identity, keyed on `name`. `dev_id`
    is a MODEL id (vendor<<16|class), so a second device of the same model at a
    different window is legitimate and must register — `probe` then lists both,
    each binds, and each grants its own window.

    This leg is the guard against over-reach: refusing duplicates on `dev_id`
    would reject a machine with two identical device models (the structural
    harness `tools/geos_os_skel_verify.py` registers exactly such a set), and
    the model id is what a driver MATCHES on (I3), not what identifies a row.
    """
    tab = Devtab()
    uart0 = tab.register_device(_desc("uart0", 0x1001, 0x0003, 0x40, 0x48, irq=0x48))
    uart1 = tab.register_device(_desc("uart1", 0x1001, 0x0003, 0x48, 0x50))  # same model

    assert uart0.dev_id == uart1.dev_id
    assert set(tab.devices) == {"uart0", "uart1"}
    assert tab.devices["uart0"] is uart0 and tab.devices["uart1"] is uart1

    drv = Driver("uart-pl011", vendor=0x1001, dev_class=0x0003)
    assert [d.name for d in tab.probe(drv)] == ["uart0", "uart1"]
    b0 = tab.bind(drv, uart0, pid=1)
    b1 = tab.bind(drv, uart1, pid=2)
    assert tab.grant_words(b0) == (0x40, 0x48)
    assert tab.grant_words(b1) == (0x48, 0x50)

    # The name key is still the refusal: neither existing name may be reused,
    # and neither refusal may disturb the two live bindings.
    for stolen in ("uart0", "uart1"):
        with pytest.raises(REFUSAL):
            tab.register_device(_desc(stolen, 0x3003, 0x0009, 0x400, 0x408))
    assert set(tab.devices) == {"uart0", "uart1"}
    assert [b.device for b in tab.bindings] == ["uart0", "uart1"]


def test_l3_grant_words_returns_the_descriptor_exact_window() -> None:
    """L3: `grant_words` emits the bound device's own word bounds — for two
    devices at different bases, so a hardcoded/zeroed range cannot pass."""
    tab = Devtab()
    uart0 = tab.register_device(_desc("uart0", 0x1001, 0x0003, 0x40, 0x48, irq=0x48))
    uart1 = tab.register_device(_desc("uart1", 0x1001, 0x0003, 0x48, 0x50))

    drv = Driver("uart-pl011", vendor=0x1001, dev_class=0x0003)
    b0 = tab.bind(drv, uart0, pid=7)
    b1 = tab.bind(drv, uart1, pid=8)

    assert b0.window_lo == 0x40 and b0.window_hi == 0x48
    assert b1.window_lo == 0x48 and b1.window_hi == 0x50
    assert tab.grant_words(b0) == (0x40, 0x48)
    assert tab.grant_words(b1) == (0x48, 0x50)
    # ... and the pair IS the descriptor's window, not a re-derived neighbour.
    assert tab.grant_words(b0) == uart0.window
    assert tab.grant_words(b1) == uart1.window
    assert tab.grant_words(b0) != tab.grant_words(b1)


def test_l4_out_of_aperture_is_rejected_at_construction_never_clamped() -> None:
    """L4: a window outside [0, MMIO_APERTURE_WORDS) is refused when the
    descriptor is built — not clamped into range and not deferred to bind."""
    with pytest.raises(ValueError):
        _desc("far0", 0x1001, 0x0004, MMIO_APERTURE_WORDS - 4, MMIO_APERTURE_WORDS + 1)
    with pytest.raises(ValueError):
        _desc("neg0", 0x1001, 0x0004, -1, 8)
    with pytest.raises(ValueError):
        _desc("empty0", 0x1001, 0x0004, 0x40, 0x40)  # empty window is not "no window"
    with pytest.raises(ValueError):
        _desc("inv0", 0x1001, 0x0004, 0x48, 0x40)

    # The pure predicate refuses WITHOUT clamping ...
    assert window_ok(MMIO_APERTURE_WORDS - 4, MMIO_APERTURE_WORDS + 1) is False
    assert window_ok(0, MMIO_APERTURE_WORDS * 4) is False
    # ... and the last aperture word is legal (end-exclusive boundary), so the
    # refusal above is a real bound, not an off-by-one rejection.
    edge = _desc("edge0", 0x1001, 0x0005, MMIO_APERTURE_WORDS - 1, MMIO_APERTURE_WORDS)
    assert edge.window == (MMIO_APERTURE_WORDS - 1, MMIO_APERTURE_WORDS)
    assert window_ok(*edge.window) is True

    # A refused descriptor never enters the table (nothing was constructed).
    tab = Devtab()
    with pytest.raises(ValueError):
        tab.register_device(_desc("far1", 0x1001, 0x0006, 0, MMIO_APERTURE_WORDS + 8))
    assert tab.devices == {} and tab.bindings == []

    # Second layer of the same invariant: even a hand-fabricated Binding whose
    # range left the aperture cannot be granted (grant validates, not trusts).
    with pytest.raises(ValueError):
        tab.grant_words(
            Binding(device="ghost", driver="d", window_lo=0, window_hi=MMIO_APERTURE_WORDS + 2)
        )


def test_l5_register_probe_bind_grant_end_to_end() -> None:
    """L5: the whole table path on windows that are adjacent (legal, half-open)
    and on one that overlaps (refused), with the guard's refusal leaving the
    binding list untouched."""
    tab = Devtab()
    block = _desc("block0", 0x1001, 0x0002, 0x80, 0x90)
    shadow = _desc("shadow0", 0x1001, 0x0002, 0x90, 0xA0)     # touches block0: legal
    clash = _desc("clash0", 0x1001, 0x0002, 0x88, 0x90)       # inside block0: refused
    for d in (block, shadow, clash):
        tab.register_device(d)
    assert len(tab.devices) == 3

    drv = Driver("block-buf", vendor=0x1001, dev_class=0x0002)
    assert [d.name for d in tab.probe(drv)] == ["block0", "clash0", "shadow0"]  # I3 sort

    b_block = tab.bind(drv, block, pid=3)
    b_shadow = tab.bind(drv, shadow, pid=4)
    assert tab.grant_words(b_block) == (0x80, 0x90)
    assert tab.grant_words(b_shadow) == (0x90, 0xA0)

    with pytest.raises(DeviceConflict):
        tab.bind(drv, clash, pid=5)
    assert [b.device for b in tab.bindings] == ["block0", "shadow0"]
    assert tab.conflicts(0x88, 0x90) == [b_block]
    assert tab.conflicts(0x80, 0x84) == [b_block]

    # I2 stays live alongside the new identity discipline and names the holder.
    with pytest.raises(DeviceConflict) as exc:
        tab.bind(Driver("second"), block, pid=6)
    assert "block0" in str(exc.value)
    assert len(tab.bindings) == 2


def test_l6_identity_refusals_do_not_disturb_existing_bindings_or_grants() -> None:
    """L6: a refused duplicate registration leaves the live bindings, their
    pids and their granted words exactly as they were."""
    tab = Devtab()
    uart0 = tab.register_device(_desc("uart0", 0x1001, 0x0003, 0x40, 0x48, irq=0x48))
    drv = Driver("uart-pl011", vendor=0x1001, dev_class=0x0003)
    binding = tab.bind(drv, uart0, pid=7)

    before = [(b.device, b.driver, b.window_lo, b.window_hi, b.pid) for b in tab.bindings]
    with pytest.raises(REFUSAL):
        tab.register_device(_desc("uart0", 0x3003, 0x0009, 0x400, 0x408))  # name already taken

    assert [(b.device, b.driver, b.window_lo, b.window_hi, b.pid) for b in tab.bindings] == before
    assert len(tab.devices) == 1 and tab.devices["uart0"] is uart0
    assert tab.grant_words(binding) == (0x40, 0x48)
    assert [d.name for d in tab.probe(drv)] == ["uart0"]

    # A NEW instance of the same model is legal (L2) and still disturbs nothing:
    # the existing binding, its pid and its granted words are untouched, and the
    # table now lists both instances.
    uart1 = tab.register_device(_desc("uart1", 0x1001, 0x0003, 0x48, 0x50))
    assert [(b.device, b.driver, b.window_lo, b.window_hi, b.pid) for b in tab.bindings] == before
    assert tab.grant_words(binding) == (0x40, 0x48)
    assert tab.devices["uart0"] is uart0 and tab.devices["uart1"] is uart1
    assert tab.bindings[0].device == "uart0"


def test_l7_interface_hygiene_and_single_idiom() -> None:
    """L7: signatures/annotations unchanged, `__all__` untouched, no new
    module-level hook in geos_devtab (the step-2 sink and the step-3 allocator
    remain the only injection idioms, and both live in geos_aspace)."""
    assert list(inspect.signature(Devtab.register_device).parameters) == ["self", "desc"]
    assert Devtab.register_device.__annotations__.get("return") == "DeviceDescriptor"
    assert list(inspect.signature(Devtab.grant_words).parameters) == ["self", "binding"]
    assert Devtab.grant_words.__annotations__.get("return") == "Tuple[int, int]"

    assert set(geos_devtab.__all__) == {
        "DEV_VENDOR_SHIFT",
        "MMIO_APERTURE_WORDS",
        "device_id",
        "device_vendor",
        "device_class",
        "window_overlap",
        "window_ok",
        "DeviceDescriptor",
        "Driver",
        "Binding",
        "Devtab",
        "DeviceConflict",
    }
    for leaked in ("set_mmio_sink", "get_mmio_sink", "set_asid_allocator", "get_asid_allocator"):
        assert not hasattr(geos_devtab, leaked), f"geos_devtab grew its own {leaked} hook"
    assert geos_aspace.get_asid_allocator is not None
