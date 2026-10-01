#!/usr/bin/env python3
"""
geos_aspace — per-process address spaces (Glyph OS skeleton, OS-level).

WHY THIS EXISTS (the Linux gap it closes)
    GH-17 gave GeOS ONE page table (base word 1536, 256 PTEs of 256-word pages)
    and GH-25 gave it spatial Hilbert frames. What Linux has and GeOS does NOT
    is an ADDRESS SPACE PER PROCESS: an object you can create, switch, fork and
    destroy, with an identity (ASID) so a switch is a word write rather than a
    page-table rebuild, and so two processes can hold the same virtual page
    number without colliding.

    Today "isolation" is box bounds (BOX0/BOX1/BOX2 lo/hi MMIO words) — a
    contiguous range check, not translation. This module defines the contract
    for translation-per-process. It is the single biggest structural difference
    between GeOS and Linux.

ENGINE FACTS THIS MODULE MUST MATCH (do not drift — verify_os_skel leg 5 checks)
    tools/glyph_isa_v2.py:
        PAGE_WORDS           = 256     # 256 words (1024 bytes) per page
        PAGE_TABLE_BASE_WORD = 1536    # words 1536..1792 -> 256 PTEs
        PTE_V=0x1  PTE_W=0x2  PTE_U=0x4  PTE_PIX=0x8  PTE_HILB=0x10
        pfn                  = pte >> 8          # pfn occupies bits 8+
        vpn                  = (vaddr >> 8) & 0xFF   # 256 VPNs per space
        MODE_SUPER=0  MODE_USER=1

DESIGN INVARIANTS
    I1  Translation is total: every vaddr maps to (vpn, offset) with no
        ambiguity, and offset < PAGE_WORDS always.
    I2  Privilege is checked at translation, not at the box fence:
        mode==USER requires PTE_U; a store additionally requires PTE_W.
        (Mirrors engine lines 644 / 710 — a USER store to a non-U page faults.)
    I3  An ASID is an identity, not a location: two live spaces never share one.
    I4  Switching an address space writes ONE word (PAGE_TABLE_ADDR, MMIO
        0x814C). A switch that requires a rebuild is a design regression.
    I5  No space is destroyed while a live task references its asid (refcount).

BOUNDARY MAP
    geos_proctab.ProcessDescriptor.asid ──references──> AddressSpace.asid
    AddressSpace.switch()  --writes-->  PAGE_TABLE_ADDR (BOX_MMIO_BASE+0x4C)
    AddressSpace.map()     --writes-->  page_table_base + vpn
    GeosEmitter / observation plane    (unchanged; this module never writes images)

PHASE STATUS
    Phase 1 (structure) : done — types, signatures, compiles, stdlib-only
    Phase 2 (lock)      : done — invariants + engine-fact pinning
    Phase 3 (population): in progress (step 3: release + AsidAllocator wiring)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

__all__ = [
    "PAGE_WORDS",
    "PAGE_SHIFT",
    "VPN_COUNT",
    "VPN_MASK",
    "PTE_V",
    "PTE_W",
    "PTE_U",
    "PTE_PIX",
    "PTE_HILB",
    "PFN_SHIFT",
    "MODE_SUPER",
    "MODE_USER",
    "PAGE_TABLE_ADDR",
    "PAGE_TABLE_TAG",
    "validate_page_table",
    "PageTableValidationError",
    "split_vaddr",
    "pte_pack",
    "pte_unpack",
    "permits_access",
    "AsidAllocator",
    "AddressSpace",
    "stamp_page_table",
]

# --- engine-pinned constants (verify leg 5 asserts these against the source) --
PAGE_WORDS = 256          # words per page (engine: glyph_isa_v2.PAGE_WORDS)
PAGE_SHIFT = 8            # vpn = vaddr >> 8 (log2(PAGE_WORDS))
VPN_COUNT = 256           # 256 entries per page table
VPN_MASK = 0xFF
PFN_SHIFT = 8             # pfn = pte >> 8
MODE_SUPER = 0
MODE_USER = 1

PTE_V = 0x1
PTE_W = 0x2
PTE_U = 0x4
PTE_PIX = 0x8
PTE_HILB = 0x10

PAGE_TABLE_ADDR = 0x8000 + 0x4C   # engine: BOX_MMIO_BASE + 0x4C (GH-17)
PAGE_TABLE_TAG = 0x505447        # DEFECT-23-ROOT Option 1 container tag (ASCII "PTG")

_FLAG_MASK = PTE_V | PTE_W | PTE_U | PTE_PIX | PTE_HILB


def stamp_page_table(memory: Any, pt_base: int, tag: int = PAGE_TABLE_TAG) -> None:
    """Stamp the page-table container tag at pt_base - 1 (DEFECT-23-ROOT Option 1)."""
    tag_addr = pt_base - 1
    if 0 <= tag_addr < len(memory):
        memory[tag_addr] = tag


class PageTableValidationError(ValueError):
    """Raised when a page table slot fails validation."""
    pass


def _read_table_word(memory: Any, addr: int) -> int:
    """Helper to read a word from a list, dict, or image array."""
    if hasattr(memory, "shape"):
        if len(memory.shape) == 3:
            h, w, _ = memory.shape
            if 0 <= addr < h * w:
                r, g, b = memory[addr // w, addr % w]
                return (int(r) << 16) | (int(g) << 8) | int(b)
            return 0
        if len(memory.shape) == 2:
            h, w = memory.shape
            if 0 <= addr < h * w:
                return int(memory[addr // w, addr % w])
            return 0
        if len(memory.shape) == 1:
            if 0 <= addr < len(memory):
                return int(memory[addr])
            return 0
    if isinstance(memory, dict):
        return int(memory.get(addr, 0))
    if 0 <= addr < len(memory):
        return int(memory[addr])
    return 0


def validate_page_table(
    memory: Any,
    pt_base: int,
    max_frame: int = 65535,
) -> dict[str, int]:
    """Validate that every slot in [pt_base, pt_base+256) is well-formed.

    Checks:
    - slot == 0: unmapped (OK).
    - otherwise:
        - pfn = pte >> 8 must satisfy pfn <= max_frame.
        - (pte & 0xFF) must have no bits outside _FLAG_MASK (0x1F).

    Any violation raises PageTableValidationError naming slot index, word, and why.
    Returns summary dict: {'slots_checked': 256, 'violations': 0, 'mapped_slots': count}.
    """
    slots_checked = 256
    mapped_slots = 0
    for vpn in range(256):
        addr = pt_base + vpn
        pte = _read_table_word(memory, addr)
        if pte == 0:
            continue
        pfn = pte >> 8
        if pfn > max_frame:
            raise PageTableValidationError(
                f"Page table slot={vpn} at {addr:#x} word={pte:#010x}: "
                f"pfn={pfn:#x} ({pfn}) exceeds max_frame={max_frame:#x} ({max_frame})"
            )
        flags = pte & 0xFF
        if (flags & ~_FLAG_MASK) != 0:
            raise PageTableValidationError(
                f"Page table slot={vpn} at {addr:#x} word={pte:#010x}: "
                f"flags={flags:#04x} has bits outside _FLAG_MASK={_FLAG_MASK:#04x}"
            )
        mapped_slots += 1

    return {
        "slots_checked": slots_checked,
        "violations": 0,
        "mapped_slots": mapped_slots,
    }


# --- MMIO sink injection mechanism (OS-SKEL-R2 Phase 3 Step 2) ---------------
MmioSink = Callable[[int, int], None]      # (addr, word) -> None
_mmio_sink: Optional[MmioSink] = None


def set_mmio_sink(sink: Optional[MmioSink]) -> None:
    """Bind the engine's single-word MMIO write path; None unbinds."""
    global _mmio_sink
    if sink is not None and not callable(sink):
        raise TypeError(f"sink must be callable or None, got {type(sink).__name__}")
    _mmio_sink = sink


