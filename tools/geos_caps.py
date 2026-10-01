#!/usr/bin/env python3
"""
geos_caps — identity and capability model (Glyph OS skeleton, OS-level).

WHY THIS EXISTS (the Linux gap it closes)
    GeOS has exactly one privilege distinction: MODE_SUPER vs MODE_USER
    (glyph_isa_v2 lines 102-103), latched by the kernel at MODE_LATCH_ADDR
    (BOX_MMIO_BASE+0x00). That is an all-or-nothing bit — Linux has uid/gid
    plus capabilities, and the reason is that "user mode" alone cannot express
    "may write the filesystem but may not open a network endpoint".

    Concretely: BK-13 (net), GH-20 (pixel-FS v2), GH-22 (driver ABI) and
    BK-6 (boot integrity) all introduce privileged operations, and today any
    user task in a box that can reach the relevant MMIO word can perform them.
    There is no way to say "this task may do X and not Y".

DESIGN INVARIANTS
    I1  Capabilities are a monotone lattice: holding a cap implies exactly the
        caps it names, nothing transitive, no implicit hierarchy. A check that
        cannot express denial is not a check.
    I2  Denial is loud and named: every gate() result carries the missing cap
        (or the identity mismatch) — never a bare False.
    I3  Capability checks are pure: gate() does not mutate held caps, does not
        touch a process table, and is safe to call from a planner.
    I4  Capability sets serialise canonically (sorted, stable) so a grant is
        reproducible and hashable like every other receipt in this repo.
    I5  The root identity is explicit, not implied: uid 0 is privileged ONLY
        when CAP_ROOT is held. There is no silent superuser.

BOUNDARY MAP
    geos_proctab.ProcessDescriptor.caps ──held caps──> gate()
                                                          |
    syscall dispatch (GH-6/GH-18/GH-21) ────────────────> decision
    geos_devtab (MMIO window grant) ────────────────────> requires CAP_DEV_MMIO
    geos_archive / geos_registry writes ────────────────> requires CAP_OBSERVE

PHASE STATUS
    Phase 1 (structure) : done    Phase 2 (lock): done
    Phase 3 (population): in progress (step 4: grant/revoke/held)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

__all__ = [
    "CAP_NONE",
    "CAP_FS_WRITE",
    "CAP_FS_ADMIN",
    "CAP_SPAWN",
    "CAP_KILL",
    "CAP_NET",
    "CAP_DEV_MMIO",
    "CAP_OBSERVE",
    "CAP_BOOT_VERIFY",
    "CAP_ROOT",
    "CAP_NAMES",
    "cap_mask",
    "cap_names",
    "Identity",
    "Decision",
    "gate",
    "cap_implies",
    "canonical_caps",
]

# --- capability bits --------------------------------------------------------
# Each bit is grounded in a real privileged surface that already exists:
CAP_NONE = 0
CAP_FS_WRITE = 1 << 0     # GH-8/8b/20 pixel-FS writes, BK-7 grow, BK-9 paths
CAP_FS_ADMIN = 1 << 1     # rename/unlink/refcount ops (GH-20)
CAP_SPAWN = 1 << 2        # GH-7 multiprocessing / GH-9 loader (fork+exec)
CAP_KILL = 1 << 3         # BK-3 signals, SIG_KILL delivery
CAP_NET = 1 << 4          # BK-13 net_send/net_recv (SYS 18/19)
CAP_DEV_MMIO = 1 << 5     # GH-22 device driver ABI: request an MMIO window
CAP_OBSERVE = 1 << 6      # GH-24/26.5 observation plane, archive/registry reads
CAP_BOOT_VERIFY = 1 << 7  # BK-6 integrity check: read the code-region hash word
CAP_ROOT = 1 << 8         # explicit privilege, never implied by uid (I5)

CAP_NAMES: Dict[int, str] = {
    CAP_FS_WRITE: "fs_write",
    CAP_FS_ADMIN: "fs_admin",
    CAP_SPAWN: "spawn",
    CAP_KILL: "kill",
    CAP_NET: "net",
    CAP_DEV_MMIO: "dev_mmio",
    CAP_OBSERVE: "observe",
    CAP_BOOT_VERIFY: "boot_verify",
    CAP_ROOT: "root",
}


def cap_mask(required: Iterable[int]) -> int:
    """OR a set of capability bits into a mask. IMPLEMENTED (pure).

    Raises on an unknown bit so a typo cannot silently become a no-op grant.
    """
    mask = 0
    for bit in required:
        if bit not in CAP_NAMES:
            raise ValueError(f"unknown capability bit: {bit!r}")
        mask |= bit
    return mask


def cap_names(mask: int) -> List[str]:
    """Human-readable names for a mask, sorted. IMPLEMENTED (pure, I4)."""
    if mask < 0:
        raise ValueError("capability mask must be non-negative")
    return sorted(name for bit, name in CAP_NAMES.items() if mask & bit)


def cap_implies(held: int, required: int) -> bool:
    """Does `held` satisfy `required`? IMPLEMENTED (pure, I1: no transitivity).

    CAP_ROOT is deliberately NOT a wildcard — a wildcard would make every other
    bit unverifiable (you could never prove a denial). Root privileges are
    granted by holding the concrete bits; CAP_ROOT marks that fact.
    """
    if held < 0 or required < 0:
        raise ValueError("capability masks must be non-negative")
    return (held & required) == required


@dataclass(frozen=True)
class Identity:
    """Who is asking. LOCKED fields: uid, gid, label.

    uid/gid mirror POSIX naming because BK-11/BK-21 (coreutils, POSIX shim)
    will need to speak this vocabulary; `label` is the GeOS-native tag used in
    receipts and the observation plane (writer attribution, DEFECT-20).
    """

    uid: int = 1
    gid: int = 1
    label: str = "task"

    def __post_init__(self) -> None:
        if self.uid < 0 or self.gid < 0:
            raise ValueError("uid/gid must be non-negative")


@dataclass(frozen=True)
class Decision:
    """Result of a capability gate. LOCKED fields: allowed, missing, reason.

    I2: a denial always names what was missing. `missing` is a mask (0 when
    allowed) and `reason` is a stable string suitable for a receipt line.
    """

    allowed: bool
    missing: int = 0
    reason: str = ""


def gate(identity: Identity, held: int, required: int) -> Decision:
    """Decide whether `identity` holding `held` may perform `required`.

    IMPLEMENTED (pure, I2 + I3). Order of checks:
        1. required == 0            -> allowed (no capability needed)
        2. held implies required    -> allowed
        3. otherwise                -> denied, `missing` = the deficit mask

    Never raises for a well-formed mask, never mutates its inputs, and names
    the deficit rather than returning a bare boolean.
    """
    if not isinstance(identity, Identity):
        raise TypeError(f"identity must be Identity, got {type(identity).__name__}")
    if held < 0 or required < 0:
        raise ValueError("capability masks must be non-negative")

    if required == CAP_NONE:
        return Decision(True, 0, "no capability required")

    if cap_implies(held, required):
        return Decision(True, 0, f"held {cap_names(required)}")

    missing = required & ~held
    return Decision(
        False,
        missing,
        f"missing {cap_names(missing)} (denied for {identity.label} uid={identity.uid})",
    )


def canonical_caps(held: int) -> Tuple[str, ...]:
    """Canonical serialisation of a cap set (sorted names). IMPLEMENTED (I4)."""
    return tuple(cap_names(held))


# --- granter mask injection mechanism (OS-SKEL-R2 Phase 3 Step 4) ------------
_granter_mask: Optional[int] = None
_ALL_CAPS_MASK: int = 0
for _b in CAP_NAMES:
    _ALL_CAPS_MASK |= _b


def set_granter_mask(mask: Optional[int]) -> None:
    """Bind the capability mask the granting authority itself holds; None unbinds."""
    global _granter_mask
    if mask is not None:
        if not isinstance(mask, int) or isinstance(mask, bool):
            raise TypeError(f"granter mask must be int or None, got {type(mask).__name__}")
        if mask < 0:
            raise ValueError(f"granter mask must be non-negative, got {mask}")
        if mask & ~_ALL_CAPS_MASK:
            raise ValueError(f"unknown capability bit in mask: {mask & ~_ALL_CAPS_MASK:#x}")
    _granter_mask = mask


def get_granter_mask() -> Optional[int]:
    """Currently bound granter mask (None when unbound) — for tests and teardown."""
    return _granter_mask


@dataclass
class CapTable:
    """Per-process capability table (Phase 3 stub).

    PHASE 3 TODO (builder) — bodies deliberately stubbed:
        grant(pid, mask)  : add bits; refuse if pid unknown; return new mask.
        revoke(pid, mask) : remove bits; refuse to revoke CAP_ROOT without an
            explicit `force=True` (revoking root silently is how a privileged
            task becomes an unkillable one).
        held(pid)         : current mask, or raise KeyError.
    The table must never grant a cap the caller does not itself hold (no
    privilege amplification) — that rule is the reason this is a table and not
    a dict of ints.
    """

    grants: Dict[int, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.grants is None:
            self.grants = {}

    def grant(self, pid: int, mask: int) -> int:
        if not isinstance(mask, int) or isinstance(mask, bool) or mask < 0:
            raise ValueError(f"mask must be a non-negative int, got {mask!r}")
        if pid not in self.grants:
            raise KeyError(pid)
        granter = get_granter_mask()
        if granter is None:
            raise RuntimeError("no granter mask bound: refusing to grant without an amplification check")
        deficit = mask & ~granter
        if deficit != 0:
            missing_names = cap_names(deficit)
            missing_str = ", ".join(missing_names) if missing_names else f"{deficit:#x}"
            raise PermissionError(
                f"grant refused for pid {pid}: granter lacks capability {missing_str} (deficit mask {deficit:#x})"
            )
        self.grants[pid] |= mask
        return self.grants[pid]

    def revoke(self, pid: int, mask: int, force: bool = False) -> int:
        if not isinstance(mask, int) or isinstance(mask, bool) or mask < 0:
            raise ValueError(f"mask must be a non-negative int, got {mask!r}")
        if pid not in self.grants:
            raise KeyError(pid)
        if (mask & CAP_ROOT) and not force:
            raise PermissionError(
                f"refusing to revoke CAP_ROOT for pid {pid} without force=True"
            )
        self.grants[pid] &= ~mask
        return self.grants[pid]

    def held(self, pid: int) -> int:
        if pid not in self.grants:
            raise KeyError(pid)
        return self.grants[pid]


if __name__ == "__main__":  # Phase-1 smoke: shape, not behaviour.
    idn = Identity(uid=1, gid=1, label="shell")
    held = cap_mask([CAP_FS_WRITE, CAP_OBSERVE])
    for need in (CAP_FS_WRITE, CAP_NET):
        d = gate(idn, held, need)
        print(f"need={cap_names(need)} -> allowed={d.allowed} {d.reason}")
