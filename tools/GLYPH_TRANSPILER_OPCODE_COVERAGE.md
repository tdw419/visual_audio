# rv64i_to_glyph.py opcode coverage

Generated from `transpile_rv32i_to_glyph`'s own AST against every `OP_*` constant in `rv64i_decode.py` -- not hand-maintained. Regenerate with `python3 tools/rv64i_to_glyph_coverage.py > tools/GLYPH_TRANSPILER_OPCODE_COVERAGE.md` whenever the transpiler gains a new opcode case; this file will silently rot otherwise (it is not auto-checked).

**38/87 opcodes handled.**

## Handled

- `OP_ADD`
- `OP_ADDI`
- `OP_AND`
- `OP_ANDI`
- `OP_AUIPC`
- `OP_BEQ`
- `OP_BGE`
- `OP_BGEU`
- `OP_BLT`
- `OP_BLTU`
- `OP_BNE`
- `OP_ECALL`
- `OP_JAL`
- `OP_JALR`
- `OP_LBU`
- `OP_LD`
- `OP_LHU`
- `OP_LUI`
- `OP_LW`
- `OP_OR`
- `OP_ORI`
- `OP_SB`
- `OP_SD`
- `OP_SH`
- `OP_SLL`
- `OP_SLLI`
- `OP_SLT`
- `OP_SLTI`
- `OP_SLTIU`
- `OP_SLTU`
- `OP_SRA`
- `OP_SRAI`
- `OP_SRL`
- `OP_SRLI`
- `OP_SUB`
- `OP_SW`
- `OP_XOR`
- `OP_XORI`

## NOT handled (raises ValueError if encountered)

- `OP_ADDIW`
- `OP_ADDW`
- `OP_AMOADD`
- `OP_AMOAND`
- `OP_AMOMAX`
- `OP_AMOMAXU`
- `OP_AMOMIN`
- `OP_AMOMINU`
- `OP_AMOOR`
- `OP_AMOSWAP`
- `OP_AMOXOR`
- `OP_COUNT`
- `OP_CSRRC`
- `OP_CSRRCI`
- `OP_CSRRS`
- `OP_CSRRSI`
- `OP_CSRRW`
- `OP_CSRRWI`
- `OP_DIV`
- `OP_DIVU`
- `OP_DIVUW`
- `OP_DIVW`
- `OP_EBREAK`
- `OP_FENCE`
- `OP_LB`
- `OP_LH`
- `OP_LR`
- `OP_LWU`
- `OP_MRET`
- `OP_MUL`
- `OP_MULH`
- `OP_MULHSU`
- `OP_MULHU`
- `OP_MULW`
- `OP_REM`
- `OP_REMU`
- `OP_REMUW`
- `OP_REMW`
- `OP_SC`
- `OP_SFENCE_VMA`
- `OP_SLLIW`
- `OP_SLLW`
- `OP_SRAIW`
- `OP_SRAW`
- `OP_SRET`
- `OP_SRLIW`
- `OP_SRLW`
- `OP_SUBW`
- `OP_WFI`
