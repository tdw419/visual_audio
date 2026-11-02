"""BK-253: Interactive Ladder — Rung 0 Echo REPL & Infrastructure.

Implements Stage A of the interactive ladder:
- Freestanding C echo loop on the GO-3 MMIO input ring.
- RV32 compilation via riscv64-unknown-elf-gcc -> transpile -> GlyphCPUv2.
- Direct output capture and BK-19 VGA text console integration.
- Deterministic, byte-exact, with non-vacuity sabotage verification.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, Union

import numpy as np

from tools.glyph_isa_v2 import (
    GlyphCPUv2,
    INPUT_CURSOR_ADDR,
    INPUT_DATA_ADDR,
    INPUT_LEN_ADDR,
    OpcodeMapV2,
)
from tools.glyph_text_console import TextConsole
from tools.rv64i_to_glyph import (
    assemble_glyph_to_pixels,
    build_pointer_table,
    parse_elf_data_sections,
    transpile_elf_to_glyph,
)

OUTPUT_LEN_ADDR = 0x81C0
OUTPUT_DATA_ADDR = 0x81C4
INIT_FLAG_ADDR = 0x8164
SABOTAGE_FLAG_ADDR = 0x8168

RUNG0_ECHO_C = """
#define INPUT_LEN_ADDR    (*(volatile unsigned int *)0x8170)
#define INPUT_CURSOR_ADDR (*(volatile unsigned int *)0x8174)
#define INPUT_DATA_ADDR   ((volatile char *)0x8180)

#define OUTPUT_LEN_ADDR   (*(volatile unsigned int *)0x81C0)
#define OUTPUT_DATA_ADDR  ((volatile char *)0x81C4)
#define SABOTAGE_FLAG     (*(volatile unsigned int *)0x8168)

int sys_read(char *buf, int cap) {
    unsigned int tot = INPUT_LEN_ADDR;
    unsigned int cur = INPUT_CURSOR_ADDR;
    int cnt = 0;
    while (cnt < cap && cur < tot) {
        char ch = INPUT_DATA_ADDR[cur++];
        buf[cnt++] = ch;
        if (ch == 10) break; // newline
    }
    if (SABOTAGE_FLAG == 0) {
        INPUT_CURSOR_ADDR = cur;
    }
    return cnt;
}

void sys_write(const char *buf, int n) {
    unsigned int cur = OUTPUT_LEN_ADDR;
    for (int i = 0; i < n; i++) {
        OUTPUT_DATA_ADDR[cur++] = buf[i];
    }
    OUTPUT_LEN_ADDR = cur;
}

