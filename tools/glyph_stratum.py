"""glyph_stratum.py — CLAIM QUEUE item 31: GPU-first spatial window coordinator
(the GlyphStratum multi-tile manager on the infinite word-grid canvas).

Spec (claim supply, QUEUE_STATE item-31 / watchdog draft items_30_33): a
"Spatial Program Coordinator managing autonomous process windows as
rectangular instruction/framebuffer tiles on infinite 2D plane without host
compositor dependency."

Layer contract (items 26/29/30 landed the foundation):

  - item-26 (tools/glyph_process.py): GlyphProcessTable spawns tasks as
    fresh GlyphCPUv2 engines — the process model.
  - item-29 (tools/glyph_containment.py): spawn(tile=...) arms the GO-2
    tile words and drops the engine to USER — the per-window fence.
  - item-30 (tools/glyph_loader.py): programs arrive as digest-verified
    images from the ext2 root — the executable transport.

item-31 composes them into a WINDOW COORDINATOR over a 2D plane of 32-bit
word-grid cells (W_MEM=32 words per grid row — the engine's own tile
predicate vocabulary, glyph_isa_v2.py:734-747):

  - open_window(): claims a rectangular tile region on the plane, refuses
    overlap LOUD (placement containment), refuses any region overlapping
    the engine's isolation MMIO block (a window covering the BOX MMIO rows
    could rewrite its own fence — the item-29 tile words live there), and
    spawns the window's task with tile=<its own rect> so the engine's
    existing E-K1 trap fences it to its window. A window task that tries
    to paint outside its rect traps and is reaped EXIT_FAULT — cross-window
    paint is impossible BY THE FENCE, not by politeness.
  - Each window carries a WCB-style row (STATE/X/Y/W/H/Z/VISIBLE — the
    geos_pixel_v5 wcb.rs field vocabulary, word-grid coordinates) so the
    host-side table and the GPU window system name the same things.
  - composite(): renders the plane — every visible window's tile painted
    from its task's RAM words (word & 0xFFFFFF = RGB, the Glyph color
    convention), ascending z-order, black background. The framebuffer of
    a window IS its tile words; the composite IS the canvas state.

What this is NOT (honesty): the coordinator is a HOST-side Phase-2 artifact
over the CPU-oracle engine — like items 26-30 it adds NO syscall number,
NO engine change, and NO guest-visible ABI; the WGSL twin contract is
untouched (TICKET_ITEM8 false-success class structurally avoided). "Infinite
plane" is the coordinate model (sparse plane dict, any non-negative origin);
a given task's RAM is bounded by memory_words (the engine contract) —
placement refuses origins whose words would fall outside RAM. No live
compositing: tasks run to completion (cooperative, item-26 shape) and the
composite is taken over the reaped state. No input routing (item-32), no
shell UI (item-33).
"""
from __future__ import annotations

import numpy as np

