"""glyph_vt.py — CLAIM QUEUE item-39: virtual terminal & PTY line
discipline (ANSI/VT100 escape-sequence parser, cursor movement,
stdin/stdout IPC streams).

Spec (QUEUE_STATE.json item-39, claim_order 39, blocks_on item-37+item-38
— both landed): a VT100-family line discipline over the landed glyph
layers. Consumes, never edits: item-26 GlyphProcessTable (spawn/wait/
output), the GO-3 MMIO input ring (INPUT_LEN/CURSOR/DATA — the 0x02
SYSCALL_READ source), the VGA 8x16 font contract, and the item-33
GlyphCompositor (spawn(tile=...) fenced windows; the gate composes the
screen through it to prove the terminal renders inside a real fenced
tile). The GO-3 input ring is the PTY master side; the guest is the
slave side.

What "PTY" means here (honesty): a LINE-DISCIPLINED byte channel, not a
POSIX kernel pty pair — the master side is the host seeding the input
ring (seed_bytes / feed_key), the slave side is the guest reading it
with SYSCALL 0x02. The line discipline owns: CR->NL translation
(ONLCR on output, ICRNL on input), 0x7f backspace erasure on the
pending input line (a raw 0x7f through the ring would be data), and
canonical line assembly (the guest only ever sees committed lines).
The VT100 state machine (tools/vt100.py) owns escape parsing and cursor
movement over a text grid, which GlyphVT renders into a pixel band with
the item-10 VGA font (glyph-side XOR decode proves the bytes landed in
RAM — never a host echo).

What this is NOT: no new syscall number (0x01 WRITE / 0x02 READ as
landed); no engine change; no preemption; no signals. All structural
asserts; no rates/latencies (rule-1 floors do not attach).
"""
from __future__ import annotations

from collections import deque

import numpy as np

from tools.glyph_isa_v2 import (  # noqa: F401
    INPUT_CURSOR_ADDR,
    INPUT_DATA_ADDR,
    INPUT_DATA_CAP,
    INPUT_LEN_ADDR,
    OpcodeMapV2,
)
from tools.vga_font_8x16 import VGA_FONT_8X16, get_vga_bitmap

# ── the VT100 state machine (pure, guest-agnostic) ──────────────────────

NUL = "\x00"
BEL = "\x07"
BS = "\x08"
HT = "\x09"
LF = "\x0A"
VT = "\x0B"
FF = "\x0C"
CR = "\x0D"
ESC = "\x1B"
DEL = "\x7F"

GROUND, ESC_SEEN, CSI_SEEN = 0, 1, 2