int main(void) {
    char buf[64];
    while (1) {
        int n = sys_read(buf, sizeof(buf));
        if (n <= 0) break;
        sys_write(buf, n);
        if (SABOTAGE_FLAG != 0) break; // fail early on sabotage
    }
    return 0;
}
"""

CRT0_S = """
.globl _start
_start:
li sp, 0x4000
call main
ecall
"""


class InteractiveEchoSession:
    """Session managing the Rung 0 interactive echo loop on GlyphCPUv2."""

    _cached_pixels: Optional[np.ndarray] = None
    _cached_elf_bytes: Optional[bytes] = None

    @classmethod
    def _compile_and_assemble(cls) -> tuple[np.ndarray, bytes]:
        if cls._cached_pixels is not None and cls._cached_elf_bytes is not None:
            return cls._cached_pixels, cls._cached_elf_bytes

        with tempfile.TemporaryDirectory(prefix="rung0_build_") as td:
            tmp = Path(td)
            c_file = tmp / "rung0.c"
            c_file.write_text(RUNG0_ECHO_C)
            crt0_file = tmp / "crt0.S"
            crt0_file.write_text(CRT0_S)
            elf_file = tmp / "rung0.elf"

            cmd = [
                "riscv64-unknown-elf-gcc",
                "-march=rv32i",
                "-mabi=ilp32",
                "-O1",
                "-nostdlib",
                "-fno-builtin",
                "-w",
                "-Wl,-Ttext=0x0",
                str(crt0_file),
                str(c_file),
                "-o",
                str(elf_file),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"Rung 0 compile failed: {res.stderr}")

            elf_bytes = elf_file.read_bytes()
            glyph_src = transpile_elf_to_glyph(
                elf_bytes, entry_symbol="_start", byte_to_word_mem=True
            )
            pixels, _ = assemble_glyph_to_pixels(
                glyph_src, cols_instrs=64, min_rows=32
            )
            cls._cached_pixels = pixels
            cls._cached_elf_bytes = elf_bytes
            return pixels, elf_bytes

    def __init__(self) -> None:
        self.om = OpcodeMapV2()
        self.cpu = GlyphCPUv2(self.om, cols_instrs=64)
        self.cpu.memory = [0] * 16384
        self.pixels, self.elf_bytes = self._compile_and_assemble()
        self.sabotage_stub_cursor_advance: bool = False
        self._console = TextConsole()

        # Seed data sections from ELF
        for vaddr, blob in parse_elf_data_sections(self.elf_bytes):
            for i, b in enumerate(blob):
                w = (vaddr + i) >> 2
                sh = ((vaddr + i) & 3) * 8
                self.cpu.memory[w] = (self.cpu.memory[w] & ~(0xFF << sh)) | (b << sh)

    def feed_input(self, data: Union[bytes, str]) -> None:
        """Seed the GO-3 input ring with data."""
        if isinstance(data, str):
            data = data.encode("latin1")
        self.cpu.memory[INPUT_LEN_ADDR >> 2] = len(data)
        self.cpu.memory[INPUT_CURSOR_ADDR >> 2] = 0
        for i in range(0, len(data), 4):
            chunk = data[i:i + 4]
            packed = int.from_bytes(chunk + b"\x00" * (4 - len(chunk)), "little")
            self.cpu.memory[(INPUT_DATA_ADDR >> 2) + (i >> 2)] = packed

    def run(self, max_instructions: int = 50000) -> int:
        """Execute the interactive echo program until HALT."""
        if self.sabotage_stub_cursor_advance:
            self.cpu.memory[SABOTAGE_FLAG_ADDR >> 2] = 1
        else:
            self.cpu.memory[SABOTAGE_FLAG_ADDR >> 2] = 0

        self.cpu.pc = (0, 0)
        self.cpu.running = True
        steps = 0
        while self.cpu.running and steps < max_instructions:
            self.cpu.step(self.pixels)
            steps += 1

        # Feed output to TextConsole
        out_b = self.output_bytes()
        if out_b:
            self._console.feed(out_b.decode("latin1", errors="replace"))

        return steps

    def output_bytes(self) -> bytes:
        """Read accumulated output bytes from memory buffer."""
        out_len = self.cpu.memory[OUTPUT_LEN_ADDR >> 2]
        res = bytearray()
        for i in range(out_len):
            w = (OUTPUT_DATA_ADDR + i) >> 2
            sh = ((OUTPUT_DATA_ADDR + i) & 3) * 8
            b = (self.cpu.memory[w] >> sh) & 0xFF
            res.append(b)
        return bytes(res)

    def cursor(self) -> int:
        """Return the current input ring cursor."""
        return self.cpu.memory[INPUT_CURSOR_ADDR >> 2]

    def render_console_band(self) -> np.ndarray:
        return self._console.render_band()

    def decode_console_band(self, band: np.ndarray) -> str:
        return self._console.decode_band(band)


FORTH_REPL_C = """
#define INPUT_LEN_ADDR    (*(volatile unsigned int *)0x8170)
#define INPUT_CURSOR_ADDR (*(volatile unsigned int *)0x8174)
#define INPUT_DATA_ADDR   ((volatile char *)0x8180)

#define OUTPUT_LEN_ADDR   (*(volatile unsigned int *)0x81C0)
#define OUTPUT_DATA_ADDR  ((volatile char *)0x81C4)
#define INIT_FLAG         (*(volatile unsigned int *)0x8164)
#define SABOTAGE_FLAG     (*(volatile unsigned int *)0x8168)

int __mulsi3(int a, int b) {
    int res = 0;
    int sign = 1;
    if (a < 0) { sign = -sign; a = -a; }
    if (b < 0) { sign = -sign; b = -b; }
    while (b > 0) {
        if (b & 1) res += a;
        a <<= 1;
        b >>= 1;
    }
    return sign < 0 ? -res : res;
}

int __divsi3(int a, int b) {
    if (b == 0) return 0;
    int sign = 1;
    if (a < 0) { sign = -sign; a = -a; }
    if (b < 0) { sign = -sign; b = -b; }
    int q = 0;
    while (a >= b) {
        a -= b;
        q++;
    }
    return sign < 0 ? -q : q;
}

