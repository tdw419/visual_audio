#!/usr/bin/env python3
"""Glyph Desktop — a consumer-grade GUI wrapper around the Glyph GPU OS shell.

Drop-in GUI companion to `python3 experiments/glyph_interactive_shell.py`.
Same dispatch shell (e/s/w/r/quit), same grammar, same ERR:UNKNOWN_CMD
discipline — plus a real desktop window:

  - a scrollable human transcript (the shell's output, rendered large)
  - a live view of the GPU's own text console band (the glass-TTY pixels,
    re-rendered from the TextConsole after every turn — the same PNG the
    terminal path saves, glyph-decodable by construction)
  - an entry box with the one-command-per-line grammar

Nothing about the engine, the shell program, or the gates changes. This is
pure surface: the same run_turn() the batch tests and terminal repl use,
the same TextConsole, the same console-band PNG artifact.

Usage:
    python3 glyph_desktop.py
Env: same overrides as the terminal entry (GLYPH_SH_WRITE_PATH,
GLYPH_SH_AUDIO_PATH, GLYPH_SH_CONSOLE_PNG).
"""
from __future__ import annotations

import os
import sys
import threading
import queue

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "tools"))

from experiments.glyph_interactive_shell import (  # noqa: E402
    build_dispatch_shell,
    run_turn,
    GlyphCPUv2,
    OpcodeMapV2,
    W,
)
from tools.glyph_text_console import TextConsole, save_png  # noqa: E402

import tkinter as tk  # noqa: E402
from tkinter import scrolledtext  # noqa: E402
from PIL import Image, ImageTk  # noqa: E402

FS_PIX_ENABLED = True  # TASK_SE020 dispatch shell needs FS-pixel windowing


class GlyphDesktop:
    def __init__(self) -> None:
        self.write_path = os.environ.get(
            "GLYPH_SH_WRITE_PATH", "/tmp/glyph_sh_write.dat")
        self.audio_path = os.environ.get(
            "GLYPH_SH_AUDIO_PATH", "/tmp/glyph_sh_audio.wav")
        self.band_path = os.environ.get(
            "GLYPH_SH_CONSOLE_PNG", "/tmp/glyph_sh_console_band.png")

        # The machine — identical construction to the terminal entry point.
        self.cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=W,
                              fs_pix_enabled=FS_PIX_ENABLED)
        self.cpu.memory = [0] * 16384
        self.image = build_dispatch_shell(self.write_path, self.audio_path)
        self.console = TextConsole()

        self.q: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self._build_ui()
        self._banner()
        self.after_poll()

    # ---------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        self.root = tk.Tk()
        self.root.title("Glyph Desktop — GPU OS")
        self.root.geometry("900x580")

        body = tk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True)

        # Left: the human transcript.
        self.transcript = scrolledtext.ScrolledText(
            body, width=54, height=24, font=("TkFixedFont", 11),
            bg="#101014", fg="#e8e8e8", insertbackground="#e8e8e8",
            state=tk.DISABLED)
        self.transcript.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                             padx=(8, 4), pady=8)

        # Right: the GPU's own screen (its console band, 2x).
        right = tk.Frame(body)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(4, 8), pady=8)
        tk.Label(right, text="GPU screen (glass-TTY, glyph-decodable)",
                 font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        self.screen = tk.Label(right, bg="#000000", bd=1, relief=tk.SOLID)
        self.screen.pack(fill=tk.BOTH, expand=True)
        tk.Label(right, text=f"band PNG: {self.band_path}",
                 font=("TkFixedFont", 7), fg="#666666").pack(anchor="w")

        # Entry row.
        entry_row = tk.Frame(self.root)
        entry_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        tk.Label(entry_row, text="glyph>",
                 font=("TkFixedFont", 11, "bold")).pack(side=tk.LEFT)
        self.entry = tk.Entry(entry_row, font=("TkFixedFont", 12))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.entry.bind("<Return>", self.on_submit)
        self.entry.focus_set()
        tk.Button(entry_row, text="run", width=6,
                  command=self.on_submit).pack(side=tk.LEFT)

    def _say(self, text: str) -> None:
        self.transcript.configure(state=tk.NORMAL)
        self.transcript.insert(tk.END, text + "\n")
        self.transcript.see(tk.END)
        self.transcript.configure(state=tk.DISABLED)

    def _banner(self) -> None:
        self._say("Glyph interactive shell (dispatch mode) - GPU native.")
        self._say("Commands (one letter, then a space):")
        self._say("  e <text>   echo the text back")
        self._say(f"  s <text>   speak the text (AUDIO_OUT -> {self.audio_path})")
        self._say(f"  w <text>   write the text to {self.write_path}")
        self._say("  r          read that file back")
        self._say("  quit       exit")
        self._say("  grammar: the byte after the command MUST be a space;")
        self._say("           anything else answers ERR:UNKNOWN_CMD - nothing")
        self._say("           is ever executed silently.")

    # --------------------------------------------------- engine plumbing
    def on_submit(self, event=None) -> None:
        line = self.entry.get()
        self.entry.delete(0, tk.END)
        if not line.strip():
            return
        self._say(f"glyph> {line}")
        if line.strip() == "quit":
            self._shutdown()
            return
        # Engine turn on a worker thread: the GPU run is fast, but the WAV
        # encode and PNG save are host I/O; keep the window responsive.
        threading.Thread(target=self._run_line, args=(line,),
                         daemon=True).start()

    def _run_line(self, line: str) -> None:
        try:
            echoed_bytes = run_turn(self.cpu, self.image, line)
        except Exception as exc:  # engine faults surface here, not as crashes
            self.q.put(("err", repr(exc)))
            return
        echoed = "".join(chr(b) for b in echoed_bytes)
        self.console.feed_bytes(bytes(echoed_bytes))
        self.q.put(("out", echoed))

    def after_poll(self) -> None:
        try:
            while True:
                kind, text = self.q.get_nowait()
                if kind == "out":
                    self._say(f"  {text}" if text else "  (no output)")
                elif kind == "err":
                    self._say(f"  [engine error] {text}")
                self._refresh_screen()
        except queue.Empty:
            pass
        self.root.after(80, self.after_poll)

    def _refresh_screen(self) -> None:
        band = self.console.render_band()
        save_png(band, self.band_path)  # same artifact the terminal path writes
        img = Image.fromarray(band)
        # 2x nearest-neighbour so the 8x16 cells read at desktop size.
        img = img.resize((band.shape[1] * 2, band.shape[0] * 2), Image.NEAREST)
        self._photo = ImageTk.PhotoImage(img)
        self.screen.configure(image=self._photo)

    def _shutdown(self) -> None:
        try:
            save_png(self.console.render_band(), self.band_path)
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = GlyphDesktop()
    app.run()


if __name__ == "__main__":
    main()
