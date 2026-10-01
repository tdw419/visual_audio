"""
GlyphDispatchHost -- the host-side hook the Route B offload loop calls on each
servicing turn.

Route B (`tools/qemu_gpu_offload.py :: run_with_offload`) runs RISC-V on the GPU
and hands the host a servicing turn whenever the guest yields (state
`halted == 2`): the loop walks the VirtIO queue, then resumes the core. This
class is the second thing the host does on that turn -- look at the glyph
dispatch request struct in guest RAM and, if BUSY is set, run the kernel and
write the digest back.

It is a thin wrapper over `GlyphDispatcher` that adds per-turn accounting and a
single `on_yield()` entry point. It is import-clean and unit-testable with a
`MockGpuRam`; the wiring into `run_with_offload` lives in
`run_with_glyph_dispatch.py`.
"""

import sys
from pathlib import Path
from typing import Optional

# TEST-COL-1 (2026-09-13): package-relative imports instead of absolute `src.*`
# imports. The absolute form needed `glyph_dispatch/` on sys.path[0], which
# shadowed the repo's top-level `src` package process-wide.
from ..dispatch.dispatcher import GlyphDispatcher
from ..dispatch.request_struct import REQUEST_STRUCT_BASE, FLAG_ERROR


class GlyphDispatchHost:
    """Per-servicing-turn glyph dispatch hook for the Route B loop."""

    def __init__(self, ram, glyph_db_path: Optional[str] = None):
        self.ram = ram
        self.dispatcher = GlyphDispatcher(
            ram, state_buffer=None, glyph_db_path=glyph_db_path)
        self.offload_count = 0
        self.error_count = 0

    def on_yield(self, ram=None) -> bool:
        """Call once per host servicing turn.

        Returns True iff a glyph dispatch request was pending (BUSY set) and was
        processed this turn -- error dispatches count as processed. Returns
        False, touching nothing, when there is no pending request, so a
        VirtIO-only yield is undisturbed.
        """
        if not self.dispatcher.check_dispatch():
            return False
        flags = (ram or self.ram).read_u32(REQUEST_STRUCT_BASE)
        if flags & FLAG_ERROR:
            self.error_count += 1
        else:
            self.offload_count += 1
        return True

    def stats(self) -> dict:
        return {
            "glyph_offloads": self.offload_count,
            "glyph_errors": self.error_count,
        }