int __modsi3(int a, int b) {
    if (b == 0) return 0;
    if (a < 0) a = -a;
    if (b < 0) b = -b;
    while (a >= b) {
        a -= b;
    }
    return a;
}

#define STACK_CAP 32
#define MAX_WORDS 32
#define MAX_WORD_TOKENS 16
#define MAX_NAME_LEN 8

static int stack[STACK_CAP];
static int sp = 0;

static void push(int v) {
    if (sp < STACK_CAP) stack[sp++] = v;
}
static int pop(void) {
    if (sp > 0) return stack[--sp];
    return 0;
}

static void emit_char(char c) {
    unsigned int cur = OUTPUT_LEN_ADDR;
    OUTPUT_DATA_ADDR[cur++] = c;
    OUTPUT_LEN_ADDR = cur;
}

static void emit_int(int v) {
    if (v < 0) {
        emit_char('-');
        v = -v;
    }
    char buf[16];
    int p = 0;
    if (v == 0) {
        buf[p++] = '0';
    } else {
        while (v > 0) {
            buf[p++] = '0' + (v % 10);
            v /= 10;
        }
    }
    for (int i = p - 1; i >= 0; i--) {
        emit_char(buf[i]);
    }
    emit_char(10); // newline
}

enum {
    OP_NONE = 0,
    OP_ADD, OP_SUB, OP_MUL, OP_DIV,
    OP_DUP, OP_DROP, OP_SWAP, OP_DOT
};

typedef struct {
    char name[MAX_NAME_LEN];
    int builtin_op;
    int token_count;
    int tokens[MAX_WORD_TOKENS];
} DictEntry;

static DictEntry dict[MAX_WORDS];
static int num_words = 0;

static int str_eq(const char *a, const char *b) {
    int i = 0;
    while (a[i] && b[i]) {
        if (a[i] != b[i]) return 0;
        i++;
    }
    return a[i] == b[i];
}

static void str_copy(char *dst, const char *src) {
    int i = 0;
    while (src[i] && i < MAX_NAME_LEN - 1) {
        dst[i] = src[i];
        i++;
    }
    dst[i] = 0;
}

static void add_builtin(const char *name, int op) {
    str_copy(dict[num_words].name, name);
    dict[num_words].builtin_op = op;
    dict[num_words].token_count = 0;
    num_words++;
}

static void init_forth(void) {
    num_words = 0;
    add_builtin("+", OP_ADD);
    add_builtin("-", OP_SUB);
    add_builtin("*", OP_MUL);
    add_builtin("/", OP_DIV);
    add_builtin("dup", OP_DUP);
    add_builtin("drop", OP_DROP);
    add_builtin("swap", OP_SWAP);
    add_builtin(".", OP_DOT);
}

static int find_word(const char *name) {
    if (SABOTAGE_FLAG == 0) {
        for (int i = 0; i < num_words; i++) {
            if (str_eq(dict[i].name, name)) return i;
        }
    }
    emit_char('{');
    for (int k = 0; name[k]; k++) emit_char(name[k]);
    emit_char('?');
    emit_char('}');
    return -1;
}

static void exec_builtin(int op) {
    if (op == OP_ADD) {
        int b = pop(); int a = pop(); push(a + b);
    } else if (op == OP_SUB) {
        int b = pop(); int a = pop(); push(a - b);
    } else if (op == OP_MUL) {
        int b = pop(); int a = pop(); push(a * b);
    } else if (op == OP_DIV) {
        int b = pop(); int a = pop(); push(b != 0 ? a / b : 0);
    } else if (op == OP_DUP) {
        int a = pop(); push(a); push(a);
    } else if (op == OP_DROP) {
        pop();
    } else if (op == OP_SWAP) {
        int b = pop(); int a = pop(); push(b); push(a);
    } else if (op == OP_DOT) {
        int a = pop(); emit_int(a);
    }
}

static void exec_word(int idx) {
    if (dict[idx].builtin_op != OP_NONE) {
        exec_builtin(dict[idx].builtin_op);
    } else {
        for (int i = 0; i < dict[idx].token_count; i++) {
            exec_word(dict[idx].tokens[i]);
        }
    }
}

