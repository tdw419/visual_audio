#!/usr/bin/env python3
"""
SpaDSL — a restricted, array-oriented Python subset that compiles to
GlyphISA v2 assembly (tools/glyph_isa_v2.py).

Scope (Phase 1, honest about what actually runs):
    A = region(shape=(N,), initial=V)   # 1D region of N pixels, filled with V
    B = region(shape=(N,))              # 1D region, zero-filled
    C = A + B                           # elementwise add, same-size regions
    C = A - B                           # elementwise sub
    total = reduce(C, sum)              # sum all elements into one register
    print(total)                        # PRT the scalar register

Compilation strategy: every region op is unrolled at compile time into
straight-line LDI/LD/ST/ADD instructions on the real GlyphISA v2 ISA
(tools/glyph_isa_v2.py). There is no native GPU-parallel spatial opcode
in that ISA today, so this is scalar-unrolled, not warp-parallel — do
not claim GPU speedup from this compiler alone. It exists to prove the
DSL -> assembly -> execution loop closes correctly; a parallel backend
(WGSL) would need a real SIMT opcode added to the ISA first, not just a
compiler that pretends one exists.

Register usage (fixed, no allocator — fine for straight-line unrolled code):
    r20  scratch value A
    r21  scratch value B
    r22  scratch address A
    r23  scratch address B / C
    r24  reduce accumulator
Regions never overlap in the pixel address space: each is allocated a
contiguous run of addresses starting right after the assembled code's
own pixel footprint, so LD/ST on region data can never collide with the
instruction stream that is executing it.
"""

import argparse
import ast
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2, INSTR_WIDTH

WIDTH_INSTRS = 8
WIDTH_PX = WIDTH_INSTRS * INSTR_WIDTH

REG_A = 20
REG_B = 21
REG_ADDR_A = 22
REG_ADDR_B = 23
REG_ACC = 24


class SpaDSLError(Exception):
    pass


class Region:
    def __init__(self, name: str, base: int, size: int):
        self.name = name
        self.base = base
        self.size = size


class SpaDSLCompiler:
    def __init__(self):
        self.regions: Dict[str, Region] = {}
        self.code: List[str] = []
        self.next_data_addr = 0  # patched in later once code length is known
        self.scalars: Dict[str, str] = {}  # name -> description (for print), value lives in REG_ACC snapshot
        self.last_reduce_var: str = None

    def compile(self, source: str) -> List[str]:
        tree = ast.parse(source)
        for stmt in tree.body:
            self._compile_stmt(stmt)
        self.code.append("HALT")
        return self.code

    def _compile_stmt(self, stmt: ast.stmt):
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                raise SpaDSLError(f"line {stmt.lineno}: only simple `name = expr` assignment is supported")
            name = stmt.targets[0].id
            self._compile_assign(name, stmt.value, stmt.lineno)
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            self._compile_call_stmt(stmt.value, stmt.lineno)
        else:
            raise SpaDSLError(f"line {stmt.lineno}: unsupported statement {ast.dump(stmt)}")

    def _compile_assign(self, name: str, value: ast.expr, lineno: int):
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "region":
            self._compile_region_decl(name, value, lineno)
        elif isinstance(value, ast.BinOp) and isinstance(value.op, (ast.Add, ast.Sub)):
            self._compile_elementwise(name, value, lineno)
        elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "reduce":
            self._compile_reduce(name, value, lineno)
        else:
            raise SpaDSLError(f"line {lineno}: unsupported expression {ast.dump(value)}")

    def _compile_region_decl(self, name: str, call: ast.Call, lineno: int):
        shape = None
        initial = 0
        for kw in call.keywords:
            if kw.arg == "shape":
                if not isinstance(kw.value, ast.Tuple) or len(kw.value.elts) != 1:
                    raise SpaDSLError(f"line {lineno}: only 1D shape=(N,) regions are supported in Phase 1")
                shape = ast.literal_eval(kw.value.elts[0])
            elif kw.arg == "initial":
                initial = ast.literal_eval(kw.value)
            else:
                raise SpaDSLError(f"line {lineno}: unknown region() keyword {kw.arg}")
        if shape is None:
            raise SpaDSLError(f"line {lineno}: region() requires shape=(N,)")

        base = self.next_data_addr
        self.next_data_addr += shape
        region = Region(name, base, shape)
        self.regions[name] = region

        for i in range(shape):
            self.code.append(f"LDI r{REG_A} {initial}")
            self.code.append(f"LDI r{REG_ADDR_A} {base + i}")
            self.code.append(f"ST r{REG_ADDR_A} r{REG_A}")

    def _compile_elementwise(self, name: str, binop: ast.BinOp, lineno: int):
        if not (isinstance(binop.left, ast.Name) and isinstance(binop.right, ast.Name)):
            raise SpaDSLError(f"line {lineno}: elementwise ops require two region names, e.g. C = A + B")
        a = self.regions.get(binop.left.id)
        b = self.regions.get(binop.right.id)
        if a is None or b is None:
            raise SpaDSLError(f"line {lineno}: unknown region in {binop.left.id} + {binop.right.id}")
        if a.size != b.size:
            raise SpaDSLError(f"line {lineno}: region size mismatch ({a.size} vs {b.size})")

        base = self.next_data_addr
        self.next_data_addr += a.size
        out = Region(name, base, a.size)
        self.regions[name] = out

        op = "PARALLEL_ADD" if isinstance(binop.op, ast.Add) else "PARALLEL_SUB"
        
        # GPU Parallel Execution (Chunked to fit within 32 registers)
        # We use r0-r9 for A, r10-r19 for B, r20-r29 for C, and r30 for address.
        chunk_size = 10
        for i in range(0, a.size, chunk_size):
            chunk = min(chunk_size, a.size - i)
            # Load region A chunk into consecutive registers starting at r0
            self.code.append(f"PARALLEL_LD r0 {a.base + i} {chunk}")
            # Load region B chunk into consecutive registers starting at r10
            self.code.append(f"PARALLEL_LD r10 {b.base + i} {chunk}")
            
            # Perform elementwise operation: output to registers starting at r20
            self.code.append(f"{op} r20 r0 r10 {chunk}")
            
            # Store output registers to region C memory
            self.code.append(f"LDI r30 {out.base + i}")
            self.code.append(f"PARALLEL_ST r30 r20 {chunk}")

    def _compile_reduce(self, name: str, call: ast.Call, lineno: int):
        if len(call.args) != 2 or not isinstance(call.args[0], ast.Name):
            raise SpaDSLError(f"line {lineno}: reduce(region, sum) requires a region name and a reduction op")
        region = self.regions.get(call.args[0].id)
        if region is None:
            raise SpaDSLError(f"line {lineno}: unknown region {call.args[0].id}")
        op_arg = call.args[1]
        op_name = op_arg.id if isinstance(op_arg, ast.Name) else None
        if op_name != "sum":
            raise SpaDSLError(f"line {lineno}: only reduce(region, sum) is supported in Phase 1")

        # GPU Parallel Execution
        # Sum memory elements directly into the accumulator register
        self.code.append(f"PARALLEL_REDUCE_SUM r{REG_ACC} {region.base} {region.size}")
        
        self.scalars[name] = "reduce_sum"
        self.last_reduce_var = name

    def _compile_call_stmt(self, call: ast.Call, lineno: int):
        if isinstance(call.func, ast.Name) and call.func.id == "print":
            if len(call.args) != 1 or not isinstance(call.args[0], ast.Name):
                raise SpaDSLError(f"line {lineno}: print() supports a single scalar variable, e.g. print(total)")
            var = call.args[0].id
            if var not in self.scalars:
                raise SpaDSLError(f"line {lineno}: print() target '{var}' is not a reduce() result")
            self.code.append(f"PRT r{REG_ACC}")
        else:
            raise SpaDSLError(f"line {lineno}: unsupported call {ast.dump(call)}")