def get_mmio_sink() -> Optional[MmioSink]:
    """Current sink (None when unbound) — for tests and teardown."""
    return _mmio_sink


# --- ASID allocator injection mechanism (OS-SKEL-R2 Phase 3 Step 3) ----------
_asid_allocator: Optional[AsidAllocator] = None


def set_asid_allocator(allocator: Optional[AsidAllocator]) -> None:
    """Bind the allocator whose asids this module's spaces are drawn from; None unbinds."""
    global _asid_allocator
    if allocator is not None and not isinstance(allocator, AsidAllocator):
        raise TypeError(f"allocator must be AsidAllocator or None, got {type(allocator).__name__}")
    _asid_allocator = allocator


def get_asid_allocator() -> Optional[AsidAllocator]:
    """Current bound allocator (None when unbound) — for tests and teardown."""
    return _asid_allocator


# --- Space source injection mechanism (OS-SKEL-R3 Step 9) --------------------
SpaceSource = Callable[[int], Optional["AddressSpace"]]
_space_source: Optional[SpaceSource] = None


def set_space_source(source: Optional[SpaceSource]) -> None:
    """Bind the space resolver (asid -> AddressSpace | None); None unbinds."""
    global _space_source
    if source is not None and not callable(source):
        raise TypeError(f"source must be callable or None, got {type(source).__name__}")
    _space_source = source


def get_space_source() -> Optional[SpaceSource]:
    """Current space source (None when unbound) — for tests and teardown."""
    return _space_source


