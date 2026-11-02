"""BK-282 G1 + G2 + G3 — Interactive GPU OS Calculator kernel.

GLYPH ISA ARITHMETIC FORM (load-bearing discovery, measured 2026-10-08
~20:3x CDT, manual lane): ADD/SUB/MUL/DIV are ACCUMULATOR-form:

    ADD rd, rs2 : rd = rd + rs2   (glyph_isa_v2.py:1169)
    SUB rd, rs2 : rd = rd - rs2   (:1171)
    MUL rd, rs2 : rd = rd * rs2   (:1173)

The assembler accepts a third operand and the executor IGNORES it. Every
program below pre-loads rd and uses two-operand accumulator form. This ISA
quirk is exactly what FACT-4's proof index exists to record.

DESIGN: one Glyph program per keystroke/operation, fresh-spawn on a
persistent-RAM GlyphCPUv2 (pc reset per GH-27; RAM persists). Pixels do
the arithmetic. Host sequences programs; answers render via the BK-19
TextConsole.

GATE 2 (Precedence):
Two-level precedence grammar (+/- vs */div). Multiplicative/divisive terms
are accumulated in RAM[TERM] before being folded into additive RAM[ACC].

GATE 3 (Error Defense & Division):
- Division operator '/' implemented via Glyph repeated-subtraction loop.
- Division by zero emits loud 'ERR:DIV0'.
- Syntax errors (empty, consecutive ops, leading op, trailing op) emit 'ERR:SYNTAX'.
- Fast exit on error, no hang or step-cap exhaustion.

RAM MAP (persistent across keystrokes; pc is not)
  64   keystroke byte (GO-3 ring word)
  100  accumulator (LHS additive sum)
  101  operand (digits as they arrive)
  102  pending op (for debugging/inspection)
  103  result-ready flag
  104  has-operand flag
  105  multiplicative/divisive term accumulator
"""

from __future__ import annotations

from tools.glyph_isa_v2 import (
    GlyphAssemblerV2,
    GlyphCPUv2,
    OpcodeMapV2,
)
from tools.glyph_text_console import TextConsole

RING_WORD = 64
ACC = 100
OPERAND = 101
OP = 102
READY = 103
HAS_OPERAND = 104
TERM = 105

DIGIT, OPER, EQUALS, OTHER = "digit", "oper", "equals", "other"


def _classify(ch: str) -> str:
    if ch.isdigit():
        return DIGIT
    if ch in ("+", "-", "*", "/"):
        return OPER
    if ch == "=":
        return EQUALS
    return OTHER


