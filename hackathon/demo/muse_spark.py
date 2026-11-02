"""Muse Spark semantic layer v1 (h5).

English program description -> muse-spark-1.3 -> Glyph spatial asm ->
canvas placement, verified instruction-level and by execution against the
transpiler test corpus ground truth (offline; Meta API responses are
recorded fixtures — live probes are operator receipts).

The layer ENFORCES the glyph-asm machine conventions at the text boundary,
before anything reaches the assembler (grounded in tools/glyph_isa_v2.py):

  1. Operands are space-separated. GlyphAssemblerV2 parses with split();
     comma-glued operands ("LDI r10, 0") fail register parsing downstream.
  2. A label definition (":name") is the SOLE token on its line
     (GlyphAssemblerV2 pass 1). A label glued onto an instruction line
     becomes a phantom operand.
  3. JZ / JNZ are FLAG-based: CMP writes the equality flag to r0; JZ jumps
     when the flag is SET, JNZ when it is CLEAR (SE024 complement pair).
     They never compare operands directly.
  4. Fixed-arity opcodes read EXACTLY their declared operands; a 3rd
     arithmetic operand is the BK-315 accumulator class ("ADD r1 r1 5"
     bit three tickets by computing a wrong answer with no trace of why).

tools/ is imported lazily and treated as ground truth — this module never
modifies it.
"""
import json
import re

MODEL = "muse-spark-1.3"

# Fixed-arity table mirrored from GlyphAssemblerV2._FIXED_ARITY (BK-315).
# Variadic opcodes (SYSCALL's optional imm, PARALLEL_*'s optional count)
# are exempt by the same design ruling as the assembler.
FIXED_ARITY = {
    "LDI": 2, "ST": 2,
    "ADD": 2, "SUB": 2, "MUL": 2, "CMP": 2, "CMP3": 2, "LD": 2,
    "AND": 2, "OR": 2, "XOR": 2, "SHL": 2, "SHR": 2, "ROTR": 2,
    "JMPR": 1, "CALLR": 1, "KJMP": 1,
    "PRT": 1, "PUSH": 1, "POP": 1,
    "JMP": 1, "JZ": 1, "JNZ": 1, "JNE": 1, "JLT": 1, "JGT": 1, "CALL": 1,
    "HALT": 0, "RET": 0, "SYSRET": 0,
}
VARIADIC = {"SYSCALL", "PARALLEL_ADD", "PARALLEL_LD", "PARALLEL_REDUCE_SUM",
            "PARALLEL_ST", "PARALLEL_SUB"}
# Jump-family opcodes whose single operand may legally be a raw "col,row"
# coordinate pair (post-label-resolution form) — comma is NOT a violation
# there, only a label or a coordinate.
JUMP_OPS = {"JMP", "JZ", "JNZ", "JNE", "JLT", "JGT", "CALL"}

CONVENTIONS = (
    "Glyph spatial asm machine conventions (mandatory, enforced by linter "
    "and assembler):\n"
    "1. Operands are space-separated: 'ADD r1 r2'. Never comma-separated.\n"
    "2. A label definition (':name') is the sole token on its own line — "
    "put it with preceding whitespace on its own line, never glued onto an "
    "instruction line ('LDI r1 5 :loop' is invalid).\n"
    "3. JZ and JNZ are FLAG-based: CMP sets equality flag r0; JZ jumps when "
    "the flag is set, JNZ jumps when it is clear. They never compare "
    "operands directly.\n"
    "4. Arithmetic/data opcodes take EXACTLY 2 operands. A 3rd operand is "
    "SILENTLY DROPPED at the machine level ('ADD r1 r1 5' computes a wrong "
    "answer). Never emit a 3rd operand.\n"
    "Supported opcodes: " + ", ".join(sorted(FIXED_ARITY)) + "."
)

SYSTEM_PROMPT = (
    "You are Muse Spark, a compiler from plain-English program descriptions "
    "to Glyph spatial assembly (Glyph ISA v2, 4 px per instruction, labels "
    "resolve to (col,row) canvas coordinates at placement).\n"
    + CONVENTIONS
    + "\nReply with ONE fenced ```asm block containing the complete program. "
    "Leave the integer result in register r10 (a0) and end with HALT."
)


class MuseAsmError(ValueError):
    """A Muse response violates the glyph-asm contract."""