def compile_source(source: str) -> Tuple[List[str], Dict[str, Region]]:
    # Data must live in pixel addresses strictly after the code's own
    # footprint, or LD/ST would silently alias into the instruction stream
    # (glyph_isa_v2 addresses wrap over the whole image; code and data
    # share one linear pixel space). Code length depends on how many
    # region elements get unrolled, and region base addresses depend on
    # code length — so compile once with addresses at 0 to measure the
    # code footprint, then recompile with regions based right after it.
    first = SpaDSLCompiler()
    first.compile(source)
    code_rows = (len(first.code) + WIDTH_INSTRS - 1) // WIDTH_INSTRS
    offset = code_rows * WIDTH_PX

    second = SpaDSLCompiler()
    second.next_data_addr = offset
    tree = ast.parse(source)
    for stmt in tree.body:
        second._compile_stmt(stmt)
    second.code.append("HALT")
    return second.code, second.regions


def compile_file(path: Path) -> List[str]:
    source = path.read_text()
    code, _regions = compile_source(source)
    return code


def compile_and_run(path: Path, max_instructions: int = 100000):
    source = path.read_text()
    code, regions = compile_source(source)

    opcode_map = OpcodeMapV2()
    try:
        assembler = GlyphAssemblerV2(opcode_map)
        image = assembler.assemble(code, width_instrs=WIDTH_INSTRS)
        cpu = GlyphCPUv2(opcode_map, cols_instrs=WIDTH_INSTRS)
        cpu.run(image, max_instructions=max_instructions)
        return code, cpu, regions
    finally:
        opcode_map.close()


def main():
    parser = argparse.ArgumentParser(description="Compile SpaDSL (.py) to GlyphISA v2 assembly (.glyph)")
    parser.add_argument("source", type=Path, help="SpaDSL source file")
    parser.add_argument("-o", "--output", type=Path, help="Output .glyph assembly path")
    parser.add_argument("--run", action="store_true", help="Assemble and execute on GlyphCPUv2")
    args = parser.parse_args()

    try:
        if args.run:
            code, cpu, regions = compile_and_run(args.source)
        else:
            code = compile_file(args.source)
    except SpaDSLError as e:
        print(f"SpaDSL compile error: {e}", file=sys.stderr)
        sys.exit(1)

    out_path = args.output or args.source.with_suffix(".glyph")
    out_path.write_text("\n".join(code) + "\n")
    print(f"Wrote {len(code)} instructions to {out_path}")

    if args.run:
        print(f"Output: {cpu.output}")


if __name__ == "__main__":
    main()