def drop_reference(asid: int) -> int:
    """Resolve space through bound source, decrement refcount, return remaining count."""
    source = get_space_source()
    if source is None:
        raise KeyError(f"unknown asid {asid}")
    space = source(asid)
    if space is None:
        raise KeyError(f"unknown asid {asid}")
    return space.release()


def split_vaddr(vaddr: int) -> Tuple[int, int]:
    """Decompose a virtual address into (vpn, offset). IMPLEMENTED (pure).

    I1: total and unambiguous. Raises on a negative address rather than
    silently wrapping — a negative vaddr is a caller bug, not a page 255 hit.
    """
    if not isinstance(vaddr, int):
        raise TypeError(f"vaddr must be int, got {type(vaddr).__name__}")
    if vaddr < 0:
        raise ValueError(f"vaddr must be non-negative, got {vaddr}")
    vpn = (vaddr >> PAGE_SHIFT) & VPN_MASK
    offset = vaddr & (PAGE_WORDS - 1)
    return (vpn, offset)


def pte_pack(pfn: int, flags: int) -> int:
    """Build a PTE word: pfn in bits 8+, flags in bits 0..4. IMPLEMENTED (pure).

    Rejects a pfn that does not fit the field, and unknown flag bits, so a
    malformed PTE cannot be written into a page table by this module.
    """
    if not isinstance(pfn, int) or pfn < 0:
        raise ValueError(f"pfn must be a non-negative int, got {pfn!r}")
    if not isinstance(flags, int) or flags < 0:
        raise ValueError(f"flags must be a non-negative int, got {flags!r}")
    unknown = flags & ~_FLAG_MASK
    if unknown:
        raise ValueError(f"unknown PTE flag bits: {unknown:#x} (engine knows {_FLAG_MASK:#x})")
    return (pfn << PFN_SHIFT) | flags


def pte_unpack(pte: int) -> Tuple[int, int]:
    """Split a PTE word into (pfn, flags). IMPLEMENTED (pure)."""
    if not isinstance(pte, int) or pte < 0:
        raise ValueError(f"pte must be a non-negative int, got {pte!r}")
    return (pte >> PFN_SHIFT, pte & _FLAG_MASK)


def permits_access(pte: int, mode: int, is_store: bool) -> bool:
    """The translation-time permission check. IMPLEMENTED (pure).

    This mirrors the engine's own check (glyph_isa_v2 lines 644 / 710):
        load  : PTE_V                       (+ PTE_U when mode == USER)
        store : PTE_V and PTE_W             (+ PTE_U when mode == USER)

    Kept as a pure function so the policy is testable in isolation and can be
    compared against the engine's behaviour (verify leg 8, an integration leg
    the builder fills in — see the skeleton doc).
    """
    if mode not in (MODE_SUPER, MODE_USER):
        raise ValueError(f"unknown mode: {mode!r} (expected MODE_SUPER or MODE_USER)")
    _, flags = pte_unpack(pte)
    if not (flags & PTE_V):
        return False
    if is_store and not (flags & PTE_W):
        return False
    if mode == MODE_USER and not (flags & PTE_U):
        return False
    return True


class AsidAllocator:
    """Deterministic lowest-free ASID allocation. IMPLEMENTED (pure policy).

    Determinism matters: an asid is part of a process's identity, so the same
    sequence of spawn/exit must yield the same asids across runs (this repo
    treats reproducibility as the receipt discipline). No randomness, no
    recycling heuristics — lowest free wins.

    NOTE: allocation here is pure accounting. Binding an asid to an entry in a
    real page table / MMIO word is Phase 3.
    """

    def __init__(self, capacity: int = 256) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._live: List[int] = []

    def alloc(self) -> int:
        if len(self._live) >= self.capacity:
            raise RuntimeError(f"asid space exhausted ({self.capacity} live)")
        for candidate in range(self.capacity):
            if candidate not in self._live:
                self._live.append(candidate)
                return candidate
        raise AssertionError("unreachable: live < capacity but no free asid")

    def free(self, asid: int) -> None:
        if asid not in self._live:
            raise KeyError(f"asid {asid} is not live (double-free is a caller bug)")
        self._live.remove(asid)

    def live(self) -> List[int]:
        """Live asids, ascending. IMPLEMENTED (pure)."""
        return sorted(self._live)


