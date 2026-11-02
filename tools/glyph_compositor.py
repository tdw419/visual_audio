"""glyph_compositor.py — CLAIM QUEUE item 38: spatial window compositing
with OVERLAPPING tiles, damage clipping, z-order elevation, and drag
repositioning.

Spec (BRIEF_item38_compositor.md, QUEUE_STATE item-38): overlapping
window tiles on the word-grid plane with "tile damage clipping,
top-window focus, drag repositioning".

Why a NEW module (not GlyphStratum): GlyphStratum.open_window REFUSES
overlapping placement loud (tools/glyph_stratum.py:126-129) — that is a
live placement-containment guard and item-38 does not weaken it. The
compositor is the OVERLAP-PERMITTING sibling: it composes the same landed
layers (glyph_process spawn(tile=) fences + glyph_containment) directly
and permits overlapping placement BY CONTRACT, ordering paint by z.

Layer contract (consumed, never edited):
  item-26 tools/glyph_process.py     — cooperative task table (spawn/wait)
  item-29 tools/glyph_containment.py — per-window tile fences (arm_tile
                                       via spawn(tile=...))
  item-31 tools/glyph_stratum.py     — vocabulary precedent (WCB rows,
                                       word & 0xFFFFFF -> RGB); its
                                       overlap guard is UNTOUCHED.

Semantics:
  - place(image, origin, size): overlap permitted. z = max_z + 1 (later
    placement stacks on top). The task is FENCED to its own rect exactly
    as item-29/31 arm it — overlap is a COMPOSITING relation between
    windows, never a permission for a guest to store outside its tile.
  - raise_window(wid): z = max_z + 1 (elevation to top).
  - move(wid, new_origin): drag — the WCB rect's origin changes in place;
    extent is unchanged; the fence is NOT re-armed (the fence words name
    the ORIGINAL tile the task was spawned with — moving a window moves
    WHERE ITS PAINT COMPOSITES, not what its running guest may touch;
    re-arming mid/after-run would silently rewrite a landed fence, so it
    is refused: move() only accepts already-reaped windows and moves the
    record + composite placement). BK-36: a reaped window renders its
    REAP-TIME SNAPSHOT (its tile pixels captured from the origin rect at
    run_all(), frozen because a reaped guest can never repaint), so a
    dragged window keeps every pixel its guest painted — before BK-36 the
    paint stayed word-anchored to the OLD grid addresses and a drag
    composited 100% black (RESEARCH_move_damage_blackout.md).
  - composite(): damage clipping — paint ascending z; a cell already
    painted by a higher-z window is NOT overpainted by lower windows
    (equivalently: iterate descending z and SKIP already-painted cells;
    implemented ascending with an occupancy mask — same result, O(cells)).
  - hit_test(row, col): topmost (max-z) open+visible window covering the
    cell — the "top-window focus" rule (item-31 vocabulary).

What this is NOT (honesty): host-side Phase-2 composition over the
CPU-oracle engine — no new syscall number, no engine change, no edits to
any consumed layer (the gate pins glyph_isa_v2.py byte-identical to
HEAD). "Damage" here is per-composite clipping, not incremental dirty-
rect tracking (composite recomputes the full occupancy each call).
move() is a host-side record/composite move of a reaped window, not live
dragging of a running guest (delivery stays cooperative, item-26 shape).
No rates or latencies are asserted (rule-1 floors do not attach).
"""
from __future__ import annotations

import numpy as np

from tools.glyph_containment import ContainmentError  # noqa: F401
from tools.glyph_isa_v2 import W_MEM
from tools.glyph_process import GlyphProcessError, GlyphProcessTable


class CompositorError(Exception):
    """Raised on compositor misuse — loud, never silent."""


def _rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    """Half-open rects (row, col, h, w) in grid cells: True iff they share a cell."""
    ar, ac, ah, aw = a
    br, bc, bh, bw = b
    return (ar < br + bh and br < ar + ah
            and ac < bc + bw and bc < ac + aw)


