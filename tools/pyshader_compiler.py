"""tools/pyshader_compiler.py — Python shader subset -> GlyphIR -> Glyph ISA (PS001).

Compiles a restricted, array/scalar-oriented Python subset ("pyshader") into
the unified GlyphIR (GH-15, tools/glyph_ir.py) and then lowers that IR to
Glyph ISA v2 assembly text for GlyphAssemblerV2 / GlyphCPUv2 execution.

This is the first lane that *builds* GlyphIRModule structs directly
(raise_lines_to_ir parses text; we go semantic-first), and the first
front-end to share the GH-15 terminator table from the IR side.

Pipeline:
    python source -> ast -> blocks of IRInstruction -> StaticVerifier
        -> glyph asm text -> GlyphAssemblerV2 pixels -> GlyphCPUv2

Supported subset (PS001):
    def name(a, b):            # scalar u32 params (registers r1..rN)
        x = a + b              # + - * & | ^ << >> on scalars
        if a == b: ... else: ...   # real control flow (blocks + JZ/JNZ/JMP)
        while a != b: ...      # loops via the same terminator machinery
        mem[i] = x             # store to the data region (word RAM)
        x = mem[i]             # load
        return x               # result -> r9, then HALT

Verification boundary (honest):
    - u32 wrap semantics only (matches GlyphCPUv2 ADD/SUB/MUL &0xFFFFFFFF).
    - no floats, no calls, no recursion, no nested functions.
    - `if`/`while` conditions must be a single == or != comparison.
    - region memory = the CPU's 1024-word RAM (self.memory), NOT the pixel
      image; the region is placed at words 960..1023, clear of code/stack.

Differential gate (tests/test_pyshader_compiler.py):
    pure-Python IRInterpreter (this module) is the ORACLE; GlyphCPUv2 on
    the assembled pixels is the DEVICE. Same program, same inputs; r9 and
    the region window are compared at HALT.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from tools.glyph_ir import (
    Address,
    BasicBlock,
    IRInstruction,
    GlyphIRModule,
    CodeWindow,
    DataSection,
    IRContract,
    LoweringConfig,
    Operand,
    StaticVerificationError,
    StaticVerifier,
)

# ── register conventions ────────────────────────────────────────────────
# r0       : CMP flag (written by CMP only)
# r1..r8   : parameters (max 8)
# r9       : return value (contract: caller reads r9 at HALT)
# r10..r24 : compiler temporaries
# r26..r30 : LoweringConfig scratch pool (untouched)
# r31      : callstack reg (untouched: PS001 has no calls)

MAX_PARAMS = 8
REG_RESULT = "r9"
FIRST_PARAM = 1
FIRST_TEMP = 10
LAST_TEMP = 24
REG_REGION_BASE = "r25"  # fixed: holds REGION_BASE_WORD for mem[] access

U32_MASK = 0xFFFFFFFF

# Region placement: data lives below the GH-15 reserved RAM bands
# (GH-9 argv 750-760, mailbox 800-896, status 950-968, pixel-FS
# 1024-1280 is beyond the 1024-word RAM) and clear of code/stack in
# PS001-scale programs.
REGION_WORDS = 64
REGION_BASE_WORD = 680  # 680..743 — clear of all RESERVED_RANGES

# Conditional lowering: the jump target is the ELSE/EXIT block and the
# fall-through is THEN/BODY. So for `a == b` we jump when NOT equal
# (JNZ, taken when flag r0 is clear); for `a != b` we jump when equal
# (JZ, taken when flag r0 is set).
CMP_TERMS = {
    ast.Eq: "JNZ",     # equal -> flag set -> JNZ not taken -> then-block
    ast.NotEq: "JZ",   # not equal -> flag clear -> JZ not taken -> then-block
}

ARITH_OPS = {
    ast.Add: "ADD", ast.Sub: "SUB", ast.Mult: "MUL",
    ast.BitAnd: "AND", ast.BitOr: "OR", ast.BitXor: "XOR",
    ast.LShift: "SHL", ast.RShift: "SHR",
}


class PyShaderError(StaticVerificationError):
    """Loud front-end rejection with line numbers."""


class _FnLowering:
    """One function body -> GlyphIR blocks. Straight-line code accumulates
    in the current block; if/while close blocks with terminators.

    Variables get FIXED registers pre-assigned before lowering (both
    branches of an if write the same physical register, so the merge
    needs no phi). Expressions use fresh temporaries that die within one
    straight-line region.
    """

    def __init__(self, name: str, var_regs: Dict[str, str],
                 first_temp: int):
        self.name = name
        self.blocks: List[BasicBlock] = []
        self.current = BasicBlock(label=f"{name}__entry")
        self.blocks.append(self.current)
        self.temp_counter = first_temp
        self.first_temp = first_temp
        self.var_regs = dict(var_regs)

    # ── block helpers ───────────────────────────────────────────────
    def _emit(self, op: str, dests: Tuple[Operand, ...] = (),
              sources: Tuple[Operand, ...] = ()) -> None:
        self.current.append(IRInstruction(op=op, dests=dests,
                                          sources=sources))

    def _new_temp(self) -> str:
        r = self.temp_counter
        self.temp_counter += 1
        if r == 9:  # r9 = REG_RESULT, never a temp
            r = self.temp_counter
            self.temp_counter += 1
        if r > LAST_TEMP:
            raise PyShaderError(
                f"{self.name}: temporaries r{FIRST_TEMP}..r{LAST_TEMP} "
                "exhausted; simplify the expression")
        return f"r{r}"

    def _copy(self, dst: str, src: str) -> None:
        """dst = src via the zero+ADD idiom (no MOV in the palette)."""
        self._emit("SUB", dests=(Operand.reg(dst),),
                   sources=(Operand.reg(dst), Operand.reg(dst)))
        self._emit("ADD", dests=(Operand.reg(dst),),
                   sources=(Operand.reg(src),))

    def _bind(self, var: str, reg: str) -> None:
        self.var_regs[var] = reg

    def _reg_of(self, var: str) -> str:
        if var not in self.var_regs:
            raise PyShaderError(
                f"{self.name}: read of unassigned variable '{var}'")
        return self.var_regs[var]

    def _close(self, terminator: str, target: Optional[str]) -> None:
        """Terminate the current block; HALT ends emission (no successor),
        everything else opens a fresh fall-through block."""
        assert self.current.terminator is None, \
            f"block {self.current.label} already terminated"
        self.current.terminator = terminator
        self.current.terminator_target = target
        if terminator == "HALT":
            self.current = None
            return
        nxt = BasicBlock(label=f"{self.name}__blk{len(self.blocks):03d}")
        self.blocks.append(nxt)
        self.current = nxt

    # ── expressions (value -> register name) ────────────────────────
    def lower_expr(self, node: ast.expr, ln: int) -> str:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value,
                                                              int):
                raise PyShaderError(
                    f"line {ln}: only int constants supported, got "
                    f"{node.value!r}")
            tmp = self._new_temp()
            self._emit("LDI", dests=(Operand.reg(tmp),),
                       sources=(Operand.const(node.value & U32_MASK),))
            return tmp
        if isinstance(node, ast.Name):
            return self._reg_of(node.id)
        if isinstance(node, ast.BinOp):
            op = ARITH_OPS.get(type(node.op))
            if op is None:
                raise PyShaderError(
                    f"line {ln}: unsupported operator "
                    f"{type(node.op).__name__}")
            lhs = self.lower_expr(node.left, ln)
            rhs = self.lower_expr(node.right, ln)
            dst = self._new_temp()
            # Glyph ops are 2-operand (rd = rd OP rs). dst = lhs OP rhs
            # lowers to: zero dst, copy lhs in, apply op with rhs.
            self._emit("SUB", dests=(Operand.reg(dst),),
                       sources=(Operand.reg(dst), Operand.reg(dst)))
            self._emit("ADD", dests=(Operand.reg(dst),),
                       sources=(Operand.reg(lhs),))
            self._emit(op, dests=(Operand.reg(dst),),
                       sources=(Operand.reg(rhs),))
            return dst
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            v = self.lower_expr(node.operand, ln)
            dst = self._new_temp()
            # two's complement: SUB from zero
            zero = self._new_temp()
            self._emit("LDI", dests=(Operand.reg(zero),),
                       sources=(Operand.const(0),))
            self._emit("SUB", dests=(Operand.reg(dst),),
                       sources=(Operand.reg(zero), Operand.reg(v)))
            return dst
        if isinstance(node, ast.Subscript):
            if not isinstance(node.value, ast.Name):
                raise PyShaderError(
                    f"line {ln}: subscript must be name[index]")
            idx = self.lower_expr(node.slice, ln)
            addr = self._mem_addr(idx, ln)
            dst = self._new_temp()
            self._emit("LD", dests=(Operand.reg(dst),),
                       sources=(Operand.reg(addr),))
            return dst
        raise PyShaderError(
            f"line {ln}: unsupported expression {type(node).__name__}")

    def lower_cond(self, test: ast.expr, ln: int) -> str:
        """Lower an ==/!= comparison to CMP; return the JZ/JNZ op."""
        if not isinstance(test, ast.Compare):
            raise PyShaderError(
                f"line {ln}: condition must be a single ==/!= comparison")
        if len(test.ops) != 1:
            raise PyShaderError(f"line {ln}: chained comparisons unsupported")
        term = CMP_TERMS.get(type(test.ops[0]))
        if term is None:
            raise PyShaderError(
                f"line {ln}: only == and != are supported in conditions")
        lhs = self.lower_expr(test.left, ln)
        rhs = self.lower_expr(test.comparators[0], ln)
        # glyph CMP: CMP rd rs2 sets r0 = (rd == rs2). CMP does not write
        # its register operands, so passing lhs, rhs directly is safe.
        self._emit("CMP", dests=(Operand.reg("r0"),),
                   sources=(Operand.reg(lhs), Operand.reg(rhs)))
        return term

    def _mem_addr(self, idx_reg: str, ln: int) -> str:
        """Fold the region base into an index: returns addr temp holding
        REGION_BASE_WORD + idx (address bounds live in data_bounds)."""
        dst = self._new_temp()
        self._emit("SUB", dests=(Operand.reg(dst),),
                   sources=(Operand.reg(dst), Operand.reg(dst)))
        self._emit("ADD", dests=(Operand.reg(dst),),
                   sources=(Operand.reg(REG_REGION_BASE),))
        self._emit("ADD", dests=(Operand.reg(dst),),
                   sources=(Operand.reg(idx_reg),))
        return dst

    # ── statements ──────────────────────────────────────────────────
    def lower_body(self, stmts: List[ast.stmt]) -> None:
        for s in stmts:
            # statement-scoped temp reuse: temps never live past the
            # statement that allocates them (Assign copies the result
            # into the var's fixed register; Return copies into r9;
            # conditions branch within the statement). Resetting the
            # counter here reuses the same 15 temp registers for every
            # statement instead of exhausting after ~15 subexpressions
            # function-wide. PS005 (RV32I decode) needs this: imm
            # assembly is temp-heavy and cannot be expressed within a
            # function-wide budget of 15.
            self.temp_counter = self.first_temp
            self.lower_stmt(s)

    def lower_stmt(self, s: ast.stmt) -> None:
        ln = getattr(s, "lineno", 0)
        if isinstance(s, ast.Assign):
            if len(s.targets) != 1:
                raise PyShaderError(f"line {ln}: single-target assigns only")
            tgt = s.targets[0]
            if isinstance(tgt, ast.Subscript):
                # mem[i] = expr  ->  ST addr_reg, value_reg
                if not isinstance(tgt.value, ast.Name):
                    raise PyShaderError(
                        f"line {ln}: subscript must be name[index]")
                val = self.lower_expr(s.value, ln)
                idx = self.lower_expr(tgt.slice, ln)
                addr = self._mem_addr(idx, ln)
                self._emit("ST", sources=(Operand.reg(addr),
                                          Operand.reg(val)))
                return
            if not isinstance(tgt, ast.Name):
                raise PyShaderError(
                    f"line {ln}: target must be a name or mem[i]")
            reg = self.lower_expr(s.value, ln)
            # copy into the var's FIXED register (pre-assigned at plan
            # time) so both branches of an if converge without phis and
            # loop-carried values survive across iterations.
            self._copy(self._reg_of(tgt.id), reg)
            return
        if isinstance(s, ast.AugAssign):
            if not isinstance(s.target, ast.Name):
                raise PyShaderError(f"line {ln}: +=/-= target must be a name")
            op = ARITH_OPS.get(type(s.op))
            if op is None:
                raise PyShaderError(
                    f"line {ln}: unsupported augmented operator")
            cur = self._reg_of(s.target.id)
            rhs = self.lower_expr(s.value, ln)
            # glyph 2-operand semantics make augmented assign direct:
            # x += e is ADD x, e; x -= e is SUB x, e; etc.
            self._emit(op, dests=(Operand.reg(cur),),
                       sources=(Operand.reg(rhs),))
            return
        if isinstance(s, ast.Return):
            if s.value is not None:
                reg = self.lower_expr(s.value, ln)
                # r9 is initialized to 0, so ADD r9, reg is a plain copy
                # (SUB r9 r9 + ADD was redundant and the copy-in was
                # self-referential — ADD with no zeroing needed).
                self._emit("ADD", dests=(Operand.reg(REG_RESULT),),
                           sources=(Operand.reg(reg),))
            self._close("HALT", None)
            return
        if isinstance(s, ast.If):
            term = self.lower_cond(s.test, ln)
            else_lbl = f"{self.name}__else{ln}"
            end_lbl = f"{self.name}__endif{ln}"
            self._close(term, else_lbl)      # fall-through = then-block
            self.lower_body(s.body)
            self._close("JMP", end_lbl)
            self.current.label = else_lbl    # jump target = else block
            self.lower_body(s.orelse)
            self._close("JMP", end_lbl)
            self.current.label = end_lbl
            return
        if isinstance(s, ast.While):
            cond_lbl = f"{self.name}__while{ln}"
            end_lbl = f"{self.name}__wend{ln}"
            self._close("JMP", cond_lbl)     # enter the condition test
            self.current.label = cond_lbl
            term = self.lower_cond(s.test, ln)
            self._close(term, end_lbl)       # fall-through = loop body
            self.lower_body(s.body)
            self._close("JMP", cond_lbl)
            self.current.label = end_lbl
            return
        if isinstance(s, ast.Pass):
            return
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant):
            return  # docstring / bare constant
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call):
            raise PyShaderError(
                f"line {ln}: calls are not supported in PS001")
        raise PyShaderError(
            f"line {ln}: unsupported statement {type(s).__name__}")

    def finish(self, region_init: Dict[int, int]) -> GlyphIRModule:
        if self.current is not None and self.current.terminator is None:
            self._close("HALT", None)
        words = [region_init.get(i, 0) & U32_MASK
                 for i in range(REGION_WORDS)]
        module = GlyphIRModule(
            name=self.name,
            blocks=self.blocks,
            data_sections=[DataSection(symbol=f"{self.name}_region",
                                       base_word=REGION_BASE_WORD,
                                       words=words)],
            code_window=CodeWindow(
                origin_symbol="emitted-image",
                max_words=max(sum(len(b.instructions)
                                  + (1 if b.terminator else 0)
                                  for b in self.blocks), 1),
                cols_instrs=8),
            contract=IRContract(
                preserves=[],
                data_bounds=(REGION_BASE_WORD,
                             REGION_BASE_WORD + REGION_WORDS)),
            lowering=LoweringConfig(),
        )
        StaticVerifier(module).verify()
        return module


def _collect_assigned_vars(fn: ast.FunctionDef) -> List[str]:
    """All names ever assigned in the body (params first, then in order
    of first assignment). Fixed pre-allocation kills the branch-merge
    phi problem: both arms of an if write the same physical register."""
    assigned: List[str] = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Assign):
                for t in child.targets:
                    if isinstance(t, ast.Name) and t.id not in assigned:
                        assigned.append(t.id)
            elif isinstance(child, ast.AugAssign):
                if (isinstance(child.target, ast.Name)
                        and child.target.id not in assigned):
                    assigned.append(child.target.id)
            walk(child)

    walk(fn)
    return assigned


def compile_function(source: str,
                     region_init: Optional[Dict[int, int]] = None
                     ) -> GlyphIRModule:
    """Compile one top-level `def fn(a, b): ...` into a verified
    GlyphIRModule. region_init seeds region words {index: value}."""
    tree = ast.parse(source)
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(tree.body) != 1 or len(fns) != 1:
        raise PyShaderError("source must contain exactly one top-level def")
    fn = fns[0]
    if fn.args.kwonlyargs or fn.args.posonlyargs or fn.args.vararg \
            or fn.args.kwarg or fn.args.defaults:
        raise PyShaderError("only plain positional params are supported")
    params = [a.arg for a in fn.args.args]
    if len(params) > MAX_PARAMS:
        raise PyShaderError(f"max {MAX_PARAMS} params, got {len(params)}")

    # register plan: params r1..rN, then one fixed reg per assigned var,
    # then temps start after the last var reg.
    # Layout constraint (PS005): var regs may occupy r2..r8 ONLY.
    # r9 = REG_RESULT; r10..r24 = the statement-scoped temp pool; r25 =
    # region base. Before the per-statement temp reset existed, vars
    # could legally spill into r10+ (no temps were reused anyway); now
    # temps and vars share the r10..r24 range, so a var at r10+ would
    # be silently clobbered by the very next statement's temps —
    # deterministic wrong answers on ALL engines (interpreter AND GPU
    # execute the same IR), caught 2026-09-17 decoding RV32I immediates
    # (expected 5, measured 25). The planner must therefore REJECT
    # programs with more than 7 assigned vars instead of miscompiling.
    MAX_VAR_REGS = 8 - FIRST_PARAM  # r2..r8
    var_regs: Dict[str, str] = {}
    nxt = FIRST_PARAM + len(params)
    n_vars = 0
    for v in _collect_assigned_vars(fn):
        if v in params:
            continue  # param reassigned in place: keeps its param reg
        if nxt > 8:
            raise PyShaderError(
                f"{fn.name}: {n_vars + 1} assigned locals exceed the "
                f"{MAX_VAR_REGS}-register var space r2..r8 (r9 is the "
                "result register, r10..r24 are statement-scoped temps); "
                "split the program or reduce live locals")
        n_vars += 1
        var_regs[v] = f"r{nxt}"
        nxt += 1
    if nxt > LAST_TEMP:
        raise PyShaderError(
            f"{fn.name}: {nxt - FIRST_TEMP} registers needed but only "
            f"r{FIRST_TEMP}..r{LAST_TEMP} exist for locals/temps")
    lw = _FnLowering(fn.name, var_regs, first_temp=nxt)
    for i, p in enumerate(params):
        lw._bind(p, f"r{FIRST_PARAM + i}")
    # materialize the region base pointer once, up front: mem[i] lowers
    # to LD/ST at (REGION_BASE_WORD + i) via this register.
    lw._emit("LDI", dests=(Operand.reg(REG_REGION_BASE),),
             sources=(Operand.const(REGION_BASE_WORD),))
    lw.lower_body(fn.body)
    return lw.finish(region_init or {})


# ── IR -> Glyph ISA v2 text ─────────────────────────────────────────────

def emit_glyph_asm(module: GlyphIRModule) -> List[str]:
    """Lower a verified module to glyph assembly text (label form; the
    assembler resolves :labels to 2D coordinates)."""
    lines: List[str] = []
    for b in module.blocks:
        lines.append(f":{b.label}")
        for ins in b.instructions:
            d = ins.dests[0].phys_reg if ins.dests else None
            s = [o.phys_reg for o in ins.sources]
            if ins.op == "LDI":
                lines.append(f"LDI {d} {ins.sources[0].imm}")
            elif ins.op in ("ADD", "SUB", "MUL", "AND", "OR", "XOR",
                            "SHL", "SHR"):
                lines.append(f"{ins.op} {d} {s[0]}")
            elif ins.op == "CMP":
                lines.append(f"CMP {s[0]} {s[1]}")
            elif ins.op == "LD":
                lines.append(f"LD {d} {s[0]}")
            elif ins.op == "ST":
                lines.append(f"ST {s[0]} {s[1]}")  # ST addr, val
            elif ins.op == "PRT":
                lines.append(f"PRT {s[0]}")
            else:
                raise StaticVerificationError(
                    f"emit: unsupported IR op '{ins.op}'")
        if b.terminator:
            if b.terminator == "HALT":
                lines.append("HALT")
            elif b.terminator in ("JMP", "JZ", "JNZ"):
                lines.append(f"{b.terminator} :{b.terminator_target}")
            else:
                raise StaticVerificationError(
                    f"emit: unsupported terminator '{b.terminator}'")
    return lines


# ── pure-Python IR interpreter (the differential ORACLE) ────────────────

class IRInterpreter:
    """Execute a GlyphIRModule directly with GlyphCPUv2-identical u32
    semantics: 32-bit wrap on ADD/SUB/MUL, shifts mod 32, CMP writes r0,
    JZ taken when r0 != 0, JNZ when r0 == 0, LD/ST on a flat word array.
    Runs until a HALT terminator; returns r9."""

    def __init__(self, module: GlyphIRModule):
        self.module = module
        self.block_of = {b.label: i for i, b in enumerate(module.blocks)}
        self.registers = [0] * 32
        self.memory = [0] * 1024
        for ds in module.data_sections:
            for i, w in enumerate(ds.words):
                if ds.base_word + i < len(self.memory):
                    self.memory[ds.base_word + i] = w & U32_MASK
        self.output: List[int] = []

    def run(self, args: List[int], max_steps: int = 100_000) -> int:
        for i, a in enumerate(args):
            self.registers[FIRST_PARAM + i] = a & U32_MASK
        bi = 0
        steps = 0
        while 0 <= bi < len(self.module.blocks):
            blk = self.module.blocks[bi]
            for ins in blk.instructions:
                steps += 1
                if steps > max_steps:
                    raise RuntimeError("IRInterpreter: step budget blown")
                self._exec(ins)
            if blk.terminator is None:
                bi += 1
                continue
            t = blk.terminator
            if t == "HALT":
                return self.registers[9]
            if t == "JMP":
                bi = self.block_of[blk.terminator_target]
            elif t == "JZ":
                bi = (self.block_of[blk.terminator_target]
                      if self.registers[0] != 0 else bi + 1)
            elif t == "JNZ":
                bi = (self.block_of[blk.terminator_target]
                      if self.registers[0] == 0 else bi + 1)
            else:
                raise RuntimeError(f"IRInterpreter: bad terminator {t}")
        return self.registers[9]

    def _exec(self, ins: IRInstruction) -> None:
        op = ins.op
        r = self.registers
        # Every opcode below carries at least one register source except
        # LDI (immediate) and ST/CMP (no dest — ST writes memory, CMP
        # writes the flag r0). Pyright can't see the opcode/shape coupling,
        # so ops that need rd assert it explicitly.
        rd = (int(ins.dests[0].phys_reg[1:])
              if ins.dests and ins.dests[0].phys_reg else None)
        rs = [int(o.phys_reg[1:]) for o in ins.sources if o.phys_reg]
        if op not in ("ST", "PRT") and rd is None:
            raise RuntimeError(f"IRInterpreter: {op} missing dest")

        if op == "LDI":
            r[rd] = ins.sources[0].imm & U32_MASK
        elif op in ("ADD", "SUB", "MUL", "AND", "OR", "XOR", "SHL", "SHR"):
            # glyph 2-operand semantics: rd = rd OP rs
            if op == "ADD":
                r[rd] = (r[rd] + r[rs[0]]) & U32_MASK
            elif op == "SUB":
                r[rd] = (r[rd] - r[rs[0]]) & U32_MASK
            elif op == "MUL":
                r[rd] = (r[rd] * r[rs[0]]) & U32_MASK
            elif op == "AND":
                r[rd] &= r[rs[0]]
            elif op == "OR":
                r[rd] |= r[rs[0]]
            elif op == "XOR":
                r[rd] ^= r[rs[0]]
            elif op == "SHL":
                r[rd] = (r[rd] << (r[rs[0]] & 31)) & U32_MASK
            elif op == "SHR":
                r[rd] = (r[rd] & U32_MASK) >> (r[rs[0]] & 31)
        elif op == "CMP":
            r[0] = 1 if r[rs[0]] == r[rs[1]] else 0
        elif op == "LD":
            r[rd] = self.memory[r[rs[0]]] & U32_MASK
        elif op == "ST":
            self.memory[r[rs[0]]] = r[rs[1]] & U32_MASK
        elif op == "PRT":
            self.output.append(r[rs[0]])
        else:
            raise RuntimeError(f"IRInterpreter: bad op {op}")


def _run_on_cpu(module: GlyphIRModule, args: List[int]):
    """Assemble + execute the emitted program on the real GlyphCPUv2.
    Returns (registers snapshot, region window, output)."""
    import sys
    from pathlib import Path
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    from tools.glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2

    asm = emit_glyph_asm(module)
    om = OpcodeMapV2()
    ga = GlyphAssemblerV2(om)
    img = ga.assemble(asm, width_instrs=8)
    cpu = GlyphCPUv2(om, cols_instrs=8)
    for i, a in enumerate(args):
        cpu.registers[FIRST_PARAM + i] = a & U32_MASK
    cpu.run(img, max_instructions=200_000)
    if cpu.faulted:
        raise RuntimeError(
            f"GlyphCPUv2 faulted: {cpu.fault_reason} at pc={cpu.fault_pc}")
    region = [cpu.memory[REGION_BASE_WORD + i] for i in range(REGION_WORDS)]
    regs = {i: int(v) for i, v in enumerate(cpu.registers)}
    return regs, region, list(cpu.output)


def run_differential(source: str, args: List[int],
                     region_init: Optional[Dict[int, int]] = None) -> Dict:
    """Compile once, run on both engines, compare, return a receipt dict."""
    module = compile_function(source, region_init)
    interp = IRInterpreter(module)
    expected = interp.run(args)
    regs, region, out = _run_on_cpu(module, args)
    region_ok = region == [w & U32_MASK for w in interp.memory[
        REGION_BASE_WORD:REGION_BASE_WORD + REGION_WORDS]]
    ok = (regs.get(9) == (expected & U32_MASK)) and region_ok
    return {
        "ok": ok,
        "oracle_r9": expected & U32_MASK,
        "cpu_r9": regs.get(9),
        "region_ok": region_ok,
        "cpu_registers": regs,
        "n_blocks": len(module.blocks),
        "n_instructions": sum(len(b.instructions) for b in module.blocks),
        "asm": emit_glyph_asm(module),
    }
