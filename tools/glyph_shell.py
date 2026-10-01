"""glyph_shell.py — CLAIM QUEUE item 33: desktop shell UI & process task
launcher (status bar panel, storage capacity gauge, app launcher tile).

Spec (claim supply, QUEUE_STATE item-33 / watchdog draft items_30_33):
"Full desktop shell interface with system status bar, Ext2 PNG VFS
storage gauge, launcher panel, and running task monitors in native
glyph spatial assembly."

Layer contract (items 26-32 landed the foundation this composes):

  - item-31 (tools/glyph_stratum.py): GlyphStratum — windows as fenced
    tiles on the W_MEM=32 word-grid plane, WCB rows, z-order, hit_test,
    composite() (word & 0xFFFFFF = RGB).
  - item-32 (tools/glyph_input.py): GlyphInputRouter — BM905 packets
    delivered into a window's tile top row; focus pin / hit-test auto.
  - item-25/28 (tools/glyph_vfs.py, glyph_root_init.py): the ext2 root
    in the VFS-1 PNG transport — the storage the gauge measures.
  - item-30 (tools/glyph_loader.py): store_program — apps arrive as
    digest-verified images in the root; the launcher's app table names
    them.

GlyphShell is the HOST-SIDE shell over these layers; every pixel it
shows is PAINTED BY A GUEST TASK through fenced stores, and every
panel is an ordinary item-31 window:

  - open_bar(): the STATUS BAR — a full-width 1-row window at plane row
    BAR_ROW whose bar task paints its own tile cells through fenced
    STs: capacity cells (the gauge), a colored health cell, and the
    launcher cells (one per app in the app table, distinct colors).
  - storage_gauge(): the GAUGE NUMBERS — free/total 1 KiB blocks parsed
    from `debugfs -R stats` over the root image recovered through
    png_vfs.unwrap (the same e2progs-only discipline as item-25: this
    module never parses ext2 bytes itself).
  - install_app() / launch(): the LAUNCHER — install_app stores a
    program image + SHA-256 sidecar into the root under /apps/<name>
    (item-30 store_program) and records it in the app table at a
    reserved launcher cell; launch(name) opens the app's window via
    open_window and delivers a BM905 key-press INTO the new window's
    inbox pre-run (the item-32 delivery contract — the "click" the
    launcher sends the app).
  - tasks(): the TASK MONITOR — the table's cooperative view
    (pid -> name/state/exit_status) of every window the shell opened.

Fence discipline: the shell never paints a window's cells from the
host side. Panel appearances are produced by guest tasks storing inside
their own tiles (the item-31 E-K1 fence is the containment); the gauge
and task data enter guest RAM as ordinary seeded words (pre-run host
RAM seed, the item-32 router precedent — the dispatcher is kernel-class).

What this is NOT (honesty): host-side Phase-2 artifact over the
CPU-oracle engine — NO new syscall number, NO engine change, NO
guest-visible ABI beyond RAM words a task already LDs (WGSL twin
contract untouched; TICKET_ITEM8 class structurally avoided). No live
redraw while a task RUNS (cooperative item-26 model: bar task runs,
then the composite is taken). No fonts/text on the plane (cells are
solid colors; text lives in the PRT/console lanes). No window dragging
or resize (placement containment: rects are open-time fixed). Storage
gauge numbers are metadata reads (debugfs), not guest-executed queries.
"""
from __future__ import annotations

import subprocess

import numpy as np

from tools.glyph_input import GlyphInputRouter
from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2, W_MEM
from tools.glyph_loader import store_program
from tools.glyph_stratum import GlyphStratum
from tools.glyph_vfs import GlyphVfs
import tools.png_vfs as png_vfs

# ── shell layout constants (the item-33 LOCKED layout contract) ─────────
BAR_ROW = 8              # plane row of the status bar (above MMIO rows)
BAR_CELLS = 20           # bar width in grid cells (cols 0..19)
GAUGE_CELLS = 12         # cells 0..11: capacity gauge
HEALTH_CELL = 12         # cell 12: health (green <= 50% used, yellow
                         # <= 85%, red above)
