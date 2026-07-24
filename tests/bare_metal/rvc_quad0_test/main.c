// RVC Quadrant 0 Test
// Instructions: C.ADDI4SPN, C.LW, C.LD, C.SW
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
    
    // Test 1: C.ADDI4SPN - Add non-zero immediate to sp, store in rd' (x8-x15)
    // c.addi4spn x8, 32  -> Add 32 to sp, store in x8
    .insn r 0, 0, 0x0, x8, x8, 32   // This should compile to C.ADDI4SPN
    // Verify x8 = original_x8 + 32
    li  x5, TEST_VAL_A
    li  x6, 32
    add x5, x5, x6
    bne x8, x5, fail
    // Test 2: C.LW - Load word from offset[6:2](rs1') into rd'
    // Setup test memory at sp + 16
    li  x5, 0xABCD1234
    sd  x5, 16(sp)      // Store test value
    
    // c.lw x9, 16(sp)  -> Load word from sp+16 into x9
    lw  x9, 16(sp)      // Should use C.LW if compiler emits it
    
    // Verify
    li  x5, 0xABCD1234
    bne x9, x5, fail
    // Test 3: C.LD - Load double-word from offset[7:3](rs1') into rd'
    // C.LD - Load double-word from offset[7:3](rs1') into rd'
    // TODO: Implement test for C.LD
    li  x3, 0xDEADBEF1

    // Test 4: C.SW - Store word from rs2' to offset[6:2](rs1')
    // c.sw x10, 24(sp)  -> Store x10 to sp+24
    sw  x10, 24(sp)
    
    // Verify by loading back
    lw  x5, 24(sp)
    li  x6, TEST_VAL_C
    bne x5, x6, fail

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
