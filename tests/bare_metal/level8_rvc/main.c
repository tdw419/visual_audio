#include <stdint.h>

#define UART_BASE 0x10000000UL
volatile uint8_t *uart = (uint8_t *)UART_BASE;

void print_str(const char *s) {
    while (*s) *uart = *s++;
}

void print_hex64(uint64_t val) {
    const char hex[] = "0123456789ABCDEF";
    *uart = '0'; *uart = 'x';
    for (int i = 15; i >= 0; i--) {
        *uart = hex[(val >> (i * 4)) & 0xF];
    }
    *uart = '\n';
}

int fails = 0;

void check(const char *name, uint64_t got, uint64_t want) {
    print_str(name);
    print_str(": got=");
    print_hex64(got);
    if (got == want) {
        print_str("  PASS\n");
    } else {
        print_str("  FAIL want=");
        print_hex64(want);
        fails++;
    }
}

static uint64_t membuf[8] __attribute__((aligned(8)));

int main(void) {
    print_str("Level 8: RVC Edge Case Coverage\n");

    /* C.LUI: rd, nzimm[17:12] - pins into s0 (x8, in the 8-15 range) */
    {
        register uint64_t s0 asm("s0");
        asm volatile(".option push\n.option arch, +c\n"
                     "c.lui s0, 5\n"
                     ".option pop\n" : "=r"(s0));
        check("C.LUI (s0 = 5<<12)", s0, 0x5000UL);
    }

    /* C.ADDI16SP: modifies sp by a scaled immediate - save/restore around it */
    {
        uint64_t sp_before, sp_after;
        asm volatile(
            "mv %0, sp\n"
            ".option push\n.option arch, +c\n"
            "c.addi16sp sp, -32\n"
            ".option pop\n"
            "mv %1, sp\n"
            "addi sp, sp, 32\n"  /* restore */
            : "=&r"(sp_before), "=r"(sp_after));
        check("C.ADDI16SP (sp -= 32)", sp_before - sp_after, 32UL);
    }

    /* C.SUBW / C.ADDW: 32-bit sign-extending sub/add on s0'/s1' (x8/x9) */
    {
        register uint64_t s0 asm("s0") = 10;
        register uint64_t s1 asm("s1") = 3;
        asm volatile(".option push\n.option arch, +c\n"
                     "c.subw s0, s1\n"
                     ".option pop\n" : "+r"(s0) : "r"(s1));
        check("C.SUBW (10 - 3)", s0, 7UL);

        register uint64_t s0b asm("s0") = 7;
        register uint64_t s1b asm("s1") = 3;
        asm volatile(".option push\n.option arch, +c\n"
                     "c.addw s0, s1\n"
                     ".option pop\n" : "+r"(s0b) : "r"(s1b));
        check("C.ADDW (7 + 3)", s0b, 10UL);
    }

    /* C.SRLI / C.SRAI / C.ANDI on s0' (x8) */
    {
        register uint64_t s0 asm("s0") = 0xFFFFFFFFFFFFFF00UL;
        asm volatile(".option push\n.option arch, +c\nc.srli s0, 4\n.option pop\n" : "+r"(s0));
        check("C.SRLI (logical >> 4)", s0, 0x0FFFFFFFFFFFFFF0UL);
    }
    {
        register uint64_t s0 asm("s0") = 0xFFFFFFFFFFFFFF00UL;
        asm volatile(".option push\n.option arch, +c\nc.srai s0, 4\n.option pop\n" : "+r"(s0));
        check("C.SRAI (arith >> 4, sign-extends)", s0, 0xFFFFFFFFFFFFFFF0UL);
    }
    {
        register uint64_t s0 asm("s0") = 0xFF;
        asm volatile(".option push\n.option arch, +c\nc.andi s0, 0x0F\n.option pop\n" : "+r"(s0));
        check("C.ANDI (0xFF & 0x0F)", s0, 0x0FUL);
    }

    /* C.AND / C.OR / C.XOR on s0'/s1' */
    {
        register uint64_t s0 asm("s0") = 0xF0;
        register uint64_t s1 asm("s1") = 0x0F;
        asm volatile(".option push\n.option arch, +c\nc.or s0, s1\n.option pop\n" : "+r"(s0) : "r"(s1));
        check("C.OR (0xF0 | 0x0F)", s0, 0xFFUL);
    }
    {
        register uint64_t s0 asm("s0") = 0xFF;
        register uint64_t s1 asm("s1") = 0x0F;
        asm volatile(".option push\n.option arch, +c\nc.and s0, s1\n.option pop\n" : "+r"(s0) : "r"(s1));
        check("C.AND (0xFF & 0x0F)", s0, 0x0FUL);
    }
    {
        register uint64_t s0 asm("s0") = 0xFF;
        register uint64_t s1 asm("s1") = 0x0F;
        asm volatile(".option push\n.option arch, +c\nc.xor s0, s1\n.option pop\n" : "+r"(s0) : "r"(s1));
        check("C.XOR (0xFF ^ 0x0F)", s0, 0xF0UL);
    }

    /* C.LD / C.SD via compressed reg-based addressing (rs1'=s0 -> membuf) */
    {
        register uint64_t s0 asm("s0") = (uint64_t)membuf;
        register uint64_t a0 asm("a0") = 0xDEADBEEFCAFEBABEUL;
        asm volatile(".option push\n.option arch, +c\nc.sd a0, 0(s0)\n.option pop\n" :: "r"(s0), "r"(a0));

        register uint64_t s0b asm("s0") = (uint64_t)membuf;
        register uint64_t a1 asm("a1");
        asm volatile(".option push\n.option arch, +c\nc.ld a1, 0(s0)\n.option pop\n" : "=r"(a1) : "r"(s0b));
        check("C.SD/C.LD round-trip", a1, 0xDEADBEEFCAFEBABEUL);
    }

    /* C.LWSP / C.SWSP / C.LDSP / C.SDSP - stack-pointer-relative forms */
    {
        register uint64_t a0 asm("a0") = 0x1234567890ABCDEFUL;
        asm volatile(
            "addi sp, sp, -16\n"
            ".option push\n.option arch, +c\n"
            "c.sdsp a0, 0(sp)\n"
            ".option pop\n"
            :: "r"(a0));
        register uint64_t a1 asm("a1");
        asm volatile(".option push\n.option arch, +c\nc.ldsp a1, 0(sp)\n.option pop\naddi sp, sp, 16\n"
                     : "=r"(a1));
        check("C.SDSP/C.LDSP round-trip", a1, 0x1234567890ABCDEFUL);
    }
    {
        register uint64_t a0 asm("a0") = 0xCAFEBABEUL;
        asm volatile(
            "addi sp, sp, -16\n"
            ".option push\n.option arch, +c\n"
            "c.swsp a0, 0(sp)\n"
            ".option pop\n"
            :: "r"(a0));
        register uint64_t a1 asm("a1");
        asm volatile(".option push\n.option arch, +c\nc.lwsp a1, 0(sp)\n.option pop\naddi sp, sp, 16\n"
                     : "=r"(a1));
        /* LW (and so C.LWSP) sign-extends the 32-bit value to 64 bits;
         * 0xCAFEBABE has bit 31 set, so the correct result is
         * 0xFFFFFFFFCAFEBABE, not a naive zero-extend. */
        check("C.SWSP/C.LWSP round-trip", a1, 0xFFFFFFFFCAFEBABEUL);
    }

    /* C.MV / C.ADD */
    {
        register uint64_t a0 asm("a0");
        register uint64_t a1 asm("a1") = 0x42UL;
        asm volatile(".option push\n.option arch, +c\nc.mv a0, a1\n.option pop\n" : "=r"(a0) : "r"(a1));
        check("C.MV (a0 = a1)", a0, 0x42UL);
    }
    {
        register uint64_t a0 asm("a0") = 10UL;
        register uint64_t a1 asm("a1") = 32UL;
        asm volatile(".option push\n.option arch, +c\nc.add a0, a1\n.option pop\n" : "+r"(a0) : "r"(a1));
        check("C.ADD (10 + 32)", a0, 42UL);
    }

    /* C.JR / C.JALR: jump-register forms, verified via a landing label */
    {
        register uint64_t a0 asm("a0") = 0;
        asm volatile(
            "la t0, 1f\n"
            ".option push\n.option arch, +c\n"
            "c.jr t0\n"
            ".option pop\n"
            "li a0, 111\n"  /* should be skipped */
            "1: li a0, 222\n"
            : "+r"(a0) :: "t0");
        check("C.JR (landed past skipped instr)", a0, 222UL);
    }
    {
        register uint64_t ra asm("a0") = 0;
        asm volatile(
            "la t0, 1f\n"
            ".option push\n.option arch, +c\n"
            "c.jalr t0\n"
            ".option pop\n"
            "j 2f\n"
            "1: li a0, 333\n"
            "ret\n"      /* c.jalr set ra to the instruction after itself (the `j 2f`) */
            "2:\n"
            : "+r"(ra) :: "t0", "ra");
        check("C.JALR (landed at label, a0 set)", ra, 333UL);
    }

    /* C.BEQZ / C.BNEZ */
    {
        register uint64_t s0 asm("s0") = 0;
        register uint64_t a0 asm("a0") = 0;
        asm volatile(
            ".option push\n.option arch, +c\n"
            "c.beqz s0, 1f\n"
            ".option pop\n"
            "li a0, 111\n"
            "j 2f\n"
            "1: li a0, 222\n"
            "2:\n"
            : "+r"(a0) : "r"(s0));
        check("C.BEQZ (zero -> taken)", a0, 222UL);
    }
    {
        register uint64_t s0 asm("s0") = 5;
        register uint64_t a0 asm("a0") = 0;
        asm volatile(
            ".option push\n.option arch, +c\n"
            "c.bnez s0, 1f\n"
            ".option pop\n"
            "li a0, 111\n"
            "j 2f\n"
            "1: li a0, 222\n"
            "2:\n"
            : "+r"(a0) : "r"(s0));
        check("C.BNEZ (nonzero -> taken)", a0, 222UL);
    }

    print_str("\n");
    if (fails == 0) {
        print_str("ALL RVC EDGE CASES PASSED\n");
    } else {
        print_str("SOME RVC EDGE CASES FAILED: ");
        print_hex64((uint64_t)fails);
    }

    while (1) {
        asm volatile("wfi");
    }
}