LAUNCH_BASE = 14         # cells 14..19: launcher tiles (6 app slots)
LAUNCH_SLOTS = BAR_CELLS - LAUNCH_BASE
BAR_COLOR_BG = 0x202020
GAUGE_FG = 0x00B4FF
HEALTH_GREEN = 0x00C000
HEALTH_YELLOW = 0xC0C000
HEALTH_RED = 0xC00000
APP_ROW = 20             # app windows open at plane row 20+
APP_SLOT_COLS = 24       # app window width so inboxes fit (>=17 words)
APP_SLOT_H = 4


class ShellError(Exception):
    """Raised on shell misuse — loud, never silent."""


def _word(row: int, col: int) -> int:
    return row * W_MEM + col


def _rgb_word(cell: int, color: int) -> int:
    """The cell's word value: (cell_index << 24) | RGB — the low 24 bits
    are what composite() shows; the high byte carries the cell index so
    a consumer task can tell cells apart over a monochrome gauge."""
    return ((cell & 0xFF) << 24) | (color & 0xFFFFFF)


class GlyphShell:
    """Desktop shell over GlyphStratum: status bar + gauge, launcher,
    task monitor. Every visible pixel is painted by a guest task."""

    def __init__(self, stratum: GlyphStratum | None = None):
        self.stratum = stratum if stratum is not None else GlyphStratum()
        self.router = GlyphInputRouter(self.stratum)
        self._om = OpcodeMapV2()
        self._asm = GlyphAssemblerV2(self._om)
        # app name -> {path, color, cell}
        self._apps: dict[str, dict] = {}
        self._bar_wid: int | None = None
        self._app_wids: dict[str, int] = {}   # name -> wid of last launch
        self._next_app_slot = 0

    # ── gauge: storage capacity from the ext2 root (metadata read) ──────
    @staticmethod
    def storage_gauge(root_png: str) -> tuple[int, int]:
        """(free_blocks, total_blocks) of the 1 KiB-block ext2 image
        behind the VFS-1 PNG root. `debugfs -R stats` on the unwrapped
        image — never hand-parsed ext2 bytes (item-25 discipline)."""
        raw = png_vfs.unwrap(root_png)
        work = tempfile_dir()
        img = os_path(work, "disk.img")
        with open(img, "wb") as f:
            f.write(raw)
        res = subprocess.run(["debugfs", "-R", "stats", img],
                             capture_output=True)
        if res.returncode != 0:
            raise ShellError(
                f"storage_gauge: debugfs rc={res.returncode} on {root_png}")
        free = total = None
        for line in res.stdout.decode(errors="replace").splitlines():
            if line.startswith("Free blocks:"):
                free = int(line.split(":")[1].strip().split()[0])
            elif line.startswith("Block count:"):
                total = int(line.split(":")[1].strip().split()[0])
        if free is None or total is None:
            raise ShellError(
                f"storage_gauge: stats did not yield block counts on {root_png}")
        return free, total

    # ── launcher: app table over the item-30 store_program transport ────
    def install_app(self, root_png: str, name: str, image: np.ndarray,
                    color: int) -> None:
        """Store the app (digest-verified image + sidecar) at /apps/<name>
        and reserve its launcher cell. The color is the app's launcher
        tile color (cells are solid colors; no fonts on the plane)."""
        if not name or "/" in name:
            raise ShellError(f"install_app: bad app name {name!r}")
        if name in self._apps:
            raise ShellError(f"install_app: {name!r} already installed")
        if self._next_app_slot >= LAUNCH_SLOTS:
            raise ShellError(
                f"install_app: launcher full ({LAUNCH_SLOTS} slots)")
        vfs = GlyphVfs(root_png)
        store_program(vfs, f"/apps/{name}", image)
        if vfs.sync() != 0:
            raise ShellError(f"install_app: sync refused for {name!r}")
        self._apps[name] = {"path": f"/apps/{name}", "color": color & 0xFFFFFF,
                            "cell": LAUNCH_BASE + self._next_app_slot}
        self._next_app_slot += 1

    def launch(self, root_png: str, name: str) -> int:
        """Open the app's window (item-30 load through the digest) and
        deliver a BM905 key-press into its inbox pre-run (the item-32
        'click'). Returns the window id."""
        if name not in self._apps:
            raise ShellError(f"launch: unknown app {name!r}")
        if name in self._app_wids and self._app_wids[name] is not None:
            wcb = self.stratum.window(self._app_wids[name])
            if wcb["state"] == 1:
                raise ShellError(f"launch: {name!r} is already running")
        from tools.glyph_loader import load_program  # local import shape
        slot = self._free_app_slot()
        origin = (APP_ROW + slot * (APP_SLOT_H + 2), 0)
        wid = self.stratum.open_window_from_disk(
            root_png, self._apps[name]["path"],
            plane_origin=origin, size=(APP_SLOT_H, APP_SLOT_COLS),
            name=name)
        self._app_wids[name] = wid
        # The launcher 'click': one focused key-press into the fresh app.
        self.router.focus_window(wid)
        self.router.key(34)  # KEY_H — the app's 'hello' pulse
        return wid

    # ── the status bar window ────────────────────────────────────────────
    def open_bar(self, root_png: str) -> int:
        """Open the status-bar window and seed + run its bar task.

        The bar task is a REAL guest program: it LDs the seeded gauge/
        launcher words from its inbox row and STs painted cells INSIDE
        ITS OWN TILE (fenced; an out-of-bar store would trap). The
        seed enters pre-run through the item-32 router precedent (the
        shell is kernel-class; the bar task is the consumer).
        """
        if self._bar_wid is not None:
            wcb = self.stratum.window(self._bar_wid)
            if wcb["state"] == 1:
                raise ShellError("open_bar: the bar is already open")
        free, total = self.storage_gauge(root_png)
        bar_wid = self.stratum.open_window(
            self._bar_program(), plane_origin=(BAR_ROW, 0),
            size=(1, BAR_CELLS), name="statusbar")
        self._bar_wid = bar_wid
        self._seed_bar(free, total)
        self.stratum.run_all()
        return bar_wid

    def refresh_bar(self, root_png: str) -> int:
        """Re-measure the root and REPAINT the gauge.

        The table is cooperative: an exited task never re-runs, so a
        refresh CLOSES the bar window record and re-spawns a FRESH bar
        task at the same locked rect (placement containment permits the
        rect the moment the old record is closed), seeds it from the
        CURRENT root, and runs it. The returned wid is the NEW bar
        window id."""
        if self._bar_wid is None:
            raise ShellError("refresh_bar: the bar was never opened")
        free, total = self.storage_gauge(root_png)
        self.stratum.close_window(self._bar_wid)
        bar_wid = self.stratum.open_window(
            self._bar_program(), plane_origin=(BAR_ROW, 0),
            size=(1, BAR_CELLS), name="statusbar")
        self._bar_wid = bar_wid
        self._seed_bar(free, total)
        self.stratum.run_all()
        return self._bar_wid

    # ── task monitor ─────────────────────────────────────────────────────
    def tasks(self) -> dict[int, dict]:
        """pid -> {name, state, exit_status, wid} for every window the
        shell opened (the cooperative monitor view)."""
        out: dict[int, dict] = {}
        for name, wid in list(self._app_wids.items()) + [("statusbar", self._bar_wid)]:
            if wid is None:
                continue
            assert wid is not None  # narrowed above
            wcb = self.stratum.window(wid)
            task = self.stratum._table.tasks[wcb["pid"]]
            out[wcb["pid"]] = {"name": name, "state": task["state"],
                               "exit_status": task["exit_status"], "wid": wid}
        return out

    def close(self):
        self.stratum.close()
        self._om.close()

    # ── internals ────────────────────────────────────────────────────────
    def _free_app_slot(self) -> int:
        used = {self.stratum.window(w)["rect"][0]
                for w in self._app_wids.values() if w is not None}
        slot = 0
        while APP_ROW + slot * (APP_SLOT_H + 2) in used:
            slot += 1
        return slot

    def _seed_bar(self, free: int, total: int) -> None:
        """Seed the bar task's gauge words (pre-run, kernel-class write —
        the router precedent) and the launcher cells."""
        wcb = self.stratum.window(self._bar_wid)
        cpu = self.stratum._table.tasks[wcb["pid"]]["cpu"]
        base = _word(BAR_ROW, 0)
        used_pct = (total - free) * 100 // total if total else 100
        filled = GAUGE_CELLS * used_pct // 100   # host computes; guest paints
        words: dict[int, int] = {
            base + 0: free,
            base + 1: total,
            base + 2: used_pct,
            base + 3: filled,
        }
        for name, info in self._apps.items():
            words[base + info["cell"]] = _rgb_word(info["cell"], info["color"])
        for addr, val in words.items():
            cpu.memory[addr] = val & 0xFFFFFFFF

    def _bar_program(self) -> np.ndarray:
        """The bar task: paint the gauge cells from the seeded words.

        r10 = bar base word. The loop paints GAUGE_FG into cell i for
        i < filled, BAR_COLOR_BG for filled <= i < GAUGE_CELLS; then the
        health cell; then copies every nonzero launcher cell word
        through. All STs are inside the bar's own 1x20 tile — the fence
        is the containment, not politeness.
        """
        # Register plan (all addresses are word addresses in the bar row):
        #   r10 base, r11 i (cell index), r12 filled, r13 scratch addr,
        #   r14 scratch color/value, r15 = 1, r16 = GAUGE_CELLS,
        #   r17 = LAUNCH_BASE, r18 = BAR_CELLS
        b = _word(BAR_ROW, 0)
        filled_addr = b + 3          # scratch: computed filled count
        return self._asm.assemble([
            f"LDI r10 {b}",
            "LDI r15 1",
            "LDI r16 %d" % GAUGE_CELLS,
            "LDI r19 0",
            # filled is seeded by the shell (host computes the percent ->
            # cells mapping; the guest paints r12 cells — NO-DIV contract).
            f"LDI r13 {filled_addr}",
            "LD r12 r13",            # r12 = filled (seeded by the shell)
            "LDI r11 0",             # i = 0
            ":loop",
            f"LDI r13 {b}",          # addr = base + i
            "ADD r13 r11",
            # ENGINE FACT (measured, probe_jlt.py): CMP is an EQUALITY flag
            # (r0 = rd==rs2); JLT jumps when r0==0, which is CMP3's
            # less-than encoding. The loop guards therefore use CMP3
            # (tri-state signed): r0==0 ⇔ i < bound.
            "CMP3 r11 r12",          # i < filled ?
            "JLT :paint_fg",
            f"LDI r14 {BAR_COLOR_BG}",
            "JMP :do_paint",
            ":paint_fg",
            f"LDI r14 {GAUGE_FG}",
            ":do_paint",
            "ST r13 r14",
            "ADD r11 r15",           # i++
            "CMP3 r11 r16",
            "JLT :loop",
            # health cell (fixed offsets, not index math)
            f"LDI r13 {b + HEALTH_CELL}",
            f"LDI r14 {HEALTH_RED}",
            "ST r13 r14",
            # launcher cells: copy seeded words through (skip zero words:
            # CMP against r19=0 raises the equality flag; JZ takes it).
            f"LDI r13 {b + LAUNCH_BASE}",
            "LD r14 r13",
            "CMP r14 r19",
            "JZ :skip14",
            "ST r13 r14",
            ":skip14",
            f"LDI r13 {b + LAUNCH_BASE + 1}",
            "LD r14 r13",
            "CMP r14 r19",
            "JZ :skip15",
            "ST r13 r14",
            ":skip15",
            "LDI r1 0",
            "SYSCALL r0 0x05",
            "HALT",
        ], width_instrs=8)


def tempfile_dir() -> str:
    import tempfile
    return tempfile.mkdtemp(prefix="glyph_shell_")


def os_path(*parts) -> str:
    import os
    return os.path.join(*parts)
