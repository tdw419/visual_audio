#!/usr/bin/env python3
"""
geos_spawn — cross-module spawn integration (Glyph OS skeleton, OS-level).

WHY THIS EXISTS (the Linux gap it closes)
    The four OS-level skeleton modules (geos_aspace, geos_caps, geos_proctab,
    geos_devtab) define the core resource abstractions, but step 7 is the
    integration seam that binds them into a coherent whole:
        one call allocates pid + asid + box, sets caps, binds a driver when
        CAP_DEV_MMIO is held, and refuses the bind with the missing cap named
        when it is not.

SEAMS TO DOCUMENT (architectural reality, do not paper over):
    (a) CapTable exposes no create-row API, so geos_spawn is the one place
        outside geos_caps that writes captab.grants[pid] — a CapTable.create(pid)
        would be the fix, but the interface is locked this round.
    (b) reap retires the asid through the allocator, so a retired AddressSpace
        must not be released again — that double free is refused loudly by
        AsidAllocator.free, and step 8 (engine wiring) is where ownership of
        the space's lifetime moves.
"""

from __future__ import annotations

from typing import List, Optional

from tools.geos_aspace import AddressSpace, get_asid_allocator
from tools.geos_caps import (
    CAP_DEV_MMIO,
    CAP_NONE,
    CAP_SPAWN,
    CapTable,
    cap_implies,
    cap_names,
    get_granter_mask,
)
from tools.geos_devtab import DeviceConflict, DeviceDescriptor, Devtab, Driver
from tools.geos_proctab import ProcessDescriptor, Proctab

__all__ = ["BoxAllocator", "spawn"]


class BoxAllocator:
    """Minimal deterministic pool over the engine's three boxes.

    Mirrors PidAllocator and AsidAllocator policy (lowest-free, no randomness).
    """

    def __init__(self, capacity: int = 3) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._live: List[int] = []

    def alloc(self) -> int:
        """Allocate lowest free box; exhausted -> RuntimeError."""
        if len(self._live) >= self.capacity:
            raise RuntimeError(f"box space exhausted ({self.capacity} live)")
        for candidate in range(self.capacity):
            if candidate not in self._live:
                self._live.append(candidate)
                return candidate
        raise AssertionError("unreachable: live < capacity but no free box found")

    def free(self, box: int) -> None:
        """Release an allocated box; not live -> KeyError."""
        if box not in self._live:
            raise KeyError(f"box {box} is not live (double-free is a caller bug)")
        self._live.remove(box)

    def live(self) -> List[int]:
        """Live box IDs, sorted ascending."""
        return sorted(self._live)


def _lowest_free(live: List[int], capacity: int) -> int:
    """Compute the lowest free integer in [0, capacity).

    Proctab.admit is the independent oracle for this prediction — any drift
    between this prediction and PidAllocator.alloc() raises a loud ValueError
    in admit, never silent divergence.
    """
    for candidate in range(capacity):
        if candidate not in live:
            return candidate
    raise RuntimeError(f"pid space exhausted ({capacity} live)")


def spawn(
    proctab: Proctab,
    captab: CapTable,
    devtab: Devtab,
    box_allocator: BoxAllocator,
    *,
    caps: int = 0,
    pt_base_word: int = 0,
    parent_pid: Optional[int] = None,
    driver: Optional[Driver] = None,
    device: Optional[DeviceDescriptor] = None,
) -> ProcessDescriptor:
    """Cross-module spawn integration.

    Validates all preconditions atomically, then allocates box + asid + pid,
    admits to process table, initializes capabilities, and binds device driver
    if specified.
    """
    # 1. Pre-flight: unbound hook checks (no mutation)
    asid_allocator = get_asid_allocator()
    if asid_allocator is None:
        raise RuntimeError("no asid allocator bound: refusing to spawn")

    granter_mask = get_granter_mask()
    if granter_mask is None:
        raise RuntimeError("no granter mask bound: refusing to spawn")

    # 2. Pre-flight: granter must hold CAP_SPAWN (who may spawn rule)
    if not cap_implies(granter_mask, CAP_SPAWN):
        raise PermissionError(
            f"granter lacks CAP_SPAWN capability (held mask {granter_mask:#x})"
        )

    # 3. Pre-flight: requested caps must be subset of granter mask (no amplification)
    if not isinstance(caps, int) or isinstance(caps, bool) or caps < 0:
        raise ValueError(f"caps must be a non-negative int, got {caps!r}")
    deficit = caps & ~granter_mask
    if deficit != 0:
        deficit_names = cap_names(deficit)
        names_str = ", ".join(deficit_names) if deficit_names else f"{deficit:#x}"
        raise PermissionError(
            f"spawn refused: granter lacks requested capability {names_str} (deficit mask {deficit:#x})"
        )

    # 4. Pre-flight: device legs
    if (driver is None) ^ (device is None):
        raise ValueError("driver and device must be provided together or both None")

    if driver is not None and device is not None:
        if not (caps & CAP_DEV_MMIO):
            raise PermissionError(
                "binding a device driver requires CAP_DEV_MMIO"
            )
        if device.name not in devtab.devices:
            raise ValueError(f"device {device.name!r} is not registered in devtab")
        clash = devtab.conflicts(device.window_lo, device.window_hi)
        if clash:
            raise DeviceConflict(
                f"window [{device.window_lo},{device.window_hi}) for {device.name} overlaps "
                f"{[(b.driver, b.window_lo, b.window_hi) for b in clash]}"
            )
        already = [b for b in devtab.bindings if b.device == device.name]
        if already:
            raise DeviceConflict(
                f"device {device.name} already bound to {already[0].driver}"
            )

    # 5. Mutate in order: box -> asid -> desc -> admit -> caps -> devtab
    box = box_allocator.alloc()
    try:
        asid = asid_allocator.alloc()
        try:
            predicted_pid = _lowest_free(proctab.pids.live(), proctab.pids.capacity)
            space = AddressSpace(asid=asid, pt_base_word=pt_base_word)
            desc = ProcessDescriptor(
                pid=predicted_pid,
                asid=asid,
                box=box,
                caps=0,
                parent_pid=parent_pid,
                meta={"aspace": space},
            )
            proctab.admit(desc)
        except Exception:
            asid_allocator.free(asid)
            raise
    except Exception:
        box_allocator.free(box)
        raise

    # 7. Every post-admit operation is guaranteed infallible by the pre-flight in 2–4.
    captab.grants[desc.pid] = CAP_NONE
    desc.caps = captab.grant(desc.pid, caps)

    if driver is not None and device is not None:
        desc.meta["binding"] = devtab.bind(driver, device, pid=desc.pid)

    return desc