def build_prompt(description):
    """Messages for a chat request. Embeds every machine convention."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",
         "content": f"Program description: {description}\n"
                    f"Glyph asm:"},
    ]


def extract_asm(text):
    """Pull the asm payload out of a Muse response.

    Accepts a fenced ```asm ...``` block, any fenced block, or raw asm
    text. Raises MuseAsmError when nothing asm-shaped is present.
    """
    m = re.search(r"```(?:asm)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip() + "\n"
    stripped = text.strip()
    if stripped and _looks_like_asm(stripped):
        return stripped + "\n"
    raise MuseAsmError("no asm block or asm-shaped text in Muse response")


def _looks_like_asm(text):
    for line in text.splitlines():
        code = line.split("#")[0].split(";")[0].strip()
        tok = code.split()
        if tok and (tok[0] in FIXED_ARITY or tok[0] in VARIADIC
                    or tok[0].startswith(":")):
            return True
    return False


def _code_lines(asm):
    """Instruction-bearing lines: comments/blanks stripped, trailing
    comments removed ('#' and ';' are both live comment conventions)."""
    out = []
    for line in asm.splitlines():
        code = line.split("#")[0].split(";")[0].strip()
        if code:
            out.append(code)
    return out


def lint_asm(asm):
    """Check the four machine conventions. Returns [] when clean, raises
    MuseAsmError naming the violated convention otherwise."""
    for code in _code_lines(asm):
        tokens = code.split()
        opcode = tokens[0]
        args = tokens[1:]

        # (2) label DEFS are the sole token on their line (":name" first
        # and only). A ":name" in operand position is a normal jump/CALL
        # reference — only a label def sharing its line with an
        # instruction, or a label token as an EXTRA operand, is the
        # glued-label class.
        if opcode.startswith(":"):
            if len(tokens) > 1:
                raise MuseAsmError(
                    f"label def {code!r} shares its line with other "
                    f"tokens — a label def must be the sole token on its "
                    f"own line")
            continue

        if opcode in FIXED_ARITY:
            # (1) space-separated operands: commas only legal as the raw
            # 'col,row' jump-target coordinate form
            for arg in args:
                if "," in arg and not (opcode in JUMP_OPS
                                       and re.fullmatch(r"\d+,\d+", arg)):
                    raise MuseAsmError(
                        f"comma-separated operand {arg!r} in {code!r} — "
                        f"operands must be space-separated")
            # (4) fixed arity — the silently-dropped 3rd operand class
            expected = FIXED_ARITY[opcode]
            if len(args) != expected:
                extra = args[expected:] if len(args) > expected else []
                if extra and any(t.startswith(":") for t in extra):
                    raise MuseAsmError(
                        f"label {extra[0]} is glued onto the instruction "
                        f"{code!r} — a label def must be the sole token on "
                        f"its own line")
                if extra:
                    raise MuseAsmError(
                        f"{opcode} got a 3rd (extra) operand {extra} in "
                        f"{code!r} — extra operands are SILENTLY DROPPED at "
                        f"the machine level (BK-315 accumulator class); "
                        f"expected exactly {expected}")
                raise MuseAsmError(
                    f"{opcode} expects {expected} operand(s) but got "
                    f"{len(args)} in {code!r}")
        elif opcode not in VARIADIC:
            raise MuseAsmError(
                f"unknown opcode {opcode!r} in {code!r} — not in the "
                f"Glyph ISA v2 opcode set")
    return []


def normalize(asm):
    """Comparable instruction stream: code lines with comments stripped,
    label defs kept (they are part of instruction-level identity)."""
    return _code_lines(asm)


def instruction_level_match(candidate_asm, reference_asm):
    """True iff the normalized instruction streams are identical,
    label-for-label and instruction-for-instruction."""
    return normalize(candidate_asm) == normalize(reference_asm)


def place_on_canvas(asm, cols_instrs=64):
    """Canvas placement: glyph asm -> (pixel array, label coordinate map)
    via the ground-truth assembler in tools/."""
    from tools.rv64i_to_glyph import assemble_glyph_to_pixels
    return assemble_glyph_to_pixels(asm, cols_instrs=cols_instrs, min_rows=32)


def execute_canvas(placed, mem_words=16384, max_steps=300000):
    """Execute placed canvas on GlyphCPUv2 (the QEMU-diff-verified engine
    chain). Returns {halted, a0, steps}; a0 is r10 (RV a0 / return value)."""
    from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2
    pixels, _coords = placed
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=pixels.shape[1] // 4)
    cpu.memory = [0] * mem_words
    cpu.pc = (0, 0)
    cpu.running = True
    steps = 0
    for _ in range(max_steps):
        if not cpu.step(pixels):
            break
        steps += 1
    return {"halted": not cpu.running, "a0": cpu.registers[10], "steps": steps}


def generate_and_verify(client, description, reference_asm=None,
                        ground_truth=None):
    """Full v1 pipeline: prompt -> chat -> extract -> lint -> verify.

    match: instruction-level match against reference_asm (when given).
    execution: canvas placement + GlyphCPUv2 run vs ground_truth (when
    given). lint_clean: the convention linter passed.
    """
    response = client.chat(model=MODEL, messages=build_prompt(description))
    content = response["choices"][0]["message"]["content"]
    asm = extract_asm(content)
    lint_asm(asm)  # raises on any convention violation
    result = {"asm": asm, "lint_clean": True, "match": None,
              "execution": None}
    if reference_asm is not None:
        result["match"] = instruction_level_match(asm, reference_asm)
    if ground_truth is not None:
        result["execution"] = execute_canvas(place_on_canvas(asm))
        result["execution_ok"] = (
            result["execution"]["halted"]
            and result["execution"]["a0"] == ground_truth["glyph_result"])
    return result


def corpus_score(corpus, responses):
    """Corpus score for the receipt: for every case, execute the reference
    asm against recorded ground truth; for cases with a recorded response,
    also check instruction-level match of the response vs the reference."""
    exact = 0
    for case in corpus["cases"]:
        if case["name"] in responses:
            cand = extract_asm(
                responses[case["name"]]["choices"][0]["message"]["content"])
            lint_asm(cand)
            if instruction_level_match(cand, case["reference_asm"]):
                exact += 1
    executed = 0
    for case in corpus["cases"]:
        run = execute_canvas(place_on_canvas(case["reference_asm"]))
        if run["halted"] and run["a0"] == case["ground_truth"]["glyph_result"]:
            executed += 1
    return {"exact_match": exact, "executed": executed,
            "corpus_size": len(corpus["cases"])}
