"""glyph_notify.py — CLAIM QUEUE item 40: desktop notification daemon &
system tray ABI (asynchronous agent toast alerts, status bar reactive
applets).

Spec (QUEUE_STATE item-40, brief .builder_queue/BRIEF_item40_notify.md):
compose the LANDED item-38 GlyphCompositor into a notification layer:
toasts are ordinary compositor windows placed OVER content (overlap
permitted by the compositor's contract), alerts are emitted by agent
guests as a request word stored INSIDE the agent's own tile and
harvested kernel-class by the daemon (item-34 commit_guest_ring /
item-37 wire-word->percept precedent), and the tray is a window whose
applet cells are repainted by a fresh tray task per state change
(item-33 refresh_bar respawn idiom).

Layer contract (what this module consumes, never modifies):
  - item-38 (tools/glyph_compositor.py): GlyphCompositor.place/move/
    close_window/composite/hit_test — arrival-order z, damage clipping,
    reaped-window re-stacking via move().
  - item-31/29 (tools/glyph_stratum.py, glyph_containment.py): every
    toast/tray/agent task is FENCED to its own tile (spawn(tile=...));
    an out-of-tile store traps E-K1 to the reaper and reaps EXIT_FAULT.
  - item-33 (tools/glyph_shell.py): guest-paint idiom (host seeds/
    harvests words kernel-class; the GUEST stores painted cells), and
    the close-and-respawn repaint idiom (refresh_bar).
  - CPU-oracle engine: NO new syscall, NO engine change (N1 byte-guard).

Honesty (Phase-2 boundary, item-37 doctrine): host-side artifact over
the CPU-oracle engine. Delivery is cooperative commit-between-runs —
"asynchronous" means the agent's alert is queued at its own run and
harvested later by the daemon, NOT mid-run preemption (no interrupts).
No GPU/WGSL execution. No text/fonts on toast cells (solid color words;
text lives in the PRT/console lanes).
"""
from __future__ import annotations

import numpy as np

from tools.glyph_compositor import CompositorError, GlyphCompositor
from tools.glyph_isa_v2 import (
    TILE_COL_ADDR,
    TILE_ROW_ADDR,
    GlyphAssemblerV2,
    OpcodeMapV2,
    W_MEM,
)

# ── GlyphNotifyDaemon ABI constants ──────────────────────────────────────

LEVEL_INFO = 0
LEVEL_WARN = 1
LEVEL_ERROR = 2
LEVEL_OK = 3
LEVELS = (LEVEL_INFO, LEVEL_WARN, LEVEL_ERROR, LEVEL_OK)

LEVEL_COLORS = {
    LEVEL_INFO: 0x3050FF,   # blue
    LEVEL_WARN: 0xFFC000,   # amber
    LEVEL_ERROR: 0xFF2020,  # red
    LEVEL_OK: 0x20C040,     # green
}

REQUEST_MAGIC = 0x4E            # 'N' — request-word magic (byte 3)
QUEUE_CAP = 8                   # held toasts before dispatch
TOAST_W = 6                     # toast extent (cells)
TOAST_H = 1
TOAST_PITCH = 2                 # rows between stacked toasts
STACK_TOP_ROW = 2               # first toast stack row
TRAY_SLOTS = 4                  # tray applet capacity
TRAY_ROW = 0                    # tray window plane row
TRAY_W = TRAY_SLOTS + 1         # slots + one state cell
TRAY_SLOT_OFFSET = 1            # first applet slot cell (cell 0 = tray id)


class NotifyError(Exception):
    """Raised on daemon misuse or a quarantined request — loud, never silent."""


def encode_request(level: int, payload: int) -> int:
    """The agent->daemon request word: magic<<24 | level<<16 | payload."""
    return ((REQUEST_MAGIC & 0xFF) << 24) | ((level & 0xFF) << 16) | (payload & 0xFFFF)


def decode_request(word: int) -> tuple[int, int, int]:
    magic = (word >> 24) & 0xFF
    level = (word >> 16) & 0xFF
    payload = word & 0xFFFF
    return magic, level, payload