from tools.glyph_containment import ContainmentError  # noqa: F401
from tools.glyph_isa_v2 import (  # noqa: F401
    BOX_MMIO_BASE,
    W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessError, GlyphProcessTable

# The engine's isolation MMIO block: BOX_MMIO_BASE bytes .. +256 words
# (glyph_isa_v2.py:42, _iso_enabled at :716-723). In grid cells: rows
# [256, 264). A window overlapping these rows would have the box words
# (including its OWN fence words at 0x8160..0x816C, rows 256, cols 20..27)
# inside its storeable tile — a self-fence-rewrite vector. Refuse, never.
MMIO_BLOCK_BASE_WORD = BOX_MMIO_BASE >> 2          # 8192
MMIO_BLOCK_WORDS = 256
MMIO_ROW_LO = MMIO_BLOCK_BASE_WORD // W_MEM        # 256
MMIO_ROW_HI = (MMIO_BLOCK_BASE_WORD + MMIO_BLOCK_WORDS) // W_MEM  # 264


class StratumError(Exception):
    """Raised on coordinator misuse — loud, never silent."""


def _rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    """Half-open rects (row, col, h, w) in grid cells: True iff they share a cell."""
    ar, ac, ah, aw = a
    br, bc, bh, bw = b
    return (ar < br + bh and br < ar + ah
            and ac < bc + bw and bc < ac + aw)


class GlyphStratum:
    """Spatial window coordinator: autonomous fenced task-tiles on the
    word-grid plane, WCB-style rows, z-order, and a canvas composite."""

    def __init__(self, cols_instrs: int = 8, memory_words: int = 16384):
        self._cols_instrs = cols_instrs
        self._memory_words = memory_words
        self._table = GlyphProcessTable(cols_instrs=cols_instrs,
                                        memory_words=memory_words)
        # wid -> {state,x,y,w,h,z,visible,name,pid,rect}
        self._windows: dict[int, dict] = {}
        self._next_wid = 1
        self._plane_rows = memory_words // W_MEM  # placement ceiling from RAM

    # ── window lifecycle ─────────────────────────────────────────────────
    def open_window(self, image: np.ndarray,
                    plane_origin: tuple[int, int], size: tuple[int, int],
                    name: str = "", visible: bool = True, **spawn_kw) -> int:
        """Claim rect plane_origin+(size) and spawn the window's task fenced
        to it. Returns the window id. Raises StratumError on: overlap with
        an open window, overlap with the isolation MMIO block, origin or
        extent outside the RAM-bounded plane, or non-positive extent."""
        row, col = plane_origin
        h, w = size
        if not all(isinstance(v, int) and v >= 0 for v in (row, col)):
            raise StratumError(f"plane_origin must be non-negative ints, got {plane_origin!r}")
        if not all(isinstance(v, int) and v > 0 for v in (h, w)):
            raise StratumError(f"size must be positive ints, got {size!r}")
        if row + h > self._plane_rows or col >= W_MEM or col + w > W_MEM:
            raise StratumError(
                f"rect rows [{row},{row + h}) x cols [{col},{col + w}) exceeds the "
                f"RAM-bounded plane ({self._plane_rows} rows x {W_MEM} cols)")
        rect = (row, col, h, w)
        if row < MMIO_ROW_HI and row + h > MMIO_ROW_LO:
            raise StratumError(
                f"rect rows [{row},{row + h}) overlaps the isolation MMIO block "
                f"rows [{MMIO_ROW_LO},{MMIO_ROW_HI}) — a window there could "
                "rewrite its own fence; refused, never silently unfenced")
        for wid, wcb in self._windows.items():
            if wcb["state"] == 1 and _rects_overlap(rect, wcb["rect"]):
                raise StratumError(
                    f"rect {rect} overlaps open window {wid} at {wcb['rect']} "
                    "— placement containment refuses overlap, loud")
        try:
            pid = self._table.spawn(image, name=name or f"win{self._next_wid}",
                                    tile=rect, **spawn_kw)
        except GlyphProcessError as exc:
            raise StratumError(f"open_window: spawn refused: {exc}") from exc
        except ContainmentError as exc:  # defensive: rect is validated above
            raise StratumError(f"open_window: {exc}") from exc
        wid = self._next_wid
        self._next_wid += 1
        z = self._max_z() + 1
        # WCB row — field vocabulary of systems/geos_pixel_v5/src/wcb.rs
        # (STATE/X/Y/W/H/Z/VISIBLE), in word-grid coordinates.
        self._windows[wid] = {
            "state": 1, "x": col, "y": row, "w": w, "h": h,
            "z": z, "visible": 1 if visible else 0,
            "name": name or f"win{wid}", "pid": pid, "rect": rect,
        }
        return wid

    def open_window_from_disk(self, png_path: str, path: str,
                              plane_origin: tuple[int, int],
                              size: tuple[int, int],
                              name: str = "", **load_kw) -> int:
        """Open a window whose program arrives through the item-30 loader
        (fresh GlyphVfs -> digest verify -> reshape). Same placement rules
        as open_window; returns the window id."""
        from tools.glyph_loader import load_program  # local: import shape only

        row, col = plane_origin
        h, w = size
        if not all(isinstance(v, int) and v >= 0 for v in (row, col)):
            raise StratumError(f"plane_origin must be non-negative ints, got {plane_origin!r}")
        if not all(isinstance(v, int) and v > 0 for v in (h, w)):
            raise StratumError(f"size must be positive ints, got {size!r}")
        if row + h > self._plane_rows or col >= W_MEM or col + w > W_MEM:
            raise StratumError(
                f"rect rows [{row},{row + h}) x cols [{col},{col + w}) exceeds the "
                f"RAM-bounded plane ({self._plane_rows} rows x {W_MEM} cols)")
        rect = (row, col, h, w)
        if row < MMIO_ROW_HI and row + h > MMIO_ROW_LO:
            raise StratumError(
                f"rect rows [{row},{row + h}) overlaps the isolation MMIO block "
                f"rows [{MMIO_ROW_LO},{MMIO_ROW_HI}) — refused, never silently unfenced")
        for wid, wcb in self._windows.items():
            if wcb["state"] == 1 and _rects_overlap(rect, wcb["rect"]):
                raise StratumError(
                    f"rect {rect} overlaps open window {wid} at {wcb['rect']}")
        wid = self._next_wid
        try:
            pid = load_program(png_path, path, self._table,
                               name=name or f"win{wid}", tile=rect, **load_kw)
        except GlyphProcessError as exc:
            raise StratumError(f"open_window_from_disk: spawn refused: {exc}") from exc
        except Exception as exc:  # LoaderError without importing the type twice
            raise StratumError(f"open_window_from_disk: load refused: {exc}") from exc
        self._next_wid += 1
        self._windows[wid] = {
            "state": 1, "x": col, "y": row, "w": w, "h": h,
            "z": self._max_z() + 1, "visible": 1,
            "name": name or f"win{wid}", "pid": pid, "rect": rect,
        }
        return wid

    def close_window(self, wid: int) -> None:
        """Close a window: its WCB row goes STATE=0, its pid's task is
        forgotten (the table's cooperative model: tasks exit on their own;
        closing only retires the window record and frees the rect)."""
        wcb = self._require(wid)
        wcb["state"] = 0
        wcb["visible"] = 0

    def raise_window(self, wid: int) -> int:
        """Raise to top of z-order (max z + 1). Returns the new z."""
        wcb = self._require(wid)
        wcb["z"] = self._max_z() + 1
        return wcb["z"]

    def set_visible(self, wid: int, visible: bool) -> None:
        self._require(wid)["visible"] = 1 if visible else 0

    # ── queries ──────────────────────────────────────────────────────────
    def hit_test(self, row: int, col: int) -> int | None:
        """The id of the TOPMOST (max-z) open, visible window covering grid
        cell (row, col); None if the cell hits no window."""
        best: int | None = None
        best_z = -1
        for wid, wcb in self._windows.items():
            if wcb["state"] != 1 or wcb["visible"] != 1:
                continue
            r, c, h, w = wcb["rect"]
            if r <= row < r + h and c <= col < c + w and wcb["z"] > best_z:
                best, best_z = wid, wcb["z"]
        return best

    def window(self, wid: int) -> dict:
        return dict(self._require(wid))

    def windows(self) -> dict[int, dict]:
        return {wid: dict(wcb) for wid, wcb in self._windows.items()}

    # ── execution + composition ──────────────────────────────────────────
    def run_all(self) -> dict[int, int]:
        """Run every window's task to completion (cooperative, item-26
        shape). Returns pid -> exit status."""
        return self._table.wait_all()

    def composite(self) -> np.ndarray:
        """Render the plane: a (rows x cols x 3) uint8 canvas covering the
        bounding box of all open+visible windows; each window's tile painted
        from its task's RAM words (word & 0xFFFFFF -> RGB) in ascending
        z-order; background black."""
        visible = [(wid, wcb) for wid, wcb in self._windows.items()
                   if wcb["state"] == 1 and wcb["visible"] == 1]
        if not visible:
            return np.zeros((0, 0, 3), dtype=np.uint8)
        height = max(wcb["y"] + wcb["h"] for _, wcb in visible)
        width = max(wcb["x"] + wcb["w"] for _, wcb in visible)
        canvas = np.zeros((height, width, 3), dtype=np.uint8)
        for wid, wcb in sorted(visible, key=lambda kv: kv[1]["z"]):
            r, c, h, w = wcb["rect"]
            cpu = self._table.tasks[wcb["pid"]]["cpu"]
            for dr in range(h):
                for dc in range(w):
                    word = cpu.memory[(r + dr) * W_MEM + (c + dc)] & 0xFFFFFF
                    canvas[r + dr, c + dc] = (
                        (word >> 16) & 0xFF, (word >> 8) & 0xFF, word & 0xFF)
        return canvas

    def output(self, wid: int) -> bytes:
        """The window task's PRT stream (the glyph stdout contract)."""
        return self._table.output(self._require(wid)["pid"])

    def close(self):
        self._table.close()

    # ── internals ────────────────────────────────────────────────────────
    def _require(self, wid: int) -> dict:
        if wid not in self._windows:
            raise StratumError(f"no such window {wid}")
        return self._windows[wid]

    def _max_z(self) -> int:
        if not self._windows:
            return 0
        return max(wcb["z"] for wcb in self._windows.values())