@dataclass
class AddressSpace:
    """A per-process virtual address space.

    Fields (LOCKED):
        asid         : identity from AsidAllocator — stable for the space's life
        pt_base_word : first word of this space's page table in RAM
        satp_word    : the single word written to PAGE_TABLE_ADDR on switch (I4)
        refcount     : live references; teardown is refused at refcount > 0 (I5)
        entries      : vpn -> pte, the in-memory model used by plan/map (Phase 3)

    PHASE 3 TODO (builder) — stubs by design:
        map(vpn, pfn, flags) : validate vpn range, write entries[vpn]; refuse a
            remap of a live entry without an explicit unmap (silent aliasing is
            how two processes end up sharing a frame by accident).
            Returns the previous entry or None.
        unmap(vpn)           : clear the entry; refuse if the entry is PTE_HILB
            and a live frame binding exists (GH-25 spatial frames are shared).
        switch()             : write satp_word to PAGE_TABLE_ADDR (ONE word, I4).
        clone_for_fork()     : copy entries into a fresh asid, mark writable
            pages copy-on-write rather than deep-copying frames.
        release()            : decrement refcount; at 0, free the asid.
    """

    asid: int
    pt_base_word: int
    satp_word: int = 0
    refcount: int = 1
    entries: Dict[int, int] = field(default_factory=dict)
    faults: List[Tuple[int, int, int]] = field(default_factory=list)  # (vaddr, mode, is_store)

    def __post_init__(self) -> None:
        if not (0 <= self.asid < 256):
            raise ValueError(f"asid out of range: {self.asid}")
        if self.pt_base_word < 0:
            raise ValueError("pt_base_word must be non-negative")
        if self.satp_word == 0:
            # Default encoding: base word in bits 8+, asid in bits 0..7.
            # Chosen to mirror the PTE layout (pfn<<8|flags) so the whole
            # substrate keeps one bit-packing convention.
            self.satp_word = (self.pt_base_word << PFN_SHIFT) | (self.asid & 0xFF)

    # --- Phase 3 stubs (declared shape only) ------------------------------
    def map(self, vpn: int, pfn: int, flags: int) -> Optional[int]:
        # validate vpn range: 0 <= vpn < 256 (VPN capacity is 256)
        if not isinstance(vpn, int) or isinstance(vpn, bool) or not (0 <= vpn < VPN_COUNT):
            raise ValueError(f"vpn out of range: {vpn} (expected 0 <= vpn < {VPN_COUNT})")
        # refuse remap of a live entry without explicit unmap
        if vpn in self.entries:
            raise RuntimeError(f"remap of live vpn {vpn} without unmap")
        self.entries[vpn] = pte_pack(pfn, flags)
        return None

    def unmap(self, vpn: int) -> Optional[int]:
        return self.entries.pop(vpn, None)

    def switch(self) -> int:
        if _mmio_sink is None:
            raise RuntimeError("no MMIO sink bound: refusing to report a switch that wrote nothing")
        _mmio_sink(PAGE_TABLE_ADDR, self.satp_word)
        return self.satp_word

    def stamp_window(self, memory: Any, tag: int = PAGE_TABLE_TAG) -> None:
        """Stamp the container tag at (pt_base - 1) in engine memory (DEFECT-23-ROOT Option 1)."""
        pt_base = self.satp_word if self.satp_word != 0 else self.pt_base_word
        stamp_page_table(memory, pt_base, tag=tag)

    def clone_for_fork(self, allocator: AsidAllocator) -> "AddressSpace":
        # TODO(Phase 3): copy-on-write clone under a fresh asid.
        child_asid = allocator.alloc()
        return AddressSpace(asid=child_asid, pt_base_word=self.pt_base_word)

    def release(self) -> int:
        """Decrement refcount; return the remaining count. (Phase 3 Step 3).

        Phase 3 wires the asid free + page-table teardown; the accounting rule
        (refuse below zero) is implemented here because it is the invariant.
        """
        if self.refcount <= 0:
            raise RuntimeError(f"aspace asid={self.asid} released more times than acquired")
        if self.refcount == 1:
            allocator = get_asid_allocator()
            if allocator is None:
                raise RuntimeError("no asid allocator bound: refusing to report a release that freed nothing")
            allocator.free(self.asid)
            self.refcount = 0
            return 0
        self.refcount -= 1
        return self.refcount

    def pin(self) -> int:
        """Take an extra reference (IMPLEMENTED, pure)."""
        self.refcount += 1
        return self.refcount


if __name__ == "__main__":  # Phase-1 smoke: shape, not behaviour.
    alloc = AsidAllocator()
    a = AddressSpace(asid=alloc.alloc(), pt_base_word=1536)
    b = AddressSpace(asid=alloc.alloc(), pt_base_word=1792)
    print(f"asids live={alloc.live()}  a.satp={a.satp_word:#x}  b.satp={b.satp_word:#x}")
    vpn, off = split_vaddr(0x03FF)
    print(f"split_vaddr(0x03FF) = vpn {vpn}, offset {off}")
    pte = pte_pack(7, PTE_V | PTE_W | PTE_U)
    print(f"pte={pte:#x} unpack={pte_unpack(pte)} permits(user,store)={permits_access(pte, MODE_USER, True)}")