class GlyphCompositor:
    """Overlapping spatial windows on the word-grid plane: z-ordered
    damage-clipped compositing, elevation, and drag repositioning."""

    def __init__(self, cols_instrs: int = 8, memory_words: int = 16384):
        self._cols_instrs = cols_instrs
        self._memory_words = memory_words
        self._table = GlyphProcessTable(cols_instrs=cols_instrs,
                                        memory_words=memory_words)
        # wid -> {state,x,y,w,h,z,visible,name,pid,reaped,rect}
        self._windows: dict[int, dict] = {}
        self._next_wid = 1
        self._plane_rows = memory_words // W_MEM
        # BK-36 snapshot-at-reap: wid -> (h, w, 3) uint8 tile captured from
        # the ORIGIN rect when the window's task runs to completion. A
        # reaped window's paint is FROZEN (its guest can never run again),
        # so composite() renders the snapshot instead of re-reading RAM at
        # the window's CURRENT rect — which is why a dragged window used to
        # composite 100% black (RESEARCH_move_damage_blackout.md: the RAM
        # paint lives at the OLD grid words; composite read the NEW rect).
        # Live (un-reaped) windows have NO snapshot and keep rendering from
        # RAM, exactly as before.
        self._snapshots: dict[int, np.ndarray] = {}

    # ── placement (overlap permitted BY CONTRACT) ────────────────────────
    def place(self, image: np.ndarray,
              plane_origin: tuple[int, int], size: tuple[int, int],
              name: str = "", visible: bool = True, **spawn_kw) -> int:
        """Place a window tile at plane_origin with extent size. OVERLAP
        with existing windows is permitted (that is this module's reason
        to exist); the task is still fenced to its OWN rect via
        spawn(tile=rect). Returns the window id. Raises CompositorError
        on degenerate/out-of-plane rects or spawn refusal."""
        row, col = plane_origin
        h, w = size
        if not all(isinstance(v, int) and v >= 0 for v in (row, col)):
            raise CompositorError(f"plane_origin must be non-negative ints, got {plane_origin!r}")
        if not all(isinstance(v, int) and v > 0 for v in (h, w)):
            raise CompositorError(f"size must be positive ints, got {size!r}")
        if row + h > self._plane_rows or col >= W_MEM or col + w > W_MEM:
            raise CompositorError(
                f"rect rows [{row},{row + h}) x cols [{col},{col + w}) exceeds the "
                f"RAM-bounded plane ({self._plane_rows} rows x {W_MEM} cols)")
        rect = (row, col, h, w)
        try:
            pid = self._table.spawn(image, name=name or f"win{self._next_wid}",
                                    tile=rect, **spawn_kw)
        except GlyphProcessError as exc:
            raise CompositorError(f"place: spawn refused: {exc}") from exc
        except ContainmentError as exc:  # defensive: rect validated above
            raise CompositorError(f"place: {exc}") from exc
        wid = self._next_wid
        self._next_wid += 1
        self._windows[wid] = {
            "state": 1, "x": col, "y": row, "w": w, "h": h,
            "z": self._max_z() + 1, "visible": 1 if visible else 0,
            "name": name or f"win{wid}", "pid": pid, "reaped": False,
            "rect": rect,
        }
        return wid

    def raise_window(self, wid: int) -> int:
        """Elevate to top of z-order (max z + 1). Returns the new z."""
        self._require(wid)["z"] = self._max_z() + 1
        return self._require(wid)["z"]

    def set_visible(self, wid: int, visible: bool) -> None:
        self._require(wid)["visible"] = 1 if visible else 0

    def move(self, wid: int, new_origin: tuple[int, int]) -> None:
        """Drag a REAPED window to new_origin: the WCB rect's origin
        changes; extent unchanged. The task's FENCE is never re-armed
        (a landed fence is not silently rewritten) — move() refuses any
        window whose task has not run to completion, and refuses
        out-of-plane origins LOUD (the record is unchanged after a
        refusal)."""
        row, col = new_origin
        wcb = self._require(wid)
        if not wcb["reaped"]:
            raise CompositorError(
                f"move: window {wid} has not run to completion (cooperative "
                "delivery — a running task's fence names its live tile)")
        h, w = wcb["h"], wcb["w"]
        if not all(isinstance(v, int) and v >= 0 for v in (row, col)):
            raise CompositorError(f"move: origin must be non-negative ints, got {new_origin!r}")
        if row + h > self._plane_rows or col >= W_MEM or col + w > W_MEM:
            raise CompositorError(
                f"move: origin {new_origin!r} puts rect rows [{row},{row + h}) "
                f"x cols [{col},{col + w}) outside the RAM-bounded plane "
                f"({self._plane_rows} rows x {W_MEM} cols) — refused, "
                "record unchanged")
        wcb["x"], wcb["y"] = col, row
        wcb["rect"] = (row, col, h, w)

    # ── queries ──────────────────────────────────────────────────────────
    def hit_test(self, row: int, col: int) -> int | None:
        """Topmost (max-z) open+visible window covering (row, col); None
        if the cell hits no window. THE top-window focus rule."""
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
        shape); marks each window reaped. Returns pid -> exit status."""
        statuses = self._table.wait_all()
        for wid, wcb in self._windows.items():
            if not wcb["reaped"]:
                self._snapshot_at_reap(wid, wcb)
            wcb["reaped"] = True
        return statuses

    def _snapshot_at_reap(self, wid: int, wcb: dict) -> None:
        """BK-36: capture the window's tile pixels from the ORIGIN rect
        (its guest painted inside its fence at those grid words; after
        reap the guest can never repaint, so this freeze is exact)."""
        r, c, h, w = wcb["rect"]
        pid = wcb["pid"]
        if pid not in self._table.tasks:
            return
        cpu = self._table.tasks[pid]["cpu"]
        snap = np.zeros((h, w, 3), dtype=np.uint8)
        for dr in range(h):
            for dc in range(w):
                word = cpu.memory[(r + dr) * W_MEM + (c + dc)] & 0xFFFFFF
                snap[dr, dc] = (
                    (word >> 16) & 0xFF, (word >> 8) & 0xFF, word & 0xFF)
        self._snapshots[wid] = snap
        # NON-VACUITY SEAM (BK-36 L5): commenting the line above out (or
        # inserting `return` before it) must turn BK-36 L1 RED — the gate
        # is proven able to fail. See RECEIPT_BK36_move_snapshot.md.

    def composite(self) -> np.ndarray:
        """Damage-clipped render of the plane: a (rows x cols x 3) uint8
        canvas over the bounding box of all open+visible windows; windows
        painted in DESCENDING z order with an occupancy mask — the TOP
        window claims its damage region FIRST, and every LOWER window is
        CLIPPED out of already-claimed cells (its covered words are never
        rendered; word & 0xFFFFFF -> RGB, the Glyph color convention;
        background black). The clip is load-bearing, not decorative:
        suppressing the skip lets a lower window overpaint the top (the
        gate's RED 2 proves this fails)."""
        visible = [(wid, wcb) for wid, wcb in self._windows.items()
                   if wcb["state"] == 1 and wcb["visible"] == 1]
        if not visible:
            return np.zeros((0, 0, 3), dtype=np.uint8)
        height = max(wcb["y"] + wcb["h"] for _, wcb in visible)
        width = max(wcb["x"] + wcb["w"] for _, wcb in visible)
        canvas = np.zeros((height, width, 3), dtype=np.uint8)
        occupied = np.zeros((height, width), dtype=bool)
        for wid, wcb in sorted(visible, key=lambda kv: -kv[1]["z"]):
            r, c, h, w = wcb["rect"]
            snap = self._snapshots.get(wid)
            if snap is not None:
                # BK-36: reaped window — render the reap-time snapshot at
                # the CURRENT rect (the paint follows the drag).
                for dr in range(h):
                    for dc in range(w):
                        rr, cc = r + dr, c + dc
                        if occupied[rr, cc]:
                            continue  # damage clipping: higher z owns this cell
                        canvas[rr, cc] = snap[dr, dc]
                        occupied[rr, cc] = True
            else:
                cpu = self._table.tasks[wcb["pid"]]["cpu"]
                for dr in range(h):
                    for dc in range(w):
                        rr, cc = r + dr, c + dc
                        if occupied[rr, cc]:
                            continue  # damage clipping: higher z owns this cell
                        word = cpu.memory[rr * W_MEM + cc] & 0xFFFFFF
                        canvas[rr, cc] = (
                            (word >> 16) & 0xFF, (word >> 8) & 0xFF, word & 0xFF)
                        occupied[rr, cc] = True
        return canvas

    def output(self, wid: int) -> bytes:
        """The window task's PRT stream (the glyph stdout contract)."""
        return self._table.output(self._require(wid)["pid"])

    def close(self):
        self._table.close()

    # ── internals ────────────────────────────────────────────────────────
    def _require(self, wid: int) -> dict:
        if wid not in self._windows:
            raise CompositorError(f"no such window: {wid}")
        return self._windows[wid]

    def _max_z(self) -> int:
        return max((wcb["z"] for wcb in self._windows.values()), default=0)
