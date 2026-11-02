
# --- BK-253 Rung 2: NanoPy slice ------------------------------------------
# A tiny Python-expression REPL in freestanding C, compiled through the same
# rv32i -> Glyph pipeline as Rungs 0/1.  Honest scope (per Path A decision,
# Jericho 2026-10-09): integer literals, + - * / ( ) with precedence,
# single-letter variables with assignment, print("..."), expression echo.
# NOT Python: no strings-as-values, no lists, no floats, no control flow.

NANOPY_CRT0_S = r"""
.section .text.init
.globl _start
_start:
    .option push
    .option norelax
    lui gp, %hi(__global_pointer$)
    addi gp, gp, %lo(__global_pointer$)
    .option pop
    li sp, 0x6000
    call nanopy_main
    ecall
"""

NANOPY_C = r"""
#define INPUT_LEN_ADDR    (*(volatile unsigned int *)0x8170)
#define INPUT_CURSOR_ADDR (*(volatile unsigned int *)0x8174)
#define INPUT_DATA_ADDR   ((volatile char *)0x8180)
#define OUTPUT_LEN_ADDR   (*(volatile unsigned int *)0x81C0)
#define OUTPUT_DATA_ADDR  ((volatile char *)0x81C4)
#define SABOTAGE_FLAG     (*(volatile unsigned int *)0x8168)

/* single-letter variables: 'a'..'z' -> vars[0..25]; -999999 = undefined */
static int vars[26];

static void out_ch(char c) {
    OUTPUT_DATA_ADDR[OUTPUT_LEN_ADDR] = c;
    OUTPUT_LEN_ADDR = OUTPUT_LEN_ADDR + 1;
}

static void out_str(const char *s) {
    while (*s) { out_ch(*s); s = s + 1; }
}

static void out_num(int v) {
    if (v < 0) { out_ch('-'); v = -v; }
    if (v > 9) out_num(v / 10);
    out_ch((char)('0' + (v % 10)));
}

static char peek(void) {
    if (INPUT_CURSOR_ADDR >= INPUT_LEN_ADDR) return 0;
    return INPUT_DATA_ADDR[INPUT_CURSOR_ADDR];
}

static void advance(void) {
    if (INPUT_CURSOR_ADDR < INPUT_LEN_ADDR)
        INPUT_CURSOR_ADDR = INPUT_CURSOR_ADDR + 1;
}

static void skip_ws(void) {
    while (peek() == ' ' || peek() == '\t') advance();
}

static int parse_expr(void);

static int parse_primary(void) {
    skip_ws();
    char c = peek();
    if (c >= '0' && c <= '9') {
        int v = 0;
        while (peek() >= '0' && peek() <= '9') {
            v = v * 10 + (peek() - '0');
            advance();
        }
        return v;
    }
    if (c >= 'a' && c <= 'z') {
        int idx = c - 'a';
        advance();
        if (vars[idx] == -999999) {
            out_ch('{'); out_ch(c); out_ch('?'); out_ch('}');
            return 0;
        }
        return vars[idx];
    }
    if (c == '(') {
        advance();
        int v = parse_expr();
        skip_ws();
        if (peek() == ')') advance();
        return v;
    }
    return 0;
}

static int parse_term(void) {
    int v = parse_primary();
    for (;;) {
        skip_ws();
        char c = peek();
        if (c == '*') { advance(); v = v * parse_primary(); }
        else if (c == '/') {
            advance();
            int d = parse_primary();
            if (d == 0) { out_str("ERR:DIV0"); return v; }
            v = v / d;
        }
        else return v;
    }
}

static int parse_expr(void) {
    int v = parse_term();
    for (;;) {
        skip_ws();
        char c = peek();
        if (c == '+') { advance(); v = v + parse_term(); }
        else if (c == '-') { advance(); v = v - parse_term(); }
        else return v;
    }
}

/* does the line start with the literal s? cursor untouched if not */
static int match_kw(const char *s) {
    unsigned int save = INPUT_CURSOR_ADDR;
    skip_ws();
    const char *p = s;
    while (*p) {
        if (peek() != *p) { INPUT_CURSOR_ADDR = save; return 0; }
        advance(); p = p + 1;
    }
    return 1;
}

static void nanopy_turn(void) {
    /* NOTE: cursor is positioned by the caller (host feed_input sets 0,
     * and this loop advances across lines within one turn). */
    if (INPUT_LEN_ADDR == 0) return;

    if (match_kw("print(")) {
        /* print("...")  -> emit the literal, no quotes */
        skip_ws();
        if (peek() == '"') {
            advance();
            while (peek() && peek() != '"') { out_ch(peek()); advance(); }
            if (peek() == '"') advance();
            skip_ws();
            if (peek() == ')') advance();
        }
        out_ch('\n');
    }
    else {
        /* assignment?  <letter> = expr  (but not ==) */
        unsigned int save = INPUT_CURSOR_ADDR;
        skip_ws();
        char c0 = peek();
        int is_assign = 0;
        if (c0 >= 'a' && c0 <= 'z') {
            advance();
            skip_ws();
            if (peek() == '=' && INPUT_CURSOR_ADDR + 1 < INPUT_LEN_ADDR
                && INPUT_DATA_ADDR[INPUT_CURSOR_ADDR + 1] != '=') {
                advance();
                is_assign = 1;
            } else {
                INPUT_CURSOR_ADDR = save;
            }
        }
        int v = parse_expr();
        if (is_assign) {
            vars[c0 - 'a'] = v;          /* assignment prints nothing */
        } else if (peek() != 0 && peek() != '\n') {
            /* trailing garbage after a full expression */
            out_str("ERR:SYNTAX\n");
        } else {
            out_num(v);
            out_ch('\n');
        }
    }
}

void nanopy_main(void) {
    /* one-shot init guard: state (vars) must survive multi-turn restarts */
    static int inited = 0;
    if (!inited) {
        for (int i = 0; i < 26; i = i + 1) vars[i] = -999999;
        inited = 1;
    }
    while (INPUT_CURSOR_ADDR < INPUT_LEN_ADDR) {
        nanopy_turn();
        /* consume trailing newline of this line */
        if (peek() == '\n') advance();
        if (SABOTAGE_FLAG) {
            /* sabotage leg: report broken evaluator loudly and stop */
            out_str("{eval?}\n");
            return;
        }
    }
}
"""