class GlyphNotifyDaemon:
    """Desktop notification daemon + tray ABI over the item-38 compositor."""

    def __init__(self, compositor: GlyphCompositor | None = None):
        self.comp = compositor if compositor is not None else GlyphCompositor()
        self._om = OpcodeMapV2()
        self._asm = GlyphAssemblerV2(self._om)
        self._queue: list[dict] = []          # held toasts pre-dispatch
        self._toasts: list[int] = []          # dispatched toast wids, bottom->top
        self._agents: dict[int, dict] = {}    # wid -> {"request_cell": int}
        self._tray_wid: int | None = None
        self._applets: dict[int, dict] = {}   # slot -> {"color","state"}
        self._tray_task_n = 0

    # ── agent registration + harvest (kernel-class, item-34 precedent) ──
    def register_agent(self, wid: int,
                       request_cell: tuple[int, int]) -> None:
        """Register a placed window (the compositor owns the tile) as an
        alerting agent: the daemon will read request words at
        `request_cell` — a (row, col) INSIDE the window's own tile. The
        agent guest computes and STs the word itself (fenced); the host
        only reads it after the task's run (commit-between-runs)."""
        wcb = self.comp.window(wid)
        r, c, h, w = wcb["rect"]
        rr, cc = request_cell
        if not (r <= rr < r + h and c <= cc < c + w):
            raise NotifyError(
                f"register_agent: request_cell {request_cell} is outside "
                f"window {wid}'s own tile {wcb['rect']} — agents emit from "
                "inside their fence, never across it")
        self._agents[wid] = {"request_cell": request_cell}

    def harvest(self) -> int:
        """Read every registered agent's request word (post-run, its task
        must have completed via comp.run_all()); accept well-formed words
        onto the toast queue and ZERO the slot (consumption is real).
        Returns the number of toasts enqueued. A word with a bad magic is
        quarantined LOUD (NotifyError) and its slot still consumed."""
        enqueued = 0
        for wid, info in self._agents.items():
            wcb = self.comp.window(wid)
            cpu = self.comp._table.tasks[wcb["pid"]]["cpu"]
            r, c = info["request_cell"]
            addr = r * W_MEM + c
            word = cpu.memory[addr]
            cpu.memory[addr] = 0           # consume, then judge
            if word == 0:
                continue                   # no alert this round (N2)
            magic, level, payload = decode_request(word)
            if magic != REQUEST_MAGIC:
                raise NotifyError(
                    f"harvest: window {wid} request word {word:#010x} has "
                    f"magic {magic:#x} != {REQUEST_MAGIC:#x} — QUARANTINED")
            if level not in LEVELS:
                raise NotifyError(
                    f"harvest: window {wid} request level {level} out of "
                    f"range {LEVELS} — QUARANTINED")
            self.submit(level, payload)
            enqueued += 1
        return enqueued

    # ── queue (bounded; refusals never damage held state) ────────────────
    def submit(self, level: int, payload: int) -> dict:
        """Hold a toast on the queue. Loud refusals: bad level, queue
        full. A refused submit leaves the queue byte-identical."""
        if level not in LEVELS:
            raise NotifyError(
                f"submit: level {level} out of range {LEVELS} — refused, "
                "queue unchanged")
        if len(self._queue) >= QUEUE_CAP:
            raise NotifyError(
                f"submit: queue full ({QUEUE_CAP} held toasts) — refused, "
                "queue unchanged")
        entry = {"level": level, "payload": payload}
        self._queue.append(entry)
        return entry

    # ── dispatch (toasts go OVER content: compositor arrival-z) ─────────
    def dispatch(self, origin: tuple[int, int] | None = None) -> list[int]:
        """Place every held toast as a compositor window in a vertical
        stack starting at `origin` (default (STACK_TOP_ROW, W_MEM -
        TOAST_W)): later toasts land BELOW earlier ones, each at
        origin + i*TOAST_PITCH rows — all visible (no overlap on the
        stack itself). Returns the new toast wids, bottom->top."""
        base_row = origin[0] if origin else STACK_TOP_ROW
        base_col = origin[1] if origin else W_MEM - TOAST_W
        placed = []
        for i, entry in enumerate(self._queue):
            row = base_row + i * TOAST_PITCH
            wid = self.comp.place(self._toast_program(entry["payload"]),
                                  plane_origin=(row, base_col),
                                  size=(TOAST_H, TOAST_W),
                                  name=f"toast{entry['payload']}")
            self.comp.run_all()            # toast paints itself, fenced
            self._toasts.append(wid)
            placed.append(wid)
        self._queue = []
        return placed

    def expire_top(self) -> int:
        """Retire the OLDEST toast (the stack's top row — toasts are
        placed downward, so the oldest sits highest) and re-stack the
        survivors upward by one TOAST_PITCH via compositor move()
        (reaped-window record move — the landed fence is never
        re-armed). Retirement is
        set_visible(False) — the compositor's sanctioned removal (its
        records are append-only; a hidden toast drops out of hit_test
        AND composite(), the item-38 C6 pattern). Returns the retired
        wid."""
        if not self._toasts:
            raise NotifyError("expire_top: no toasts are up")
        top = self._toasts.pop(0)
        wcb = self.comp.window(top)
        r, _c, _h, _w = wcb["rect"]  # noqa: F841 — row kept for the re-stack predicate
        self.comp.set_visible(top, False)
        for wid in self._toasts:
            sw = self.comp.window(wid)
            sr, sc, sh, sw2 = sw["rect"]
            if sr > r:                     # was BELOW the expired toast
                self.comp.move(wid, (sr - TOAST_PITCH, sc))
        return top

    # ── tray ABI (item-33 respawn repaint idiom) ─────────────────────────
    def open_tray(self) -> int:
        """Place the tray window (a real fenced tile) and run its tray
        task, which paints one cell per registered applet."""
        if self._tray_wid is not None:
            wcb = self.comp.window(self._tray_wid)
            if wcb["state"] == 1:
                raise NotifyError("open_tray: the tray is already open")
        self._tray_wid = self.comp.place(
            self._tray_program(), plane_origin=(TRAY_ROW, 0),
            size=(1, TRAY_W), name="tray")
        self._seed_tray()
        self.comp.run_all()
        return self._tray_wid

    def register_applet(self, color: int) -> int:
        """Register an applet in the next free tray slot; REFUSES past
        TRAY_SLOTS with the tray record unchanged (no partial slot)."""
        if len(self._applets) >= TRAY_SLOTS:
            raise NotifyError(
                f"register_applet: tray full ({TRAY_SLOTS} slots) — refused, "
                "tray record unchanged")
        slot = len(self._applets)
        self._applets[slot] = {"color": color, "state": 0}
        if self._tray_wid is not None:
            self._repaint_tray()      # only when the tray window is open
        return slot

    def set_applet_state(self, slot: int, state: int) -> None:
        """Set an applet's state word and REPAINT the tray (fresh tray
        task, item-33 refresh idiom): the reactive applet leg."""
        if slot not in self._applets:
            raise NotifyError(f"set_applet_state: no applet in slot {slot}")
        self._applets[slot]["state"] = state
        if self._tray_wid is not None:
            self._repaint_tray()

    # ── queries ──────────────────────────────────────────────────────────
    def toasts_up(self) -> list[int]:
        return list(self._toasts)

    def held(self) -> int:
        return len(self._queue)

    def close(self) -> None:
        self.comp.close()
        self._om.close()

    # ── internals ────────────────────────────────────────────────────────
    def _toast_program(self, filled: int) -> np.ndarray:
        """The toast task: paint `filled` payload cells at its OWN tile
        origin (read from TILE_ROW/COL like the item-38 C7 painter), the
        rest of its row in the level background. All STs fenced."""
        return self._asm.assemble([
            f"LDI r20 {TILE_ROW_ADDR >> 2}",
            "LD r10 r20",
            f"LDI r21 {TILE_COL_ADDR >> 2}",
            "LD r11 r21",
            f"LDI r12 {W_MEM}",
            "MUL r10 r12",
            "ADD r10 r11",               # r10 = origin word
            f"LDI r13 {TOAST_W}",
            "LDI r14 0",                 # i
            "LDI r15 1",
            f"LDI r16 {filled}",
            ":loop",
            "CMP3 r14 r16",              # i < filled ?
            "JLT :fg",
            "LDI r17 0x202020",          # toast bg
            "JMP :st",
            ":fg",
            "LDI r17 0xF0F0F0",          # toast fg (payload cells)
            ":st",
            "ST r10 r17",
            "ADD r10 r15",
            "ADD r14 r15",
            "CMP3 r14 r13",              # i < TOAST_W ?
            "JLT :loop",
            "LDI r1 0",
            "SYSCALL r0 0x05",
            "HALT",
        ], width_instrs=8)

    def _tray_program(self) -> np.ndarray:
        """The tray task: copy TRAY_W seeded cell words through at its own
        tile row (zero words skipped — an empty slot paints nothing)."""
        b = TRAY_ROW * W_MEM
        lines = []
        for i in range(TRAY_W):
            lines += [
                f"LDI r13 {b + i}",
                "LD r14 r13",
                "LDI r19 0",
                "CMP r14 r19",
                f"JZ :skip{i}",
                "ST r13 r14",
                f":skip{i}",
            ]
        return self._asm.assemble(
            lines + ["LDI r1 0", "SYSCALL r0 0x05", "HALT"], width_instrs=8)

    def _seed_tray(self) -> None:
        """Kernel-class seed: applet cell words into the tray task's RAM
        (the guest copies them through — the paint is still guest-side)."""
        wcb = self.comp.window(self._tray_wid)
        cpu = self.comp._table.tasks[wcb["pid"]]["cpu"]
        b = TRAY_ROW * W_MEM
        cpu.memory[b] = 0xC0FFEE         # tray id cell (cell 0)
        for slot, info in self._applets.items():
            color = info["color"]
            state = info["state"]
            word = ((color & 0xFFFFFF) << 8) | (state & 0xFF)
            cpu.memory[b + TRAY_SLOT_OFFSET + slot] = word & 0xFFFFFF

    def _repaint_tray(self) -> None:
        """Respawn the tray task: retire the old tray window
        (set_visible False — the compositor's records are append-only)
        and place a FRESH task at the SAME locked rect, then re-run —
        the cooperative model's repaint (item-33 refresh idiom adapted
        to the compositor's contract)."""
        if self._tray_wid is None:
            raise NotifyError("repaint: the tray was never opened")
        self.comp.set_visible(self._tray_wid, False)
        self._tray_task_n += 1
        self._tray_wid = self.comp.place(
            self._tray_program(), plane_origin=(TRAY_ROW, 0),
            size=(1, TRAY_W), name=f"tray{self._tray_task_n}")
        self._seed_tray()
        self.comp.run_all()
