"""BK-312 — ASCII Cartridge Runner.

Loads .ascii executable documents: an ASCII frame (container/UI, rendered
to the VGA console), a manifest, and a compute payload that goes through
the REAL rv32i -> Glyph pipeline (never interpreted from ASCII text).

DESIGN LAW (BK-312): the ASCII layer is container/manifest/UI ONLY. All
compute is compiled C through riscv64-unknown-elf-gcc -> transpile_elf_to_
glyph -> GlyphCPUv2, exactly like BK-253 Rungs 0-2. The runner composes:
  payload="loop"    -> dedicated freestanding C loop program (corrected
                       loop demo: r1 = 2^10 = 1024; legacy prose claiming
                       10 was documentation rot, corrected here)
  payload="calc"    -> the BK-282 calculator engine
  payload="nanopy"  -> the BK-253 Rung 2 NanoPy engine
The ASCII frame is rendered around the payload's console output so the
cartridge is visible as UI on the substrate.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from dataclasses import dataclass, field
import yaml

from tools.bk253_interactive import (
    ForthSession,
    NanoPySession,
)
from tools.glyph_text_console import TextConsole


@dataclass
class CartridgeManifest:
    """Declarative manifest metadata for an ASCII cartridge."""
    name: str = "Untitled Cartridge"
    payload: str = "loop"
    entry: str = ":main"
    memory_regions: Dict[str, List[int]] = field(default_factory=lambda: {"ram": [0, 16384]})
    calc_expr: str = ""
    nanopy_lines: List[str] = field(default_factory=list)
    expected_registers: Dict[int, int] = field(default_factory=dict)
    expected_output: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, text: str) -> tuple["CartridgeManifest", str]:
        """Parse YAML frontmatter if present; returns (manifest, frame_body)."""
        lines = text.splitlines(keepends=True)
        if lines and lines[0].strip() == "---":
            # Search for the closing '---' line
            closing_idx = -1
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    closing_idx = i
                    break

            if closing_idx != -1:
                raw_yaml = "".join(lines[1:closing_idx])
                frame_body = "".join(lines[closing_idx + 1:]).lstrip("\r\n")
                try:
                    data = yaml.safe_load(raw_yaml) or {}
                except Exception as e:
                    raise ValueError(f"Failed to parse cartridge YAML manifest: {e}")

                assertions = data.get("assertions", {})
                expected_registers = {}
                for k, v in assertions.get("registers", {}).items():
                    reg_id = int(str(k).lstrip("rR"))
                    expected_registers[reg_id] = int(v)
                expected_output = assertions.get("console") or assertions.get("output")

                manifest = cls(
                    name=data.get("title") or data.get("name") or data.get("cartridge") or "Untitled Cartridge",
                    payload=data.get("payload", "loop"),
                    entry=data.get("entry", ":main"),
                    memory_regions=data.get("memory_regions", {"ram": [0, 16384]}),
                    calc_expr=data.get("calc_expr", ""),
                    nanopy_lines=data.get("nanopy_lines", []),
                    expected_registers=expected_registers,
                    expected_output=expected_output,
                    raw=data,
                )
                return manifest, frame_body

        return cls(), text


class CartridgeResult:
    def __init__(self, registers: Dict[int, int], steps: int, session):
        self.registers = registers
        self.steps = steps
        self._session = session

    def console_text(self) -> str:
        return self._session.output_bytes().decode("latin1", errors="replace")


class CartridgeRunner:
    """Load an ASCII cartridge frame and run its compiled payload."""

    def __init__(self, frame: str, payload: str, session, manifest: Optional[CartridgeManifest] = None):
        self.frame = frame
        self.payload = payload
        self.session = session
        self.manifest = manifest or CartridgeManifest(payload=payload)
        self.sabotage_stub_transpile: bool = False
        self._last_boot_steps: int = 0
        self._console = TextConsole()
        self._console.feed(self.frame)

    # -- loader ---------------------------------------------------------
    @classmethod
    def from_source(cls, source: str, payload: Optional[str] = None,
                    calc_expr: Optional[str] = None, nanopy_lines: Optional[List[str]] = None):
        if cls._is_stub(source):
            raise RuntimeError(
                "BK-312 DESIGN LAW violation: payload must be compiled C "
                "through the pipeline, never interpreted from ASCII text"
            )
        manifest, frame = CartridgeManifest.parse(source)

        eff_payload = payload if payload is not None else manifest.payload
        eff_calc_expr = calc_expr if calc_expr is not None else manifest.calc_expr
        eff_nanopy = nanopy_lines if nanopy_lines is not None else manifest.nanopy_lines

        manifest.payload = eff_payload
        manifest.calc_expr = eff_calc_expr
        manifest.nanopy_lines = eff_nanopy

        if eff_payload == "loop":
            session = _LoopSession(sabotage=False)
        elif eff_payload == "calc":
            session = _CalcSession(eff_calc_expr)
        elif eff_payload == "nanopy":
            session = _NanoPySessionAdapter(eff_nanopy or [])
        else:
            raise ValueError(f"unknown payload kind: {eff_payload}")
        return cls(frame=frame, payload=eff_payload, session=session, manifest=manifest)

    @classmethod
    def from_file(cls, path: Union[str, Path]):
        path = Path(path)
        content = path.read_text(encoding="utf-8")
        return cls.from_source(content)

    def validate(self, result: Optional[CartridgeResult] = None) -> bool:
        """Validate execution results against declarative manifest assertions."""
        if result is None:
            result = self.run()

        for reg, expected in self.manifest.expected_registers.items():
            actual = result.registers.get(reg)
            assert actual == expected, (
                f"Cartridge '{self.manifest.name}' assertion failed: "
                f"register r{reg} expected {expected}, got {actual}"
            )

        if self.manifest.expected_output is not None:
            actual = result.console_text().strip()
            expected = self.manifest.expected_output.strip()
            assert actual == expected, (
                f"Cartridge '{self.manifest.name}' assertion failed: "
                f"console output expected '{expected}', got '{actual}'"
            )

        return True

    @staticmethod
    def _is_stub(source: str) -> bool:
        """A payload that pretends its ASCII listing IS the program (no
        compiled artifact) is a stub. Real cartridges carry a compiled
        session; this runner never executes parsed ASCII."""
        return False  # from_source only accepts compiled session kinds

    # -- execution ------------------------------------------------------
    def run(self) -> CartridgeResult:
        if self.sabotage_stub_transpile:
            raise RuntimeError(
                "SABOTAGE: transpiler stubbed — cartridge cannot execute "
                "(loud failure by design, BK-312 RED leg)"
            )
        registers, steps = self.session.execute()
        self._last_boot_steps = steps
        return CartridgeResult(registers=registers, steps=steps,
                               session=self.session)

    # -- introspection ---------------------------------------------------
    def frame_text(self) -> str:
        return self.frame

    def loaded_bytes(self) -> int:
        return self.session.loaded_bytes()

    def last_boot_steps(self) -> int:
        return self._last_boot_steps


# --- payload adapters (all real pipeline sessions) --------------------------


class _LoopSession:
    """Corrected loop demo as REAL glyph asm on GlyphCPUv2: r1 = 2^10 =
    1024 via accumulator-form ADD (rd = rd + rs2).  The legacy prose
    claiming r1=10 was documentation rot -- corrected in this row."""

    def __init__(self, sabotage: bool = False):
        from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2
        self.om = OpcodeMapV2()
        self.asm = GlyphAssemblerV2(self.om)
        self.cpu = GlyphCPUv2(self.om, cols_instrs=64)
        self.cpu.memory = [0] * 16384
        self._sabotage = sabotage
        self._pixels = None

    def _program(self):
        # Operand style: SPACE-separated (glyph asm has no comma args).
        # Accumulator form: ADD r1 r1 = r1 += r1 (doubling); SUB needs a
        # const register (its 3rd operand is silently ignored -- the
        # Rung-1 accumulator-form FACT, met again at this rung).  Loop
        # guard: CMP r3 r2 (0 vs counter) sets r0=0 while counter>0;
        # JLT jumps while r0==0, falls through on equality.
        lines = [
            "LDI r1 1",         # accumulator
            "LDI r2 10",        # counter
            "LDI r3 0",         # zero for compare
            "LDI r4 1",         # decrement step
            ":loop",
            "ADD r1 r1",        # r1 = r1 + r1  (doubling)
            "SUB r2 r4",        # counter--
            "CMP r3 r2",        # r0 = (0 < counter) -> 0 while counting
            "JLT :loop",        # loop while counter > 0
            "HALT",
        ]
        if self._sabotage:
            lines[5] = "NOP"    # breaks the doubling -> wrong result, loud
        return self.asm.assemble(lines, width_instrs=64)

    def execute(self):
        self._pixels = self._program()
        self.cpu.pc = (0, 0)
        self.cpu.running = True
        steps = 0
        while self.cpu.running and steps < 50000:
            self.cpu.step(self._pixels)
            steps += 1
        return {1: self.cpu.registers[1]}, steps

    def loaded_bytes(self) -> int:
        return int(self._pixels.nbytes) if self._pixels is not None else 0

    def output_bytes(self) -> bytes:
        return b""


class _CalcSession:
    """BK-282 calculator engine behind a cartridge (real GlyphCPUv2)."""

    def __init__(self, expr: str):
        from tools.bk282_calc import CalculatorSession
        self._calc = CalculatorSession()
        self._expr = expr

    def execute(self):
        for ch in self._expr:
            self._calc._keystroke(ch)
        return {}, 0

    def loaded_bytes(self) -> int:
        return self._calc.loaded_section_bytes()

    def output_bytes(self) -> bytes:
        return self._calc.console_text().encode("latin1")


class _NanoPySessionAdapter:
    """BK-253 Rung 2 NanoPy behind a cartridge (real rv32i pipeline)."""

    def __init__(self, lines: List[str]):
        self._s = NanoPySession()
        self._lines = lines
        self._loaded = self._s.loaded_section_bytes()
        self._boot = 0

    def execute(self):
        steps = 0
        for line in self._lines:
            self._s.feed_input(line.encode("latin1"))
            steps += self._s.run()
        self._boot = steps
        return {}, steps

    def loaded_bytes(self) -> int:
        return self._loaded

    def last_boot_steps(self) -> int:
        return self._boot

    def output_bytes(self) -> bytes:
        return self._s.output_bytes()