# Freestanding libgcc shims (same pattern as Rung 1's FORTH_REPL_C):
# rv32i has no M/D extension, so GCC emits calls to __XXXsi3 helpers which
# we must provide ourselves under -nostdlib.
NANOPY_C = (
    "int __mulsi3(int a, int b) {\n"
    "    int res = 0;\n"
    "    int sign = 1;\n"
    "    if (b < 0) { sign = -sign; b = -b; }\n"
    "    if (a < 0) { sign = -sign; a = -a; }\n"
    "    while (b) {\n"
    "        if (b & 1) res += a;\n"
    "        a <<= 1;\n"
    "        b >>= 1;\n"
    "    }\n"
    "    return sign < 0 ? -res : res;\n"
    "}\n"
    "\n"
    "int __divsi3(int a, int b) {\n"
    "    if (b == 0) return 0;\n"
    "    int sign = 1;\n"
    "    if (a < 0) { sign = -sign; a = -a; }\n"
    "    if (b < 0) { sign = -sign; b = -b; }\n"
    "    int q = 0;\n"
    "    while (a >= b) {\n"
    "        a -= b;\n"
    "        q++;\n"
    "    }\n"
    "    return sign < 0 ? -q : q;\n"
    "}\n"
    "\n"
    "int __modsi3(int a, int b) {\n"
    "    if (b == 0) return 0;\n"
    "    if (a < 0) a = -a;\n"
    "    if (b < 0) b = -b;\n"
    "    while (a >= b) {\n"
    "        a -= b;\n"
    "    }\n"
    "    return a;\n"
    "}\n"
) + NANOPY_C
