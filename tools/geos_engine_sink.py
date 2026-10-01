#!/usr/bin/env python3
"""
geos_engine_sink — Engine-backed MMIO sink for AddressSpace.switch (OS-SKEL-R3 Step 8).

Wires AddressSpace.switch() to the real GlyphCPUv2 engine memory at PAGE_TABLE_ADDR
(BOX_MMIO_BASE + 0x4C = 0x804C, word 8211).

INVARIANTS & CONTRACT:
    - EngineMmioSink is a callable (addr: int, word: int) -> None bound via
      tools.geos_aspace.set_mmio_sink(EngineMmioSink(engine)).
    - The store is engine.memory[addr >> 2] = word into the engine's real word-array.
    - Validation before any store (loud and named, never silent):
        * addr must be an int (reject bool) in [BOX_MMIO_BASE, BOX_MMIO_BASE + 0x400);
          otherwise raises ValueError naming the address.
        * word must be an int (reject bool) in [0, 0xFFFFFFFF];
          otherwise raises ValueError.
        * if len(engine.memory) <= addr >> 2, raises RuntimeError naming the address
          and capacity rather than resizing or ignoring.
    - Tracks sink.writes (int count) and sink.last (Optional[Tuple[int, int]]).
    - Module-level helpers bind_engine(engine) and unbind_engine() ensure leak-free
      binding and teardown across tests.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from tools.geos_aspace import PAGE_TABLE_ADDR, set_mmio_sink
from tools.glyph_isa_v2 import BOX_MMIO_BASE

__all__ = [
    "BOX_MMIO_BASE",
    "BOX_MMIO_WINDOW_BYTES",
    "EngineMmioSink",
    "bind_engine",
    "unbind_engine",
]

BOX_MMIO_WINDOW_BYTES = 0x400  # 1024 bytes (256 words)


class EngineMmioSink:
    """Callable MMIO sink storing words directly into an engine's real memory array."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.writes: int = 0
        self.last: Optional[Tuple[int, int]] = None

    def __call__(self, addr: int, word: int) -> None:
        if isinstance(addr, bool) or not isinstance(addr, int):
            raise ValueError(f"addr must be an int (got {type(addr).__name__}: {addr!r})")

        if not (BOX_MMIO_BASE <= addr < BOX_MMIO_BASE + BOX_MMIO_WINDOW_BYTES):
            raise ValueError(
                f"addr 0x{addr:X} ({addr}) outside BOX-MMIO window "
                f"[0x{BOX_MMIO_BASE:X}, 0x{BOX_MMIO_BASE + BOX_MMIO_WINDOW_BYTES:X})"
            )

        if isinstance(word, bool) or not isinstance(word, int):
            raise ValueError(f"word must be an int (got {type(word).__name__}: {word!r})")

        if not (0 <= word <= 0xFFFFFFFF):
            raise ValueError(f"word {word} out of range [0, 0xFFFFFFFF]")

        word_idx = addr >> 2
        if len(self.engine.memory) <= word_idx:
            raise RuntimeError(
                f"engine memory too small ({len(self.engine.memory)} words) "
                f"to hold MMIO word {word_idx} (addr 0x{addr:X})"
            )

        self.engine.memory[word_idx] = word
        self.writes += 1
        self.last = (addr, word)


def bind_engine(engine: Any) -> EngineMmioSink:
    """Instantiate an EngineMmioSink for engine, bind it via set_mmio_sink, and return it."""
    sink = EngineMmioSink(engine)
    set_mmio_sink(sink)
    return sink


def unbind_engine() -> None:
    """Unbind the MMIO sink via set_mmio_sink(None)."""
    set_mmio_sink(None)