class CalculatorSession:
    """Persistent-RAM calculator supporting multi-digit numbers, standard
    operator precedence (* / over + -), and robust error defense (ERR:DIV0,
    ERR:SYNTAX). Arithmetic executes as assembled Glyph programs on GlyphCPUv2."""

    def __init__(self) -> None:
        self.om = OpcodeMapV2()
        self.asm = GlyphAssemblerV2(self.om)
        self.cpu = GlyphCPUv2(self.om, cols_instrs=64)
        self._console = TextConsole()
        self._steps_total = 0
        self._console_text = ""
        self._pending_add_op: str = ""
        self._pending_mul_op: str = ""
        self._in_error: bool = False
        self._has_typed_any_digit: bool = False
        self._last_was_op: bool = False

    # -- glyph program generators -------------------------------------------
    def _prog_digit(self) -> list[str]:
        """operand = operand*10 + (ch-48) in Glyph accumulator form."""
        return [
            f"LDI r2 {OPERAND}", "LD r3 r2",       # r3 = operand
            f"LDI r4 {RING_WORD}", "LD r5 r4",     # r5 = ch
            "LDI r6 48",
            "SUB r5 r6",                            # r5 = ch-48
            "LDI r8 10",
            "MUL r3 r8",                            # r3 = operand*10
            "ADD r3 r5",                            # r3 = operand*10 + digit
            "ST r2 r3",                             # RAM[OPERAND] = r3
            f"LDI r11 {HAS_OPERAND}", "LDI r12 1", "ST r11 r12",
            "HALT",
        ]

    def _prog_assign(self, dest: int, src: int, clear_src: bool = True, set_ready: bool = False) -> list[str]:
        """RAM[dest] = RAM[src]; optionally RAM[src] = 0."""
        prog = [
            f"LDI r2 {src}", "LD r3 r2",
            f"LDI r4 {dest}", "ST r4 r3",
        ]
        if clear_src:
            prog.extend([f"LDI r5 0", f"ST r2 r5"])
        if set_ready:
            prog.extend([f"LDI r6 {READY}", "LDI r7 1", "ST r6 r7"])
        prog.append("HALT")
        return prog

    def _prog_mul_term(self) -> list[str]:
        """term = term * operand; operand = 0."""
        return [
            f"LDI r2 {TERM}", "LD r3 r2",
            f"LDI r4 {OPERAND}", "LD r5 r4",
            "MUL r3 r5",
            "ST r2 r3",
            f"LDI r6 0", "ST r4 r6",
            "HALT",
        ]

    def _prog_div_term(self) -> list[str]:
        """term = term // operand (integer division loop); operand = 0."""
        return [
            f"LDI r2 {TERM}", "LD r3 r2",           # r3 = dividend
            f"LDI r4 {OPERAND}", "LD r5 r4",        # r5 = divisor
            "LDI r7 0",                             # r7 = quotient
            ":div_loop",
            "CMP3 r3 r5",
            "JLT :div_done",
            "SUB r3 r5",                            # r3 = r3 - r5
            "LDI r8 1",
            "ADD r7 r8",                            # r7 = r7 + 1
            "JMP :div_loop",
            ":div_done",
            "ST r2 r7",                             # RAM[TERM] = quotient
            f"LDI r6 0", "ST r4 r6",
            "HALT",
        ]

    def _prog_fold_add(self, op: str, src: int, clear_src: bool = True, set_ready: bool = False) -> list[str]:
        """acc = acc OP RAM[src]; optionally RAM[src] = 0; optionally READY=1."""
        gate = "ADD" if op == "+" else "SUB"
        prog = [
            f"LDI r2 {ACC}", "LD r3 r2",
            f"LDI r4 {src}", "LD r5 r4",
            f"{gate} r3 r5",
            "ST r2 r3",
        ]
        if clear_src:
            prog.extend([f"LDI r6 0", f"ST r4 r6"])
        if set_ready:
            prog.extend([f"LDI r7 {READY}", "LDI r8 1", "ST r7 r8"])
        prog.append("HALT")
        return prog

    def _run_prog(self, prog: list[str]) -> None:
        self.cpu.pc = (0, 0)
        image = self.asm.assemble(prog, width_instrs=64)
        self._steps_total += self.cpu.run(image, max_instructions=80)

    # -- public API ----------------------------------------------------------
    def type_digits(self, text: str) -> None:
        for ch in text:
            self._keystroke(ch)
            if self._in_error:
                break

    def _emit_error(self, err_code: str) -> None:
        self._in_error = True
        self._console_text = err_code
        self._console.feed(self._console_text)

    def _fold_pending_mul(self) -> bool:
        """Folds pending mul/div into TERM. Returns False on divide by zero."""
        if self._pending_mul_op == "*":
            self._run_prog(self._prog_mul_term())
        elif self._pending_mul_op == "/":
            divisor = self.cpu.memory[OPERAND]
            if divisor == 0:
                self._emit_error("ERR:DIV0")
                return False
            self._run_prog(self._prog_div_term())
        return True

    def _keystroke(self, ch: str) -> None:
        if self._in_error:
            return

        kind = _classify(ch)
        if kind == OTHER:
            return

        self.cpu.memory[RING_WORD] = ord(ch)

        if kind == DIGIT:
            self._has_typed_any_digit = True
            self._last_was_op = False
            self._run_prog(self._prog_digit())

        elif kind == OPER:
            # Syntax validation: leading operator or consecutive operators
            if not self._has_typed_any_digit or self._last_was_op:
                self._emit_error("ERR:SYNTAX")
                return

            self._last_was_op = True

            if ch in ("*", "/"):
                if self._pending_mul_op in ("*", "/"):
                    if not self._fold_pending_mul():
                        return
                else:
                    self._run_prog(self._prog_assign(dest=TERM, src=OPERAND, clear_src=True))
                self._pending_mul_op = ch
            else:  # "+" or "-"
                if self._pending_mul_op in ("*", "/"):
                    if not self._fold_pending_mul():
                        return
                    if self._pending_add_op == "":
                        self._run_prog(self._prog_assign(dest=ACC, src=TERM, clear_src=True))
                    else:
                        self._run_prog(self._prog_fold_add(self._pending_add_op, src=TERM, clear_src=True))
                    self._pending_mul_op = ""
                else:
                    if self._pending_add_op == "":
                        self._run_prog(self._prog_assign(dest=ACC, src=OPERAND, clear_src=True))
                    else:
                        self._run_prog(self._prog_fold_add(self._pending_add_op, src=OPERAND, clear_src=True))
                self._pending_add_op = ch

        elif kind == EQUALS:
            # Syntax validation: empty expression or trailing operator
            if not self._has_typed_any_digit or self._last_was_op:
                self._emit_error("ERR:SYNTAX")
                return

            if self._pending_mul_op in ("*", "/"):
                if not self._fold_pending_mul():
                    return
                if self._pending_add_op == "":
                    self._run_prog(self._prog_assign(dest=ACC, src=TERM, clear_src=True, set_ready=True))
                else:
                    self._run_prog(self._prog_fold_add(self._pending_add_op, src=TERM, clear_src=True, set_ready=True))
            else:
                if self._pending_add_op == "":
                    self._run_prog(self._prog_assign(dest=ACC, src=OPERAND, clear_src=True, set_ready=True))
                else:
                    self._run_prog(self._prog_fold_add(self._pending_add_op, src=OPERAND, clear_src=True, set_ready=True))

            if self.cpu.memory[READY] == 1:
                self._emit(self.cpu.memory[ACC])
                self._reset_for_next_expression()

    def _emit(self, value: int) -> None:
        self._console_text = str(value)
        self._console.feed(self._console_text)

    def _reset_for_next_expression(self) -> None:
        for addr in (ACC, OPERAND, OP, READY, HAS_OPERAND, TERM):
            self.cpu.memory[addr] = 0
        self._pending_add_op = ""
        self._pending_mul_op = ""
        self._in_error = False
        self._has_typed_any_digit = False
        self._last_was_op = False

    # -- console surface --------------------------------------------------------
    def console_text(self) -> str:
        return self._console_text

    def console_band(self):
        return self._console.render_band()

    def console_decode(self, band) -> str:
        return self._console.decode_band(band)
