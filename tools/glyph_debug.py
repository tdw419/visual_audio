#!/usr/bin/env python3
"""glyph_debug — interactive debugger for GlyphCPUv2 spatial images.

Wraps the engine's single-`step()` primitive with the four operations the
builder loop keeps re-deriving in throwaway output/dbg_* probes (664 and
counting as of 2026-09-10):

  1. debug_run()      — run with breakpoints / watchpoints / step budget
  2. diff_replay()    — run two images, report the FIRST divergence
  3. DebugSession     — load/seed/step/peek/poke REPL-style object
  4. postmortem()     — standardized fault report (the receipt format)

All functions are pure wrappers over GlyphCPUv2 — no engine changes, no
new dependencies. Import the baker module the SAME WAY every time
(tools.glyph_gpt.baker) to avoid the dual-module-instance bug (cron297).

Usage (standalone):
  python3 tools/glyph_debug.py image.npy                 # REPL
  python3 tools/glyph_debug.py a.npy b.npy               # diff replay

Usage (from a probe script):
  from tools.glyph_debug import DebugSession, debug_run, diff_replay, postmortem
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
from glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2, INSTR_WIDTH  # noqa: E402

# Words worth showing in a default state dump (ABI constants live here)
_ABI_WORDS = {
    "status_950": 950, "stdout_718": 718, "stdout_719": 719,
    "exit_720": 720, "brk_723": 723, "bus_700": 700, "result_754": 754,
}


def load_image(path: str) -> np.ndarray:
    return np.load(path)


def new_cpu(cols_instrs: int = 8) -> GlyphCPUv2:
    return GlyphCPUv2(OpcodeMapV2(), cols_instrs=cols_instrs)


def fmt_state(cpu: GlyphCPUv2, mem_words: Optional[List[int]] = None) -> str:
    """One standardized state block — the format the receipts keep hand-rolling."""
    r = cpu.registers
    lines = [
        f"pc=({cpu.pc[0]},{cpu.pc[1]}) mode={'USER' if cpu.mode == 1 else 'SUPER'} "
        f"running={cpu.running} faulted={cpu.faulted}",
        f"r0={r[0]:#010x} r1={r[1]:#010x} r2(sp)={r[2]:#010x} r17(sysn)={r[17]:#010x}",
        f"r30={r[30]:#010x} r31(hwsp)={r[31]:#010x}",
    ]
    words = dict(_ABI_WORDS)
    if mem_words:
        words.update({f"mem[{w}]": w for w in mem_words})
    dump = " ".join(f"{k}={cpu.memory[w] if w < len(cpu.memory) else '?':#x}"
                    for k, w in words.items())
    lines.append(dump)
    if cpu.faulted:
        lines.append(f"FAULT addr={cpu.fault_addr:#010x} pc={cpu.fault_pc:#010x}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 1. debug_run — breakpoints / watchpoints
# ---------------------------------------------------------------------------

def debug_run(
    cpu: GlyphCPUv2,
    image: np.ndarray,
    max_steps: int = 100_000,
    break_when: Optional[Callable[[GlyphCPUv2], bool]] = None,
    watch: Optional[Dict[int, str]] = None,
    on_hit: Optional[Callable[[GlyphCPUv2, int, str], None]] = None,
) -> List[Tuple[int, str]]:
    """Step until a breakpoint/watchpoint fires or the budget expires.

    break_when(cpu)  — halt when it returns True (checked BEFORE each step)
    watch = {word: label} — halt the first time any listed word CHANGES value
    on_hit(cpu, step, reason) — callback (default: print state and stop)
    Returns the event log [(step, reason), ...].
    """
    events: List[Tuple[int, str]] = []
    prev_watch_vals = {w: (cpu.memory[w] if w < len(cpu.memory) else 0)
                       for w in (watch or {})}
    for n in range(max_steps):
        if break_when and break_when(cpu):
            reason = f"breakpoint at step {n}"
            events.append((n, reason))
            (on_hit or (lambda c, s, r: print(f"[halt] {r}\n{fmt_state(c)}")))(cpu, n, reason)
            return events
        if not cpu.running:
            reason = f"halted at step {n} (faulted={cpu.faulted})"
            events.append((n, reason))
            (on_hit or (lambda c, s, r: print(f"[halt] {r}\n{fmt_state(c)}")))(cpu, n, reason)
            return events
        cpu.step(image)
        for w, label in (watch or {}).items():
            cur = cpu.memory[w] if w < len(cpu.memory) else 0
            if cur != prev_watch_vals[w]:
                reason = f"step {n}: watch {label or hex(w)} changed {prev_watch_vals[w]:#x} -> {cur:#x}"
                events.append((n, reason))
                (on_hit or (lambda c, s, r: print(f"[watch] {r}\n{fmt_state(c)}")))(cpu, n, reason)
                prev_watch_vals[w] = cur
    events.append((max_steps, "step budget exhausted"))
    return events


# ---------------------------------------------------------------------------
# 2. diff_replay — first divergence between two images
# ---------------------------------------------------------------------------

def diff_replay(
    image_a: np.ndarray,
    image_b: np.ndarray,
    cols_instrs: int = 8,
    max_steps: int = 200_000,
    watch_words: Optional[List[int]] = None,
) -> Optional[Dict]:
    """Run both images in lockstep; report the FIRST divergence.

    Divergence = pc, mode, register-file, or any watch_words value differing.
    Returns None if both run to identical halts within budget.
    """
    ca, cb = new_cpu(cols_instrs), new_cpu(cols_instrs)
    ca.running = cb.running = True
    watch = set(watch_words or [])
    for n in range(max_steps):
        if not (ca.running and cb.running):
            if ca.running != cb.running:
                return {"step": n, "kind": "liveness", "a": _snap(ca), "b": _snap(cb)}
            if ca.faulted != cb.faulted:
                return {"step": n, "kind": "fault", "a": _snap(ca), "b": _snap(cb)}
            if ca.output != cb.output:
                return {"step": n, "kind": "output", "a": _snap(ca), "b": _snap(cb)}
            return None
        ca.step(image_a)
        cb.step(image_b)
        if ca.pc != cb.pc:
            return {"step": n, "kind": "pc", "a": _snap(ca), "b": _snap(cb)}
        if ca.registers != cb.registers:
            for i, (x, y) in enumerate(zip(ca.registers, cb.registers)):
                if x != y:
                    return {"step": n, "kind": f"r{i}", "a": _snap(ca), "b": _snap(cb)}
        if ca.output != cb.output:
            return {"step": n, "kind": "output", "a": _snap(ca), "b": _snap(cb)}
        for w in watch:
            va = ca.memory[w] if w < len(ca.memory) else 0
            vb = cb.memory[w] if w < len(cb.memory) else 0
            if va != vb:
                return {"step": n, "kind": f"mem[{w}]", "a": _snap(ca), "b": _snap(cb)}
    return {"step": max_steps, "kind": "budget", "a": _snap(ca), "b": _snap(cb)}


def _snap(cpu: GlyphCPUv2) -> Dict:
    return {"pc": cpu.pc, "mode": cpu.mode, "regs": list(cpu.registers),
            "faulted": cpu.faulted, "fault_addr": cpu.fault_addr}


# ---------------------------------------------------------------------------
# 3. DebugSession — seed / step / peek / poke
# ---------------------------------------------------------------------------

class DebugSession:
    """REPL-style harness: load image, seed words, step, inspect, resume."""

    def __init__(self, image_path: str, cols_instrs: int = 8):
        self.image = load_image(image_path)
        self.cpu = new_cpu(cols_instrs)
        self.cpu.running = True
        self.step_count = 0

    # -- seeding ----------------------------------------------------------
    def seed_word(self, word_addr: int, value: int) -> "DebugSession":
        """Seed a memory word (addr in WORDS, matching engine mem[] layout)."""
        while (word_addr) >= len(self.cpu.memory):
            self.cpu.memory.extend([0] * 256)
        self.cpu.memory[word_addr] = value & 0xFFFFFFFF
        return self

    def seed_registers(self, **regs: int) -> "DebugSession":
        for name, val in regs.items():
            idx = int(name.lstrip("r"))
            self.cpu.registers[idx] = val & 0xFFFFFFFF
        return self

    def start_at(self, col_instr: int, row: int) -> "DebugSession":
        self.cpu.pc = (col_instr * INSTR_WIDTH, row)
        return self

    # -- execution --------------------------------------------------------
    def step(self, n: int = 1) -> "DebugSession":
        for _ in range(n):
            if not self.cpu.running:
                break
            self.cpu.step(self.image)
            self.step_count += 1
        return self

    def run(self, max_steps: int = 100_000) -> "DebugSession":
        self.cpu.run(self.image, max_instructions=max_steps)
        return self

    # -- inspection -------------------------------------------------------
    def peek(self, word_addr: int) -> int:
        return self.cpu.memory[word_addr] if word_addr < len(self.cpu.memory) else 0

    def poke(self, word_addr: int, value: int) -> "DebugSession":
        return self.seed_word(word_addr, value)

    def state(self, mem_words: Optional[List[int]] = None) -> str:
        return fmt_state(self.cpu, mem_words)

    def repl(self):
        """Tiny interactive loop: step [n] | peek w | poke w v | regs | q"""
        while True:
            try:
                cmd = input(f"[step {self.step_count}] db> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if cmd in ("q", "quit", ""):
                break
            parts = cmd.split()
            try:
                if parts[0] == "step":
                    self.step(int(parts[1]) if len(parts) > 1 else 1)
                    print(self.state())
                elif parts[0] == "peek" and len(parts) > 1:
                    print(f"mem[{parts[1]}] = {self.peek(int(parts[1], 0)):#010x}")
                elif parts[0] == "poke" and len(parts) > 2:
                    self.poke(int(parts[1], 0), int(parts[2], 0))
                    print("ok")
                elif parts[0] == "regs":
                    print(self.state())
                else:
                    print("commands: step [n] | peek <word> | poke <word> <val> | regs | q")
            except Exception as e:  # keep the REPL alive
                print(f"error: {e}")


# ---------------------------------------------------------------------------
# 4. postmortem — standardized fault receipt
# ---------------------------------------------------------------------------

def postmortem(cpu: GlyphCPUv2, extra_words: Optional[List[int]] = None) -> str:
    """The receipt block for a faulted/halted run — paste into gate reports."""
    head = "POSTMORTEM\n" + "=" * 40
    return head + "\n" + fmt_state(cpu, extra_words)


# ---------------------------------------------------------------------------

def main(argv: List[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(argv) >= 2 and argv[1] in ("-h", "--help") else 1
    if len(argv) >= 3:
        d = diff_replay(load_image(argv[1]), load_image(argv[2]))
        if d is None:
            print("IDENTICAL: no divergence within budget")
        else:
            print(f"DIVERGED at step {d['step']} ({d['kind']}):")
            for tag in ("a", "b"):
                s = d[tag]
                print(f"  {tag}: pc={s['pc']} mode={s['mode']} faulted={s['faulted']} "
                      f"r2={s['regs'][2]:#x} r31={s['regs'][31]:#x}")
        return 0
    if len(argv) == 2:
        DebugSession(argv[1]).repl()
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
