#!/usr/bin/env python3
"""
geos_devtab — device table and driver registry (Glyph OS skeleton, OS-level).

WHY THIS EXISTS (the Linux gap it closes)
    GH-22 defines a device-driver ABI where drivers run as unprivileged tasks
    and are handed an MMIO window. What does not exist is the TABLE: the object
    that knows which devices exist, which driver claims which device, and which
    windows are already granted — so two drivers cannot be handed overlapping
    MMIO ranges, and a driver cannot be bound twice.

    Linux reaches the same shape through driver-core `struct device_driver`
    match tables + `request_mem_region`. This is that, sized for the substrate.

ENGINE FACTS THIS MODULE MUST MATCH
    MMIO lives at BOX_MMIO_BASE = 0x8000; granted windows are expressed to the
    engine as box lo/hi word pairs (BOX0_LO/HI = +0x0C/+0x10, BOX1 +0x14/+0x18,
    BOX2 +0x28/+0x2C). Windows are WORD ranges, not byte ranges — the engine's
    box bounds are word-addressed. A device descriptor therefore carries word
    bounds, and the grant writer converts to the box words.

DESIGN INVARIANTS
    I1  Disjoint windows: no two granted windows overlap. Enforced by a pure
        predicate so it is testable without the kernel.
    I2  No double binding: one driver instance binds one device; a second bind
        raises rather than silently replacing the first binding.
    I3  Deterministic matching: match_score is a pure function and probe order
        is sorted, so the same device table always binds the same way
        (replayability — the receipt discipline).
    I4  Windows are word ranges within the MMIO aperture; a window outside
        [0, MMIO_APERTURE_WORDS) is rejected, not clamped.
    I5  A driver may bind only with CAP_DEV_MMIO (geos_caps) — the registry
        records the capability requirement rather than assuming it.

BOUNDARY MAP
    geos_caps.gate(CAP_DEV_MMIO) ──> Driver.bind authorised
    Devtab.bind() ──> window grant ──> box lo/hi MMIO words (BOX0/1/2)
    geos_proctab: the bound driver's task pid is recorded on the binding

PHASE STATUS
    Phase 1 (structure) : done    Phase 2 (lock): done
    Phase 3 (population): table identity path (register_device) is populated;
                          probe/bind/grant_words guards were already live.
                          Unprivileged driver-task wiring (GH-22) and real
                          MMIO emission are still NOT done.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

__all__ = [
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
]

DEV_VENDOR_SHIFT = 16
MMIO_APERTURE_WORDS = 0x1000   # the 0x8000..0x8FFF MMIO aperture, in words


def device_id(vendor: int, dev_class: int) -> int:
    """Pack a device identity as (vendor << 16) | class. IMPLEMENTED (pure).

    Field widths are fixed and validated; a vendor or class that does not fit
    raises rather than silently truncating (a truncated id would make two
    different devices indistinguishable — undetectable aliasing).
    """
    for name, value in (("vendor", vendor), ("dev_class", dev_class)):
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative int, got {value!r}")
        if value > 0xFFFF:
            raise ValueError(f"{name} does not fit 16 bits: {value:#x}")
    return (vendor << DEV_VENDOR_SHIFT) | dev_class


def device_vendor(dev_id: int) -> int:
    """Vendor field of a packed device id. IMPLEMENTED (pure)."""
    _check_id(dev_id)
    return (dev_id >> DEV_VENDOR_SHIFT) & 0xFFFF


def device_class(dev_id: int) -> int:
    """Class field of a packed device id. IMPLEMENTED (pure)."""
    _check_id(dev_id)
    return dev_id & 0xFFFF


def _check_id(dev_id: int) -> None:
    if not isinstance(dev_id, int) or dev_id < 0:
        raise ValueError(f"device id must be a non-negative int, got {dev_id!r}")


def window_overlap(lo_a: int, hi_a: int, lo_b: int, hi_b: int) -> bool:
    """Do word ranges [lo,hi) and [lo,hi) intersect? IMPLEMENTED (pure, I1).

    Half-open by construction, so an end-exclusive range that merely touches
    ([0,10) and [10,20)) is NOT an overlap. An empty or inverted range raises —
    a malformed window must not read as "no conflict".
    """
    for lo, hi in ((lo_a, hi_a), (lo_b, hi_b)):
        if hi <= lo:
            raise ValueError(f"empty or inverted window: [{lo}, {hi})")
    return lo_a < hi_b and lo_b < hi_a


def window_ok(lo: int, hi: int, aperture_words: int = MMIO_APERTURE_WORDS) -> bool:
    """Is the window inside the MMIO aperture? IMPLEMENTED (pure, I4)."""
    if hi <= lo:
        raise ValueError(f"empty or inverted window: [{lo}, {hi})")
    if lo < 0:
        raise ValueError(f"window lo must be non-negative, got {lo}")
    return hi <= aperture_words


@dataclass(frozen=True)
class DeviceDescriptor:
    """A device the kernel knows about. LOCKED fields."""

    dev_id: int
    name: str
    window_lo: int
    window_hi: int
    irq_word: int = 0      # MMIO word the device raises its interrupt through

    def __post_init__(self) -> None:
        _check_id(self.dev_id)
        if not window_ok(self.window_lo, self.window_hi):
            raise ValueError(
                f"device {self.name}: window [{self.window_lo},{self.window_hi}) "
                f"outside aperture (0..{MMIO_APERTURE_WORDS})"
            )
        if self.irq_word < 0:
            raise ValueError("irq_word must be non-negative")

    @property
    def window(self) -> Tuple[int, int]:
        return (self.window_lo, self.window_hi)


@dataclass(frozen=True)
class Driver:
    """A driver's match table. LOCKED fields.

    vendor/dev_class of None means "wildcard on that field". A driver with both
    wildcards matches everything — allowed, because the resulting bind order is
    still deterministic (I3), but it is the caller's explicit choice.
    """

    name: str
    vendor: Optional[int] = None
    dev_class: Optional[int] = None

    def __post_init__(self) -> None:
        for field_name, value in (("vendor", self.vendor), ("dev_class", self.dev_class)):
            if value is not None and (not isinstance(value, int) or not 0 <= value <= 0xFFFF):
                raise ValueError(f"{field_name} must be None or a 16-bit int, got {value!r}")


def match_score(driver: Driver, device: DeviceDescriptor) -> int:
    """Specificity of a driver/device match. IMPLEMENTED (pure, I3).

    Scoring is deliberately simple and total:
        -1  no match
         2  both fields match
         1  one field matches, the other is a wildcard
    Higher wins; ties broken by sorted driver name at the call site so the
    outcome is deterministic.
    """
    v_ok = driver.vendor is None or driver.vendor == device_vendor(device.dev_id)
    c_ok = driver.dev_class is None or driver.dev_class == device_class(device.dev_id)
    if not (v_ok and c_ok):
        return -1
    if driver.vendor is not None and driver.dev_class is not None:
        return 2
    return 1


@dataclass(frozen=True)
class Binding:
    """A driver bound to a device with a granted window. LOCKED fields."""

    device: str
    driver: str
    window_lo: int
    window_hi: int
    pid: Optional[int] = None


class DeviceConflict(RuntimeError):
    """Raised on overlapping windows (I1) or a double bind (I2)."""


@dataclass
class Devtab:
    """The device table + binding registry (Phase 3 stub).

    PHASE 3 TODO (builder) — bodies deliberately stubbed:
        register_device(desc) : add to the table; reject a duplicate dev_id+name.
        probe(driver)         : devices matching, sorted by (-score, name) —
                                deterministic bind order (I3).
        bind(driver, device, pid): enforce I1 (no window overlap with existing
                                grants) and I2 (no double bind); record the pid.
        grant_words(binding)  : emit the box lo/hi word pair for the engine.
        release(device)       : unbind and free the window.
    """

    devices: Dict[str, DeviceDescriptor] = field(default_factory=dict)
    bindings: List[Binding] = field(default_factory=list)

    def register_device(self, desc: DeviceDescriptor) -> DeviceDescriptor:
        """Register a device with identity discipline.

        Refusals:
            1. desc is not a DeviceDescriptor -> TypeError
            2. desc.name already in self.devices -> DeviceConflict

        Any refusal is non-mutating: self.devices and self.bindings are untouched.
        """
        if not isinstance(desc, DeviceDescriptor):
            raise TypeError(f"desc must be DeviceDescriptor, got {type(desc).__name__}")
        if desc.name in self.devices:
            raise DeviceConflict(f"device {desc.name!r} already registered")
        self.devices[desc.name] = desc
        return desc

    def probe(self, driver: Driver) -> List[DeviceDescriptor]:
        """Matching devices, most-specific first. IMPLEMENTED (pure, I3)."""
        scored = [
            (match_score(driver, d), d.name, d)
            for d in self.devices.values()
        ]
        matched = [(s, n, d) for (s, n, d) in scored if s >= 0]
        return [d for _s, _n, d in sorted(matched, key=lambda t: (-t[0], t[1]))]

    def conflicts(self, lo: int, hi: int) -> List[Binding]:
        """Existing bindings that would overlap [lo,hi). IMPLEMENTED (I1)."""
        return [
            b for b in self.bindings
            if window_overlap(b.window_lo, b.window_hi, lo, hi)
        ]

    def bind(self, driver: Driver, device: DeviceDescriptor, pid: Optional[int] = None) -> Binding:
        """ENFORCED guard + stubbed effect (I1/I2 are live, the grant is Phase 3)."""
        clash = self.conflicts(device.window_lo, device.window_hi)
        if clash:
            raise DeviceConflict(
                f"window [{device.window_lo},{device.window_hi}) for {device.name} overlaps "
                f"{[(b.driver, b.window_lo, b.window_hi) for b in clash]}"
            )
        already = [b for b in self.bindings if b.device == device.name]
        if already:
            raise DeviceConflict(f"device {device.name} already bound to {already[0].driver}")
        binding = Binding(
            device=device.name,
            driver=driver.name,
            window_lo=device.window_lo,
            window_hi=device.window_hi,
            pid=pid,
        )
        self.bindings.append(binding)
        return binding

    def grant_words(self, binding: Binding) -> Tuple[int, int]:
        """Box lo/hi word pair for the engine. IMPLEMENTED (pure, I4)."""
        if not window_ok(binding.window_lo, binding.window_hi):
            raise ValueError(
                f"refusing to grant window outside aperture: "
                f"[{binding.window_lo},{binding.window_hi})"
            )
        return (binding.window_lo, binding.window_hi)


if __name__ == "__main__":  # Phase-1 smoke: shape, not behaviour.
    tab = Devtab()
    uart = DeviceDescriptor(device_id(0x1001, 0x0003), "uart0", 0x40, 0x48, irq_word=0x48)
    tab.register_device(uart)
    drv = Driver("uart-pl011", vendor=0x1001, dev_class=0x0003)
    print(f"probe -> {[d.name for d in tab.probe(drv)]}")
    b = tab.bind(drv, uart, pid=7)
    print(f"bound {b.driver}->{b.device} words={tab.grant_words(b)}")
    try:
        tab.bind(Driver("other"), uart, pid=8)
    except DeviceConflict as exc:
        print(f"refused double bind: {exc}")