static int next_token(char *token) {
    unsigned int tot = INPUT_LEN_ADDR;
    unsigned int cur = INPUT_CURSOR_ADDR;
    while (cur < tot && ((unsigned char)INPUT_DATA_ADDR[cur]) <= 32) {
        cur++;
    }
    if (cur >= tot) {
        INPUT_CURSOR_ADDR = cur;
        return 0;
    }
    int p = 0;
    while (cur < tot && ((unsigned char)INPUT_DATA_ADDR[cur]) > 32) {
        if (p < MAX_NAME_LEN - 1) {
            token[p++] = INPUT_DATA_ADDR[cur];
        }
        cur++;
    }
    token[p] = 0;
    INPUT_CURSOR_ADDR = cur;
    return p;
}

static int is_number(const char *tok, int *out_val) {
    int i = 0;
    int sign = 1;
    if (tok[0] == '-') {
        sign = -1;
        i++;
    }
    if (!tok[i]) return 0;
    int val = 0;
    for (; tok[i]; i++) {
        if (tok[i] < '0' || tok[i] > '9') return 0;
        val = (val << 3) + (val << 1) + (tok[i] - '0');
    }
    *out_val = (sign < 0) ? -val : val;
    return 1;
}

int main(void) {
    if (INIT_FLAG == 0) {
        init_forth();
        sp = 0;
        INIT_FLAG = 1;
    }

    char tok[16];
    int compiling = 0;
    int current_def = -1;

    while (next_token(tok)) {
        if (compiling) {
            if (str_eq(tok, ";")) {
                compiling = 0;
                current_def = -1;
            } else if (current_def == -1) {
                current_def = num_words++;
                str_copy(dict[current_def].name, tok);
                dict[current_def].builtin_op = OP_NONE;
                dict[current_def].token_count = 0;
            } else {
                int w_idx = find_word(tok);
                if (w_idx >= 0 && dict[current_def].token_count < MAX_WORD_TOKENS) {
                    dict[current_def].tokens[dict[current_def].token_count++] = w_idx;
                }
            }
        } else {
            if (str_eq(tok, ":")) {
                compiling = 1;
                current_def = -1;
            } else {
                int num;
                if (is_number(tok, &num)) {
                    push(num);
                } else {
                    int w_idx = find_word(tok);
                    if (w_idx >= 0) {
                        exec_word(w_idx);
                    }
                }
            }
        }
    }
    return 0;
}
"""

FORTH_CRT0_S = """
.globl _start
_start:
.option push
.option norelax
lui gp, %hi(__global_pointer$)
addi gp, gp, %lo(__global_pointer$)
.option pop
li sp, 0x6000
call main
ecall
"""


class ForthSession:
    """Session managing the Rung 1 interactive Forth REPL on GlyphCPUv2."""

    _cached_pixels: Optional[np.ndarray] = None
    _cached_elf_bytes: Optional[bytes] = None
    _cached_ptr_table: Optional[Dict[int, int]] = None

    PTR_TABLE_BASE: int = 0x4000

    @classmethod
    def _compile_and_assemble(cls) -> tuple[np.ndarray, bytes, Dict[int, int]]:
        if (
            cls._cached_pixels is not None
            and cls._cached_elf_bytes is not None
            and cls._cached_ptr_table is not None
        ):
            return cls._cached_pixels, cls._cached_elf_bytes, cls._cached_ptr_table

        with tempfile.TemporaryDirectory(prefix="rung1_build_") as td:
            tmp = Path(td)
            c_file = tmp / "forth.c"
            c_file.write_text(FORTH_REPL_C)
            crt0_file = tmp / "crt0.S"
            crt0_file.write_text(FORTH_CRT0_S)
            elf_file = tmp / "forth.elf"

            cmd = [
                "riscv64-unknown-elf-gcc",
                "-march=rv32i",
                "-mabi=ilp32",
                "-O1",
                "-nostdlib",
                "-fno-builtin",
                "-w",
                "-Wl,-Ttext=0x0",
                "-Wl,-Tdata=0x2000",
                str(crt0_file),
                str(c_file),
                "-o",
                str(elf_file),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"Rung 1 Forth compile failed: {res.stderr}")

            elf_bytes = elf_file.read_bytes()

            bin_file = tmp / "text.bin"
            subprocess.run(
                [
                    "riscv64-unknown-elf-objcopy",
                    "-O",
                    "binary",
                    "--only-section=.text",
                    str(elf_file),
                    str(bin_file),
                ],
                check=True,
            )
            text_bytes = bin_file.read_bytes()

            glyph_src = transpile_elf_to_glyph(
                elf_bytes,
                entry_symbol="_start",
                byte_to_word_mem=True,
                ptr_table_base=cls.PTR_TABLE_BASE,
            )
            pixels, coords = assemble_glyph_to_pixels(
                glyph_src, cols_instrs=64, min_rows=32
            )
            ptr_table = build_pointer_table(text_bytes, 0, coords)

            cls._cached_pixels = pixels
            cls._cached_elf_bytes = elf_bytes
            cls._cached_ptr_table = ptr_table
            return pixels, elf_bytes, ptr_table

    def __init__(self) -> None:
        self.om = OpcodeMapV2()
        self.cpu = GlyphCPUv2(self.om, cols_instrs=64)
        self.cpu.memory = [0] * 16384
        self.pixels, self.elf_bytes, self.ptr_table = self._compile_and_assemble()
        self.sabotage_stub_dict_lookup: bool = False
        self._console = TextConsole()
        self._console_offset: int = 0
        self._last_out_len: int = 0

        # Seed data and rodata sections from ELF
        for vaddr, blob in parse_elf_data_sections(self.elf_bytes):
            for i, b in enumerate(blob):
                w = (vaddr + i) >> 2
                sh = ((vaddr + i) & 3) * 8
                self.cpu.memory[w] = (self.cpu.memory[w] & ~(0xFF << sh)) | (b << sh)

        # Seed dynamic-jump pointer table
        for word_idx, packed in self.ptr_table.items():
            self.cpu.memory[(self.PTR_TABLE_BASE >> 2) + word_idx] = packed

    def feed_input(self, data: Union[bytes, str]) -> None:
        """Seed the GO-3 input ring with data for the next turn."""
        if isinstance(data, str):
            data = data.encode("latin1")
        self._last_out_len = self.cpu.memory[OUTPUT_LEN_ADDR >> 2]
        self.cpu.memory[INPUT_LEN_ADDR >> 2] = len(data)
        self.cpu.memory[INPUT_CURSOR_ADDR >> 2] = 0
        for i in range(0, len(data), 4):
            chunk = data[i:i + 4]
            packed = int.from_bytes(chunk + b"\x00" * (4 - len(chunk)), "little")
            self.cpu.memory[(INPUT_DATA_ADDR >> 2) + (i >> 2)] = packed

    def run(self, max_instructions: int = 50000) -> int:
        """Execute the interactive Forth REPL for the current input turn."""
        if self.sabotage_stub_dict_lookup:
            self.cpu.memory[SABOTAGE_FLAG_ADDR >> 2] = 1
        else:
            self.cpu.memory[SABOTAGE_FLAG_ADDR >> 2] = 0

        self.cpu.pc = (0, 0)
        self.cpu.running = True
        steps = 0
        while self.cpu.running and steps < max_instructions:
            self.cpu.step(self.pixels)
            steps += 1

        # Feed newly produced output to TextConsole
        out_b = self.output_bytes()
        if len(out_b) > self._console_offset:
            new_chunk = out_b[self._console_offset:]
            self._console.feed(new_chunk.decode("latin1", errors="replace"))
            self._console_offset = len(out_b)

        return steps

    def output_bytes(self) -> bytes:
        """Read all accumulated output bytes across all turns."""
        out_len = self.cpu.memory[OUTPUT_LEN_ADDR >> 2]
        res = bytearray()
        for i in range(out_len):
            w = (OUTPUT_DATA_ADDR + i) >> 2
            sh = ((OUTPUT_DATA_ADDR + i) & 3) * 8
            b = (self.cpu.memory[w] >> sh) & 0xFF
            res.append(b)
        return bytes(res)

    def last_output_bytes(self) -> bytes:
        """Read output bytes produced specifically in the most recent turn."""
        out_len = self.cpu.memory[OUTPUT_LEN_ADDR >> 2]
        res = bytearray()
        for i in range(self._last_out_len, out_len):
            w = (OUTPUT_DATA_ADDR + i) >> 2
            sh = ((OUTPUT_DATA_ADDR + i) & 3) * 8
            b = (self.cpu.memory[w] >> sh) & 0xFF
            res.append(b)
        return bytes(res)

    def cursor(self) -> int:
        """Return the current input ring cursor."""
        return self.cpu.memory[INPUT_CURSOR_ADDR >> 2]

    def render_console_band(self) -> np.ndarray:
        return self._console.render_band()

    def decode_console_band(self, band: np.ndarray) -> str:
        return self._console.decode_band(band)



# --- BK-253 Rung 2: NanoPy slice (Python-expression REPL) ------------------

from tools.nanopy_slice import NANOPY_C, NANOPY_CRT0_S  # noqa: E402


class NanoPySession:
    """Rung 2: tiny Python-expression REPL in freestanding C through the
    rv32i -> Glyph pipeline.  Same memory map / turn semantics as Rung 1;
    state (variables) persists in .bss across hardware restarts."""

    _cached_pixels: Optional[np.ndarray] = None
    _cached_elf_bytes: Optional[bytes] = None
    _cached_ptr_table: Optional[Dict[int, int]] = None

    PTR_TABLE_BASE: int = 0x4000

    @classmethod
    def _compile_and_assemble(cls):
        if (
            cls._cached_pixels is not None
            and cls._cached_elf_bytes is not None
            and cls._cached_ptr_table is not None
        ):
            return cls._cached_pixels, cls._cached_elf_bytes, cls._cached_ptr_table

        with tempfile.TemporaryDirectory(prefix="rung2_build_") as td:
            tmp = Path(td)
            c_file = tmp / "nanopy.c"
            c_file.write_text(NANOPY_C)
            crt0_file = tmp / "crt0.S"
            crt0_file.write_text(NANOPY_CRT0_S)
            elf_file = tmp / "nanopy.elf"

            cmd = [
                "riscv64-unknown-elf-gcc",
                "-march=rv32i",
                "-mabi=ilp32",
                "-Os",
                "-nostdlib",
                "-fno-builtin",
                "-w",
                "-Wl,-Ttext=0x0",
                "-Wl,-Tdata=0x2000",
                str(crt0_file),
                str(c_file),
                "-o",
                str(elf_file),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"Rung 2 NanoPy compile failed: {res.stderr}")

            elf_bytes = elf_file.read_bytes()

            bin_file = tmp / "text.bin"
            subprocess.run(
                [
                    "riscv64-unknown-elf-objcopy",
                    "-O",
                    "binary",
                    "--only-section=.text",
                    str(elf_file),
                    str(bin_file),
                ],
                check=True,
            )
            text_bytes = bin_file.read_bytes()

            glyph_src = transpile_elf_to_glyph(
                elf_bytes,
                entry_symbol="_start",
                byte_to_word_mem=True,
                ptr_table_base=cls.PTR_TABLE_BASE,
            )
            pixels, coords = assemble_glyph_to_pixels(
                glyph_src, cols_instrs=64, min_rows=32
            )
            ptr_table = build_pointer_table(text_bytes, 0, coords)

            cls._cached_pixels = pixels
            cls._cached_elf_bytes = elf_bytes
            cls._cached_ptr_table = ptr_table
            return pixels, elf_bytes, ptr_table

    def __init__(self) -> None:
        self.om = OpcodeMapV2()
        self.cpu = GlyphCPUv2(self.om, cols_instrs=64)
        self.cpu.memory = [0] * 16384
        self.pixels, self.elf_bytes, self.ptr_table = self._compile_and_assemble()
        self.sabotage_stub_eval: bool = False
        self._console = TextConsole()
        self._console_offset: int = 0
        self._last_out_len: int = 0

        for vaddr, blob in parse_elf_data_sections(self.elf_bytes):
            for i, b in enumerate(blob):
                w = (vaddr + i) >> 2
                sh = ((vaddr + i) & 3) * 8
                self.cpu.memory[w] = (self.cpu.memory[w] & ~(0xFF << sh)) | (b << sh)

        for word_idx, packed in self.ptr_table.items():
            self.cpu.memory[(self.PTR_TABLE_BASE >> 2) + word_idx] = packed

    @property
    def elf_size_bytes(self) -> int:
        return len(self.elf_bytes)

    def loaded_section_bytes(self) -> int:
        """Sum of loadable code/data section sizes (.text+.rodata+.data).
        The honest budget metric: raw ELF bytes are dominated by vaddr
        sparseness, not program content."""
        from tools.rv64i_to_glyph import parse_elf_data_sections
        import struct

        def u32(off):
            return struct.unpack_from("<I", self.elf_bytes, off)[0]

        def u16(off):
            return struct.unpack_from("<H", self.elf_bytes, off)[0]

        shoff = u32(0x20)
        shentsize = u16(0x2E)
        shnum = u16(0x30)
        total = 0
        for i in range(shnum):
            base = shoff + i * shentsize
            sh_type = u32(base + 4)
            sh_flags = u32(base + 8)
            sh_size = u32(base + 20)
            # SHT_PROGBITS (1) with ALLOC (0x2): .text, .rodata, .data
            if sh_type == 1 and (sh_flags & 0x2) and sh_size:
                total += sh_size
        return total

    def feed_input(self, data) -> None:
        if isinstance(data, str):
            data = data.encode("latin1")
        self._last_out_len = self.cpu.memory[OUTPUT_LEN_ADDR >> 2]
        self.cpu.memory[INPUT_LEN_ADDR >> 2] = len(data)
        self.cpu.memory[INPUT_CURSOR_ADDR >> 2] = 0
        for i in range(0, len(data), 4):
            chunk = data[i:i + 4]
            packed = int.from_bytes(chunk + b"\x00" * (4 - len(chunk)), "little")
            self.cpu.memory[(INPUT_DATA_ADDR >> 2) + (i >> 2)] = packed

    def run(self, max_instructions: int = 50000) -> int:
        if self.sabotage_stub_eval:
            self.cpu.memory[SABOTAGE_FLAG_ADDR >> 2] = 1
        else:
            self.cpu.memory[SABOTAGE_FLAG_ADDR >> 2] = 0

        self.cpu.pc = (0, 0)
        self.cpu.running = True
        steps = 0
        while self.cpu.running and steps < max_instructions:
            self.cpu.step(self.pixels)
            steps += 1

        out_b = self.output_bytes()
        if len(out_b) > self._console_offset:
            new_chunk = out_b[self._console_offset:]
            self._console.feed(new_chunk.decode("latin1", errors="replace"))
            self._console_offset = len(out_b)

        return steps

    def boot_step_count(self) -> int:
        """Steps for a fresh interpreter's first (init) turn: measured,
        not assumed - trivial turn on a scratch instance, counted."""
        scratch = object.__new__(NanoPySession)
        scratch.om = self.om
        scratch.cpu = GlyphCPUv2(self.om, cols_instrs=64)
        scratch.cpu.memory = [0] * 16384
        scratch.pixels = self.pixels
        scratch.elf_bytes = self.elf_bytes
        scratch.ptr_table = self.ptr_table
        scratch.sabotage_stub_eval = False
        scratch._console = TextConsole()
        scratch._console_offset = 0
        scratch._last_out_len = 0
        for vaddr, blob in parse_elf_data_sections(self.elf_bytes):
            for i, b in enumerate(blob):
                w = (vaddr + i) >> 2
                sh = ((vaddr + i) & 3) * 8
                scratch.cpu.memory[w] = (
                    scratch.cpu.memory[w] & ~(0xFF << sh)
                ) | (b << sh)
        for word_idx, packed in self.ptr_table.items():
            scratch.cpu.memory[(self.PTR_TABLE_BASE >> 2) + word_idx] = packed
        scratch.feed_input(b"1\n")
        return scratch.run()

    def output_bytes(self) -> bytes:
        out_len = self.cpu.memory[OUTPUT_LEN_ADDR >> 2]
        res = bytearray()
        for i in range(out_len):
            w = (OUTPUT_DATA_ADDR + i) >> 2
            sh = ((OUTPUT_DATA_ADDR + i) & 3) * 8
            b = (self.cpu.memory[w] >> sh) & 0xFF
            res.append(b)
        return bytes(res)

    def last_output_bytes(self) -> bytes:
        out_len = self.cpu.memory[OUTPUT_LEN_ADDR >> 2]
        res = bytearray()
        for i in range(self._last_out_len, out_len):
            w = (OUTPUT_DATA_ADDR + i) >> 2
            sh = ((OUTPUT_DATA_ADDR + i) & 3) * 8
            b = (self.cpu.memory[w] >> sh) & 0xFF
            res.append(b)
        return bytes(res)

    def cursor(self) -> int:
        return self.cpu.memory[INPUT_CURSOR_ADDR >> 2]

    def render_console_band(self):
        return self._console.render_band()

    def decode_console_band(self, band):
        return self._console.decode_band(band)
