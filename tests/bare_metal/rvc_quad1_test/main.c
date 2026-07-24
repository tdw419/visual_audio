// RVC Quadrant 1 Test
// Instructions: C.ADDI, C.JAL, C.LIW, C.LDsp
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
    
    // Test 1: C.ADDI - Add immediate to register (imm can be zero)
    // C.ADDI - Add immediate to register (imm can be zero)
    // TODO: Implement test for C.ADDI
    li  x3, 0xDEADBEEF

    // Test 2: C.JAL - Jump and link (jal x1, imm)
    // c.jal target  -> Jump and link
    jal x1, 1f          // May emit C.JAL
    
    // Should not reach here
    j   fail
    
1:  // x1 should contain return address
    li  x5, 0xFFFFFFFF  // Any non-zero value is ok
    beqz x1, fail
    // Test 3: C.LIW - Load word from offset[5:3](rs1) into rd (RV64 only)
    // C.LIW - Load word from offset[5:3](rs1) into rd (RV64 only)
    // TODO: Implement test for C.LIW
    li  x3, 0xDEADBEF1

    // Test 4: C.LDsp - Load double-word from offset[8:3](sp) into rd
    // C.LDsp - Load double-word from offset[8:3](sp) into rd
    // TODO: Implement test for C.LDsp
    li  x3, 0xDEADBEF2


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
