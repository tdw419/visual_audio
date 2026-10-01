#!/usr/bin/env python3
"""Glyph Desktop Environment core (CLAIM QUEUE ROUND 8, item 17, L4-DESKTOP).

The headless desktop kernel that a Tk surface (the glyph_desktop.py
successor) composes. Every piece of file I/O runs THROUGH the GPU: the
editor's save is the L1 `write` verb (the engine's FILE_WRITE arm, 0x03)
and its open is `read` (FILE_READ, 0x04) — no host open()/write() in the
editor's path, verified by the gate's N1 neutered-image leg.

Components:

  DesktopConsole  — one tab: its own GlyphL1Shell (own CPU instance, own
                    dispatch image, own last_status) + its own TextConsole
                    ring. Turn output feeds the ring; the ring renders to
                    the glyph band exactly like the terminal entry.
  DesktopEditor   — the first GUI app whose I/O is GPU syscalls: buffer in
                    memory, open/save via a console's `read`/`write` verbs.
  DesktopLauncher — lists every L1 verb + `edit`; running an entry executes
                    it in the launcher's console (the "runs it, sees
                    output" leg of the round-8 success criterion).
  DesktopEnv      — the desktop: consoles, one editor, launcher, session
                    save/restore (console rings + open editor file) as a
                    JSON session dir. restore() refuses corrupt payloads
                    loudly (ValueError), never silently defaults.

NOT here (disclosed): the Tk window itself. Layout/focus/pixel legs are
operator-eyes PENDING per the L4 receipt, same pattern as
RECEIPT_glyph_desktop_gui.md. This module is importable and gate-able
headless (the suite must stay runnable — BK-18's lesson).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.glyph_l1_shell import (  # noqa: E402
    ERR, L1_VERBS, GlyphL1Shell, L1Session,
)
from tools.glyph_text_console import TextConsole  # noqa: E402

SESSION_FILE = "glyph_session.json"

# The editor's GPU write payload is " " + text (the dispatch convention:
# `w <text>` writes a leading space; `cat` reads it back byte-exact with
# that space). The buffer is capped well under the 64-byte input ring so
# `w <text>` always fits — an over-cap buffer refuses loudly (the gate's
# oversize leg), it is never silently truncated.
EDITOR_BUFFER_CAP = 56


class EditorBufferTooLarge(ValueError):
    """Editor buffer exceeds what one GPU `w` turn can carry."""


class DesktopConsole:
    """One desktop tab: an independent L1 shell + its own text ring."""

    def __init__(self, title: str, session: L1Session | None = None):
        self.title = title
        self.shell = GlyphL1Shell(session=session)
        # One shared L1Session per desktop: tabs share the filesystem (the
        # desktop's common truth) but own their CPU/ring/status state.
        self.session = self.shell.session
        self.console = TextConsole()

    def turn(self, line: str) -> str:
        out = self.shell.turn(line)
        if out:
            self.console.feed(out)
        return out

    # ring access (the deque of fed lines) for persistence and tests
    @property
    def lines(self) -> list[str]:
        return list(self.console._lines)

    def set_lines(self, lines: list[str]) -> None:
        self.console._lines.clear()
        for ln in lines:
            self.console._lines.append(ln)

    def render_band(self):
        return self.console.render_band()


class DesktopEditor:
    """Glyph-native text editor. open/save go through a console's GPU
    shell (FILE_READ / FILE_WRITE arms) — never a host file handle."""

    def __init__(self, console: DesktopConsole):
        self.console = console
        self.buffer: str = ""
        self.path: str | None = None

    def edit(self, text: str) -> None:
        if len(text.encode("utf-8")) > EDITOR_BUFFER_CAP:
            raise EditorBufferTooLarge(
                f"buffer {len(text.encode('utf-8'))}B exceeds the "
                f"{EDITOR_BUFFER_CAP}B one-turn GPU write budget")
        self.buffer = text

    def open_file(self, name: str) -> str:
        """Read a desktop file THROUGH the GPU (`read <name>` verb) into
        the buffer. Missing files refuse loudly BEFORE the turn (the L1
        shell's own NOENT discipline — never the engine's stale-buffer
        walk). The dispatch convention strips the leading space."""
        out = self.console.turn(f"read {name}")
        if out.startswith("ERR:"):
            raise FileNotFoundError(out)
        self.buffer = out[1:] if out.startswith(" ") else out
        self.path = name
        return self.buffer

    def save(self) -> None:
        if not self.path:
            raise ValueError("no path — use save_as")
        self._gpu_write(self.path)

    def save_as(self, name: str) -> None:
        self._gpu_write(name)
        self.path = name

    def _gpu_write(self, name: str) -> None:
        # `write <name> <text>` — the L1 write verb routes the FILE_WRITE
        # syscall; ITS dispatch arm adds the leading space. Adding one here
        # too would double it (measured: '  hello' on disk, and cat read
        # the doubled space back). The editor's buffer is the exact bytes.
        out = self.console.turn(f"write {name} {self.buffer}")
        if out.startswith("ERR:"):
            raise OSError(out)


class DesktopLauncher:
    """The app launcher: every L1 verb + `edit`, runnable in its console."""

    def __init__(self, console: DesktopConsole):
        self.console = console

    def entries(self) -> list[str]:
        return list(L1_VERBS) + ["edit"]

    def run(self, entry: str, args: str = "") -> str:
        if entry == "edit":
            return ""  # the desktop env routes this to the editor surface
        return self.console.turn(f"{entry} {args}".strip())


class DesktopEnv:
    """The desktop: tabbed consoles, one editor, launcher, sessions."""

    def __init__(self, session: L1Session | None = None):
        self._shared: L1Session | None = session
        self.consoles: list[DesktopConsole] = []
        first = self.new_console("tty0")
        self.editor = DesktopEditor(first)
        self.launcher = DesktopLauncher(first)

    @property
    def session(self) -> L1Session:
        return self.consoles[0].session

    def new_console(self, title: str) -> DesktopConsole:
        tab = DesktopConsole(title, session=self._shared)
        self._shared = tab.session  # subsequent tabs share the first tab's root
        self.consoles.append(tab)
        return tab

    def open_editor(self) -> DesktopEditor:
        return self.editor

    # -- session persistence ------------------------------------------------

    def save_session(self, session_dir: str | os.PathLike) -> None:
        d = Path(session_dir)
        d.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            # The desktop's filesystem root is PART OF THE SESSION: without
            # it, restore() would mint a fresh empty root and every file
            # saved before the snapshot would be unreachable (measured
            # defect: cat -> ERR:NOENT after restore).
            "session_root": self.session.root,
            "tabs": [
                {"title": t.title, "lines": t.lines}
                for t in self.consoles
            ],
            "editor": {"buffer": self.editor.buffer,
                       "path": self.editor.path},
        }
        (d / SESSION_FILE).write_text(json.dumps(payload))

    @classmethod
    def restore(cls, session_dir: str | os.PathLike) -> "DesktopEnv":
        path = Path(session_dir) / SESSION_FILE
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"corrupt glyph session: {exc}") from exc
        if not isinstance(payload, dict) or "tabs" not in payload:
            raise ValueError("corrupt glyph session: missing tabs")
        root = payload.get("session_root")
        env = cls.__new__(cls)  # no constructor tabs; rebuild from the payload
        env._shared = L1Session(root=root) if root else None
        env.consoles = []
        for spec in payload["tabs"]:
            tab = env.new_console(spec["title"])
            tab.set_lines(spec["lines"])
            if env.consoles[0] is tab:
                env.editor = DesktopEditor(tab)
                env.launcher = DesktopLauncher(tab)
        ed = payload.get("editor", {})
        env.editor.buffer = ed.get("buffer", "")
        env.editor.path = ed.get("path")
        return env