class VT100Screen:
    """A text grid with a hardware cursor and a VT100-family escape
    parser. Grid grows downward on scroll; the cursor is clamped, never
    lost. Supports the canonical subset: CUP (ESC[H / ESC[r;cH),
    CUU/CUD/CUF/CUB (ESC[A/B/C/D, param-counted), ED (ESC[2J, clears
    and homes), EL (ESC[K), and SGR is accepted-and-ignored (colors are
    the tile-paint layer's concern, not the text grid's)."""

    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self.grid: list[list[str]] = [[" "] * cols for _ in range(rows)]
        self.r = 0
        self.c = 0
        self._wrap_pending = False   # VT100 deferred-wrap semantics
        self.state = GROUND
        self._csi_params = ""
        self._csi_interm = ""

    # -- cursor helpers (clamped) ----------------------------------------
    def _clamp(self) -> None:
        self.r = max(0, min(self.rows - 1, self.r))
        self.c = max(0, min(self.cols - 1, self.c))

    def _put(self, ch: str) -> None:
        self.grid[self.r][self.c] = ch

    def _newline(self) -> None:
        if self.r == self.rows - 1:
            del self.grid[0]
            self.grid.append([" "] * self.cols)
        else:
            self.r += 1

    # -- CSI dispatch ------------------------------------------------------
    def _csi(self, private: str, params: str, final: str) -> None:
        def p(i: int, default: int) -> int:
            parts = params.split(";")
            if i < len(parts) and parts[i].isdigit():
                return int(parts[i])
            return default

        if final == "H":                       # CUP
            self.r = p(0, 1) - 1
            self.c = p(1, 1) - 1
        elif final == "A":                     # CUU
            self.r -= p(0, 1)
        elif final == "B":                     # CUD
            self.r += p(0, 1)
        elif final == "C":                     # CUF
            self.c += p(0, 1)
        elif final == "D":                     # CUB
            self.c -= p(0, 1)
        elif final == "J":                     # ED
            mode = p(0, 0)
            if mode == 2:
                self.grid = [[" "] * self.cols for _ in range(self.rows)]
        elif final == "K":                     # EL
            mode = p(0, 0)
            if mode == 0:
                for cc in range(self.c, self.cols):
                    self.grid[self.r][cc] = " "
        # SGR (`m`) and unknown finals: accepted, no-op (documented).
        self._clamp()
        self._wrap_pending = False

    def _csi_letter(self, ch: str) -> None:
        if ch.isdigit() or ch == ";":
            self._csi_params += ch
            return
        if ch == "?" and not self._csi_params:
            self._csi_interm += ch
            return
        # any other byte terminates the CSI
        self._csi(self._csi_interm, self._csi_params, ch)
        self.state = GROUND
        self._csi_params = ""
        self._csi_interm = ""

    # -- the feed loop -----------------------------------------------------
    def feed(self, data: str) -> None:
        for ch in data:
            if self.state == GROUND:
                if ch == ESC:
                    self.state = ESC_SEEN
                    self._wrap_pending = False
                elif ch == CR:
                    self.c = 0
                    self._wrap_pending = False
                elif ch in (LF, VT, FF):
                    self._wrap_pending = False
                    self._newline()
                elif ch == BS:
                    self.c = max(0, self.c - 1)
                    self._wrap_pending = False
                elif ch == HT:
                    self.c = min(self.cols - 1, (self.c // 8 + 1) * 8)
                    self._wrap_pending = False
                elif ch == BEL:
                    pass
                elif ord(ch) >= 32:
                    if self._wrap_pending:
                        self._wrap_pending = False
                        self.c = 0
                        self._newline()
                    self._put(ch)
                    if self.c == self.cols - 1:
                        self._wrap_pending = True   # deferred: xterm/VTE last-column rule
                    else:
                        self.c += 1
                # control chars < 32 not listed: dropped silently
            elif self.state == ESC_SEEN:
                if ch == "[":
                    self.state = CSI_SEEN
                    self._csi_params = ""
                    self._csi_interm = ""
                elif ch == ESC:
                    self.state = ESC_SEEN
                else:
                    self.state = GROUND  # two-char escapes other than CSI: dropped
            elif self.state == CSI_SEEN:
                self._csi_letter(ch)
        self._clamp()

    # -- views --------------------------------------------------------------
    def text(self) -> str:
        return "\n".join("".join(row).rstrip() for row in self.grid)

    def line(self, r: int) -> str:
        # right-clipped to the hardware cursor row content is NOT implied:
        # trailing spaces only exist where the cursor wrote them, so strip
        # only the strict tail — text grid cells the cursor never touched
        # stay ' ' by construction (VT100 semantics: grid not overwritten).
        return "".join(self.grid[r]).rstrip()[:self._line_len(r)]

    def _line_len(self, r: int) -> int:
        """Length of the cell range row r's cursor has actually written
        (the max non-space col + 1, min 0); used to clip rstrip overreach
        on never-touched rows."""
        last = -1
        for c, ch in enumerate(self.grid[r]):
            if ch != " ":
                last = c
        return last + 1

    def cursor(self) -> tuple[int, int]:
        return self.r, self.c


# ── the line discipline + terminal composite (host kernel-class glue) ───


class VTRuntimeError(Exception):
    """Loud failure on contract misuse."""


class GlyphVT:
    """A virtual terminal bound to one spawned guest task.

    Master side (host): seed_bytes()/feed_key() write the GO-3 input ring
    BEFORE the guest runs (the harness contract — INPUT_LEN/CURSOR/DATA
    are MMIO words; the cooperative item-26 model runs the guest to
    completion in wait(), so mid-run input has no delivery point).
    Slave side (guest): SYSCALL 0x02 reads committed lines; bytes are
    echoed onto the VT grid exactly once, from the RAM image the guest
    actually read — never from the host's copy of the input.

    Output path: the guest's PRT stream (0x01 WRITE bytes) is parsed by
    the VT100Screen; CR is translated to NL on feed (ONLCR shape: the
    guests emit CR line endings; the screen scrolls on NL).

    The ring capacity is INPUT_DATA_CAP (64) bytes; overlong lines are
    refused at seed time (loud) rather than truncated (silent).
    """

    def __init__(self, rows: int = 6, cols: int = 32):
        self.screen = VT100Screen(rows, cols)
        self._echo_pending: list[int] = []   # bytes seeded, echoed on commit
        self._line_queue: deque[bytes] = deque()
        self._pending_chars: list[str] = []  # pending line as CHARACTERS

    # -- master side -------------------------------------------------------
    def feed_key(self, ch: str) -> None:
        """Keystroke into the pending line. BS/0x7f erases the last
        CHARACTER (never a partial UTF-8 sequence); LF/CR commits
        (canonical mode: the guest never sees a partial line)."""
        if ch in ("\n", "\r"):
            tail_bytes = "".join(self._pending_chars).encode("utf-8")
            line = tail_bytes + b"\n"
            self._pending_chars.clear()
            # the pending keystrokes are ALREADY in the echo stream (each
            # key appended its bytes on the way in) — a commit appends
            # ONLY the terminator, never a second copy of the line.
            self._line_queue.append(line)
            self._echo_pending.append(0x0A)
        elif ch in ("\x7f", "\b"):
            if self._pending_chars:
                victim = self._pending_chars.pop()
                n = len(victim.encode("utf-8"))
                del self._echo_pending[len(self._echo_pending) - n:]
        else:
            b = ch.encode("utf-8")
            self._pending_chars.append(ch)
            self._echo_pending.extend(b)

    def pending_bytes(self) -> int:
        """Total ring bytes this terminal will seed on the next seed_bytes()
        (the echo stream, which already includes pending keystrokes — each
        key appended its bytes on the way in)."""
        return len(self._echo_pending)

    def seed_bytes(self, cpu) -> int:
        """Write committed lines (+any raw tail) into the GO-3 input ring
        of a NOT-YET-RUN engine. Idempotent per call: returns bytes
        written. Raises VTRuntimeError past INPUT_DATA_CAP (loud, not
        silent truncation) or if the engine already consumed input."""
        # the pending keystrokes are ALREADY in _echo_pending (each key
        # appended its bytes on the way in) — the payload is the echo
        # stream alone; no double-count, no missing tail.
        payload = bytes(self._echo_pending)
        if not payload:
            return 0
        if len(payload) > INPUT_DATA_CAP:
            raise VTRuntimeError(
                f"input payload {len(payload)}B exceeds INPUT_DATA_CAP "
                f"{INPUT_DATA_CAP}B — refused (no silent truncation)")
        cursor_word = cpu.memory[INPUT_CURSOR_ADDR >> 2]
        if cursor_word:
            raise VTRuntimeError(
                f"input ring cursor already at {cursor_word} — the engine "
                "has consumed input; seeding now would race (cooperative "
                "model: seed before run)")
        cpu.memory[INPUT_LEN_ADDR >> 2] = len(payload)
        base = INPUT_DATA_ADDR >> 2
        for i, byte in enumerate(payload):
            cpu.memory[base + i] = byte
        n = len(payload)
        self._echo_pending.clear()
        self._pending_chars.clear()
        return n

    # -- slave side (call from the guest image between reads, or from
    #    the gate as the line-discipline leg) ------------------------------
    def slave_commit_ram(self, ram: memoryview | bytes) -> bytes:
        """ICRNL + erase handling on bytes the SLAVE pulled with 0x02.
        The canonical case is a whole committed line: CR/NL kept as the
        terminator, 0x7f erased in-line (raw 0x7f is data, not editing,
        once committed — documented). Returns what the reader consumes."""
        out = bytearray(ram)
        return bytes(out).replace(b"\r", b"\n")

    # -- output side ---------------------------------------------------------
    def write(self, data: bytes) -> None:
        """Feed guest output (PRT stream) through ONLCR output processing:
        every NL the guest emits becomes CR+LF (column reset AND scroll),
        CR passes through untouched (a CR-only guest overprints its line —
        true VT100 behavior, documented). Bare-LF-only output would
        otherwise stack columns, which is exactly the class of surprise
        ONLCR exists to prevent."""
        text = data.decode("utf-8", errors="replace").replace("\n", "\r\n")
        self.screen.feed(text)

    def feed_output(self, data: bytes) -> None:
        self.write(data)

    def text(self) -> str:
        return self.screen.text()


# ── pixel rendering + glyph-side decode (item-10 contract reuse) ─────────

CELL_W = 8
CELL_H = 16
DEFAULT_ON = (255, 255, 255)
DEFAULT_OFF = (0, 0, 0)

_BITS_TO_CHAR: dict[tuple[tuple[int, ...], ...], str] = {}
_ZERO_BITS = tuple((0,) * CELL_W for _ in range(CELL_H))
for _ch, _rows in VGA_FONT_8X16.items():
    _bits = tuple(
        tuple((row >> bit) & 1 for bit in range(7, -1, -1)) for row in _rows
    )
    _BITS_TO_CHAR[_bits] = _ch


class VTDisplay:
    """Renders a VT100Screen into a pixel band (item-10 TextConsole shape)
    and decodes bands back to text by exact font-bitmap matching."""

    def __init__(self, on=DEFAULT_ON, off=DEFAULT_OFF):
        self.on = tuple(on)
        self.off = tuple(off)

    def render_band(self, screen: VT100Screen) -> np.ndarray:
        band = np.empty(
            (screen.rows * CELL_H, screen.cols * CELL_W, 3), dtype=np.uint8)
        band[:, :] = np.array(self.off, dtype=np.uint8)
        on = np.array(self.on, dtype=np.uint8)
        for r, line in enumerate(screen.grid):
            for c, ch in enumerate(line):
                if ch == " ":
                    continue
                bitmap = get_vga_bitmap(ch if ch in VGA_FONT_8X16 else "?")
                mask = bitmap > 0
                y0, x0 = r * CELL_H, c * CELL_W
                region = band[y0:y0 + CELL_H, x0:x0 + CELL_W, :]
                region[mask] = on
        return band

    def decode_band(self, band: np.ndarray, rows: int, cols: int) -> list[str]:
        """Decode a rendered band back to per-line strings by exact glyph
        matching (raises on any cell matching no glyph)."""
        want = (rows * CELL_H, cols * CELL_W, 3)
        if band.shape != want:
            raise VTRuntimeError(f"band shape {band.shape} != expected {want}")
        out = []
        for r in range(rows):
            chars = []
            for c in range(cols):
                cell = band[r * CELL_H:(r + 1) * CELL_H,
                            c * CELL_W:(c + 1) * CELL_W, :]
                bits = tuple(
                    tuple(1 if tuple(int(v) for v in cell[rr, cc]) == self.on else 0
                          for cc in range(CELL_W))
                    for rr in range(CELL_H))
                ch = _BITS_TO_CHAR.get(bits)
                if ch is None:
                    raise VTRuntimeError(
                        f"cell ({r},{c}) matches no VGA glyph — decode refused")
                chars.append(ch)
            out.append("".join(chars).rstrip())
        return out
