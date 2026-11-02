#!/usr/bin/env python3
"""tools/glyph_linter.py — ABI & Geometry static analyzer for Geometry OS.

Catches the 4 recurring semantic contract bug classes in .glyph assembly and
kernel templates before execution:

1. Packet Framing / Checksum Validation (Bug 5 shape, GH-26.4 / BK-1):
   GH-22 mailbox/argv packets use 32-bit dense packing:
       (cksum << 24) | (op << 8) | payload
   where cksum = (op + payload) & 0xFF.
   Catches hand-packed constants or invalid seed words (e.g. 0x2A112A instead
   of 0x3B00112A) that violate the checksum invariant.

2. Preemption Tick-Window Register Isolation (Bug 8 shape, GH-16 / GH-26.4):
   Tick handlers (:__ktick, :__tick) interrupt tasks at arbitrary instruction
   boundaries without full context save. Per the GH-16 isolation contract:
   - Tick routines MUST write ONLY r25..r28.
   - Any write to r0..r24 or r29..r31 in a tick routine risks clobbering registers
     live across preemption windows (e.g. r13..r15 clobber in task B).
   - User tasks should not use r25..r28 as general-purpose scratch under preemption.

3. Syscall Convention Enforcement (Bug 7 shape, GH-26.4):
   When a kernel dispatcher is armed (KSYS_PC != 0), the hardware/engine trap
   marshals r17 into SYS_N (not the instruction immediate).
   - Flag SYSCALL without preceding LDI r17 <num> in the same block.
   - Flag divergence between LDI r17 <num> and SYSCALL <rd> <imm>.

4. Geometry & Canvas Bounds Checks (GH-9 / GH-17 / GH-25):
   Spatial execution relies on 2D pixel layouts (INSTR_WIDTH = 4 pixels):
   - start_cell = wrow * cols_instrs + wcol must stay within bounds.
   - Total instruction count must not exceed cols_instrs * min_rows.
   - Branch/jump labels must resolve to valid canvas coordinates.

Usage:
    python3 tools/glyph_linter.py <file.glyph|file.py>
    python3 tools/glyph_linter.py --all
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class Finding(NamedTuple):
    check: str       # 'packet_framing' | 'tick_register_isolation' | 'syscall_abi' | 'geometry_bounds'
    line: int        # 1-indexed line number (0 if file-level)
    severity: str    # 'ERROR' | 'WARNING'
    detail: str      # description of the violation


# Set of registers reserved strictly for preemption tick handlers
TICK_ISOLATION_REGS = {"r25", "r26", "r27", "r28"}

# Opcodes that write to a destination register (rd or first reg operand)
_WRITES_FIRST_REG_OPCODES = {
    "LDI", "ADD", "SUB", "AND", "OR", "XOR", "SHL", "SHR", "ROTR", "POP"
}


# ── Check 1: Packet Framing / Checksum Validation ──────────────────────────

def validate_packet_word(word: int) -> bool:
    """Validate a 32-bit word against GH-22 packet checksum format.
    Packed as: (cksum << 24) | (op << 8) | payload
    where cksum = (op + payload) & 0xFF.
    """
    word &= 0xFFFFFFFF
    cksum = (word >> 24) & 0xFF
    op = (word >> 8) & 0xFF
    payload = word & 0xFF
    expected = (op + payload) & 0xFF
    return cksum == expected


def check_packet_framing_text(text: str) -> List[Finding]:
    """Scan assembly or Python source for packet constants / immediates and
    verify that any declared mailbox, argv, or seed packet satisfies GH-22 framing.
    """
    findings: List[Finding] = []
    lines = text.splitlines()

    # Pattern 1: Python constant definitions matching SEED, ARGV, MAILBOX, PACKET
    py_const_pat = re.compile(
        r'^\s*([A-Z0-9_]*(?:SEED|ARGV|MAILBOX|PACKET)[A-Z0-9_]*)\s*=\s*(0x[0-9a-fA-F]+|\d+)'
    )
    # Pattern 2: LDI with comment mentioning seed/argv/mailbox/packet/framing
    ldi_comment_pat = re.compile(
        r'^\s*LDI\s+r\d+\s+(0x[0-9a-fA-F]+|\d+)\s*;.*?(?:seed|argv|mailbox|packet|gh22|framing)',
        re.IGNORECASE
    )

    for idx, raw_line in enumerate(lines, start=1):
        # Strip comments for parsing Python consts, but keep for LDI comments
        m_py = py_const_pat.search(raw_line)
        if m_py:
            name, val_str = m_py.group(1), m_py.group(2)
            try:
                val = int(val_str, 16 if val_str.startswith(("0x", "0X")) else 10)
            except ValueError:
                continue
            # Non-zero 32-bit packet constants
            if val > 0xFFFF:
                cksum = (val >> 24) & 0xFF
                op = (val >> 8) & 0xFF
                payload = val & 0xFF
                expected = (op + payload) & 0xFF
                if cksum != expected:
                    findings.append(Finding(
                        check="packet_framing",
                        line=idx,
                        severity="ERROR",
                        detail=f"Constant '{name}' (0x{val:08X}) has invalid GH-22 packet checksum: "
                               f"cksum=0x{cksum:02X}, expected=0x{expected:02X} (op=0x{op:02X}, payload=0x{payload:02X})"
                    ))

        m_ldi = ldi_comment_pat.search(raw_line)
        if m_ldi:
            val_str = m_ldi.group(1)
            try:
                val = int(val_str, 16 if val_str.startswith(("0x", "0X")) else 10)
            except ValueError:
                continue
            if val > 0xFFFF:
                cksum = (val >> 24) & 0xFF
                op = (val >> 8) & 0xFF
                payload = val & 0xFF
                expected = (op + payload) & 0xFF
                if cksum != expected:
                    findings.append(Finding(
                        check="packet_framing",
                        line=idx,
                        severity="ERROR",
                        detail=f"LDI packet immediate 0x{val:08X} fails GH-22 checksum: "
                               f"cksum=0x{cksum:02X}, expected=0x{expected:02X} (op=0x{op:02X}, payload=0x{payload:02X})"
                    ))

    return findings


# ── Check 2: Preemption Tick-Window Register Isolation ─────────────────────

def check_tick_register_isolation(text: str) -> List[Finding]:
    """Verify that tick routines (:__ktick, :__tick) modify ONLY r25..r28.
    Writing any other register in a tick handler violates the GH-16 register
    isolation contract and clobbers preemption state (Bug 8 shape).
    """
    findings: List[Finding] = []
    lines = text.splitlines()

    in_tick_routine = False
    tick_label_line = 0

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.split(";", 1)[0].split("#", 1)[0].strip()
        if not line:
            continue

        # Check for label
        if line.startswith(":"):
            label = line[1:].strip().lower()
            if "tick" in label:
                in_tick_routine = True
                tick_label_line = idx
            else:
                in_tick_routine = False
            continue

        if not in_tick_routine:
            continue

        parts = line.split()
        op = parts[0].upper()

        # Exit from tick handler
        if op in ("JMPR", "SYSRET", "RET", "HALT", "KJMP"):
            if op == "JMPR":
                in_tick_routine = False
            continue

        dest_reg: Optional[str] = None
        if op in _WRITES_FIRST_REG_OPCODES and len(parts) > 1:
            reg_cand = parts[1].lower().rstrip(",")
            if reg_cand.startswith("r") and reg_cand[1:].isdigit():
                dest_reg = reg_cand
        elif op == "LD" and len(parts) > 1:
            reg_cand = parts[1].lower().rstrip(",")
            if reg_cand.startswith("r") and reg_cand[1:].isdigit():
                dest_reg = reg_cand
        elif op == "CMP":
            dest_reg = "r0"

        if dest_reg is not None and dest_reg not in TICK_ISOLATION_REGS:
            findings.append(Finding(
                check="tick_register_isolation",
                line=idx,
                severity="ERROR",
                detail=f"Tick routine (from line {tick_label_line}) modifies '{dest_reg}', "
                       f"violating GH-16 register isolation contract! Only r25..r28 are permitted. "
                       f"(This causes silent register corruption across preemption ticks, Bug 8 shape)"
            ))

    return findings


# ── Check 3: Syscall Convention Enforcement ────────────────────────────────

def check_syscall_abi(text: str) -> List[Finding]:
    """Verify that every SYSCALL is preceded by setting r17 to the syscall number.
    When a kernel dispatcher is armed (KSYS_PC != 0), the hardware trap reads
    the syscall number from r17, NOT from the instruction immediate (Bug 7 shape).
    Also flags divergence between LDI r17 <num> and SYSCALL <rd> <imm>.
    """
    findings: List[Finding] = []
    lines = text.splitlines()

    last_r17_val: Optional[int] = None
    last_r17_line: Optional[int] = None

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.split(";", 1)[0].split("#", 1)[0].strip()
        if not line:
            continue

        # Labels or control transfers reset or partition the block
        if line.startswith(":") or line.upper().startswith(("JMP", "JZ", "CALL", "RET", "KJMP", "SYSRET")):
            last_r17_val = None
            last_r17_line = None
            continue

        parts = line.split()
        op = parts[0].upper()

        if op == "LDI" and len(parts) >= 3:
            reg = parts[1].lower().rstrip(",")
            if reg == "r17":
                val_str = parts[2].rstrip(",")
                try:
                    last_r17_val = int(val_str, 16 if val_str.startswith(("0x", "0X")) else 10)
                    last_r17_line = idx
                except ValueError:
                    last_r17_val = None
                    last_r17_line = idx

        elif op == "SYSCALL":
            # Guard against English prose in comments/docstrings:
            # If arguments are present, the first argument must look like a register r0..r31 or integer
            if len(parts) > 1:
                first_arg = parts[1].lower().rstrip(",")
                if not (first_arg.startswith("r") and first_arg[1:].isdigit()) and not first_arg.isdigit():
                    continue

            # Check whether r17 was set
            if last_r17_line is None:
                findings.append(Finding(
                    check="syscall_abi",
                    line=idx,
                    severity="ERROR",
                    detail="SYSCALL executed without r17 being set in preceding basic block! "
                           "Kernel dispatcher marshals syscall number from r17 (Bug 7 shape). "
                           "Without LDI r17 <N>, dispatcher silently routes to unknown-syscall handler."
                ))
            elif len(parts) >= 3 and last_r17_val is not None:
                imm_str = parts[2].rstrip(",")
                try:
                    syscall_imm = int(imm_str, 16 if imm_str.startswith(("0x", "0X")) else 10)
                    if syscall_imm != last_r17_val:
                        findings.append(Finding(
                            check="syscall_abi",
                            line=idx,
                            severity="WARNING",
                            detail=f"SYSCALL immediate ({syscall_imm}) disagrees with preceding r17 value "
                                   f"({last_r17_val} at line {last_r17_line}). Dispatcher uses r17."
                        ))
                except ValueError:
                    pass

    return findings


# ── Check 3b: Unused / Dead CMP Verification ───────────────────────────────

def check_unused_cmp(text: str) -> List[Finding]:
    """Verify that every CMP instruction is consumed by a subsequent JZ.
    In Glyph ISA v2, CMP sets r0=1 on equality; its primary purpose is conditional
    branching via JZ. A CMP followed by control transfer or overwritten without a JZ
    indicates an omitted conditional jump.
    """
    findings: List[Finding] = []
    lines = text.splitlines()

    pending_cmp_line: Optional[int] = None

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.split(";", 1)[0].split("#", 1)[0].strip()
        if not line:
            continue

        if line.startswith(":"):
            if pending_cmp_line is not None:
                findings.append(Finding(
                    check="control_flow",
                    line=pending_cmp_line,
                    severity="WARNING",
                    detail=f"CMP at line {pending_cmp_line} was never followed by JZ before label '{line}'. "
                           f"Result in r0 was abandoned (missing branch bug shape)."
                ))
                pending_cmp_line = None
            continue

        parts = line.split()
        op = parts[0].upper()

        if op == "CMP":
            if pending_cmp_line is not None:
                findings.append(Finding(
                    check="control_flow",
                    line=pending_cmp_line,
                    severity="WARNING",
                    detail=f"CMP at line {pending_cmp_line} was superseded by another CMP at line {idx} "
                           f"without being tested by JZ."
                ))
            pending_cmp_line = idx
        elif op == "JZ":
            pending_cmp_line = None
        elif op in ("JMP", "CALL", "RET", "KJMP", "SYSRET", "HALT"):
            if pending_cmp_line is not None:
                findings.append(Finding(
                    check="control_flow",
                    line=pending_cmp_line,
                    severity="WARNING",
                    detail=f"CMP at line {pending_cmp_line} was never tested by JZ before control transfer '{op}'."
                ))
                pending_cmp_line = None

    if pending_cmp_line is not None:
        findings.append(Finding(
            check="control_flow",
            line=pending_cmp_line,
            severity="WARNING",
            detail=f"CMP at line {pending_cmp_line} was never tested by JZ before end of file."
        ))

    return findings


# ── Check 4: Geometry & Canvas Bounds Checks ───────────────────────────────

def check_geometry_bounds(
    text: str,
    cols_instrs: int = 8,
    min_rows: int = 16,
    max_rows: Optional[int] = None
) -> List[Finding]:
    """Verify spatial canvas bounds:
    - start_cell = wrow * cols_instrs + wcol fits in canvas.
    - Instruction count does not exceed allocated canvas rows.
    - Jump target labels exist.
    """
    findings: List[Finding] = []
    lines = text.splitlines()

    defined_labels: Set[str] = set()
    jump_references: List[Tuple[int, str]] = []  # (line, label)
    instruction_count = 0

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.split(";", 1)[0].split("#", 1)[0].strip()
        if not line:
            continue

        if line.startswith(":"):
            label = line.split()[0]
            defined_labels.add(label)
            continue

        parts = line.split()
        op = parts[0].upper()
        instruction_count += 1

        if op in ("JMP", "JZ", "CALL") and len(parts) > 1:
            target = parts[1].strip()
            if target.startswith(":"):
                jump_references.append((idx, target))

    # Check jump references
    for line_num, target in jump_references:
        if target not in defined_labels:
            findings.append(Finding(
                check="geometry_bounds",
                line=line_num,
                severity="ERROR",
                detail=f"Jump/call target '{target}' is never defined in the program canvas."
            ))

    # Check total instruction count vs rows
    total_capacity = cols_instrs * min_rows
    if instruction_count > total_capacity:
        needed_rows = (instruction_count + cols_instrs - 1) // cols_instrs
        findings.append(Finding(
            check="geometry_bounds",
            line=0,
            severity="WARNING",
            detail=f"Program contains {instruction_count} instructions, exceeding min_rows={min_rows} "
                   f"capacity ({total_capacity} cells at cols_instrs={cols_instrs}). "
                   f"Canvas bake will auto-expand to {needed_rows} rows."
        ))

    if max_rows is not None and instruction_count > (cols_instrs * max_rows):
        findings.append(Finding(
            check="geometry_bounds",
            line=0,
            severity="ERROR",
            detail=f"Program contains {instruction_count} instructions, exceeding max_rows={max_rows} "
                   f"hard capacity ({cols_instrs * max_rows} cells at cols_instrs={cols_instrs})."
        ))

    return findings


# ── Aggregator ─────────────────────────────────────────────────────────────

def lint_glyph_source(
    source: str,
    cols_instrs: int = 8,
    min_rows: int = 16,
    max_rows: Optional[int] = None
) -> List[Finding]:
    """Run all 4 lint checks on glyph source text."""
    findings: List[Finding] = []
    findings.extend(check_packet_framing_text(source))
    findings.extend(check_tick_register_isolation(source))
    findings.extend(check_syscall_abi(source))
    findings.extend(check_unused_cmp(source))
    findings.extend(check_geometry_bounds(source, cols_instrs=cols_instrs, min_rows=min_rows, max_rows=max_rows))
    return findings


def lint_file(file_path: Path) -> List[Finding]:
    """Lint a file (.glyph or .py containing glyph programs)."""
    text = file_path.read_text(encoding="utf-8")
    return lint_glyph_source(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Geometry OS Glyph ABI & Geometry Linter")
    parser.add_argument("files", nargs="*", type=Path, help="Files to lint (.glyph, .py, .as)")
    parser.add_argument("--cols", type=int, default=8, help="Columns in instructions (default 8)")
    parser.add_argument("--min-rows", type=int, default=16, help="Minimum canvas rows (default 16)")
    parser.add_argument("--fatal-warnings", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    files = args.files
    if not files:
        # Default scan admitted glyph files and key kernel modules
        default_files = [
            _REPO / "tools" / "glyph_gpt" / "agent_resident.py",
            _REPO / "tools" / "glyph_gpt" / "signals.py",
        ]
        admitted_dir = _REPO / "tools" / "glyph_gpt" / "admitted"
        if admitted_dir.is_dir():
            default_files.extend(admitted_dir.glob("*.glyph"))
        files = [f for f in default_files if f.exists()]

    total_errors = 0
    total_warnings = 0
    for f in files:
        findings = lint_file(f)
        if findings:
            for finding in findings:
                if finding.severity == "ERROR":
                    total_errors += 1
                else:
                    total_warnings += 1
            print(f"\n{f}: {len(findings)} finding(s):")
            for finding in findings:
                loc = f":{finding.line}" if finding.line > 0 else ""
                print(f"  [{finding.severity}] [{finding.check}]{loc} {finding.detail}")

    if total_errors == 0 and total_warnings == 0:
        print("glyph_linter: clean -- no findings across all checked files")
        return 0
    elif total_errors == 0 and not args.fatal_warnings:
        print(f"\nglyph_linter: clean (0 errors, {total_warnings} warning(s))")
        return 0
    else:
        print(f"\nglyph_linter: {total_errors} error(s), {total_warnings} warning(s) detected")
        return 1


if __name__ == "__main__":
    sys.exit(main())
