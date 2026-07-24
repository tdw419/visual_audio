// RVC Quadrant 2 Test
// Instructions: C.SLLI, C.MV, C.ADD, C.LWSP
//
// This test verifies that compressed instructions decode and execute
// correctly on the GPU RISC-V emulator, producing identical results
// to QEMU.

#include "riscv_test.h"

// Test register layout
// x8-x15: compressed registers for testing
// x5-x7: scratch registers
// x3: test result
// x31: test counter

// Test values
#define TEST_VAL_A  0xDEADBEEF
#define TEST_VAL_B  0xCAFEBABE
#define TEST_VAL_C  0x12345678
#define EXPECTED_RESULT 0x00000000

.section .text
.globl _start

_start:
    // Setup: Initialize compressed registers (x8-x15)
    li  x8,  TEST_VAL_A   // rd' = A
    li  x9,  TEST_VAL_B   // rd' = B
    li  x10, TEST_VAL_C   // rd' = C
    li  x11, 0            // scratch
    li  x12, 0            // scratch
    li  x13, 0            // scratch
    li  x14, 0            // scratch
    li  x15, 0            // scratch
    
    // Initialize result register
    li  x3, 0
    
    // Test 1: C.SLLI - Shift left logical immediate
    // c.slli x8, 8  -> x8 = x8 << 8
    slli x8, x8, 8      // May emit C.SLLI
    
    // Verify
    li  x5, TEST_VAL_A
    slli x5, x5, 8
    bne x8, x5, fail
    // Test 2: C.MV - Move register (add rd, rs2, x0)
    // c.mv x11, x8  -> x11 = x8
    mv  x11, x8         // May emit C.MV
    
    // Verify
    bne x11, x8, fail
    // Test 3: C.ADD - Add registers (add rd', rs1', rs2')
    // c.add x8, x9  -> x8 = x8 + x9 (using compressed regs x8-x15)
    add x8, x8, x9      // May emit C.ADD
    
    // Verify x8 = TEST_VAL_A + TEST_VAL_B
    li  x5, TEST_VAL_A
    li  x6, TEST_VAL_B
    add x5, x5, x6
    bne x8, x5, fail
    // Test 4: C.LWSP - Load word from offset[7:2](sp) into rd
    // Setup test memory at sp + 8
    li  x5, 0x12345678
    sd  x5, 8(sp)
    
    // c.lwsp x6, 8(sp)  -> Load word from sp+8 into x6
    lw  x6, 8(sp)
    
    // Verify
    li  x5, 0x12345678
    bne x6, x5, fail

    // All tests passed - set success marker
    li  x3, 0x424F4F54  // "BOOT" magic
    li  x31, 0x00000001 // test counter = 1
    j   done

fail:
    // Test failed - set failure marker
    li  x3, 0x4641494C  // "FAIL" magic
    li  x31, 0xFFFFFFFF

done:
    // Halt
    wfi
    j   done

.section .data
test_data:
    .quad 0xDEADBEEFCAFEBABE
    .quad 0x1234567890ABCDEF
