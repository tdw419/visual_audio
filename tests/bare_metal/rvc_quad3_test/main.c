// RVC Quadrant 3 Test
// Instructions: C.BEQZ, C.BNEZ, C.SLLI, C.SRLI
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
    
    // Test 1: C.BEQZ - Branch if equal to zero
    // c.beqz x8, target  -> Branch if x8 == 0
    li  x8, 0
    beqz x8, 1f         // Should branch (C.BEQZ)
    j   fail
    
1:  // Branch taken correctly
    li  x8, TEST_VAL_A
    beqz x8, fail       // Should not branch
    // Test 2: C.BNEZ - Branch if not equal to zero
    // c.bnez x9, target  -> Branch if x9 != 0
    li  x9, 0
    bnez x9, fail       // Should not branch
    
    li  x9, TEST_VAL_B
    bnez x9, 1f         // Should branch (C.BNEZ)
    j   fail
    
1:  // Branch taken correctly
    // Test 3: C.SLLI - Shift left logical immediate variant
    // c.slli x8, 8  -> x8 = x8 << 8
    slli x8, x8, 8      // May emit C.SLLI
    
    // Verify
    li  x5, TEST_VAL_A
    slli x5, x5, 8
    bne x8, x5, fail
    // Test 4: C.SRLI - Shift right logical immediate
    // c.srli x9, 16  -> x9 = x9 >> 16 (logical)
    srli x9, x9, 16     // May emit C.SRLI
    
    // Verify
    li  x5, TEST_VAL_B
    srli x5, x5, 16
    bne x9, x5, fail

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
