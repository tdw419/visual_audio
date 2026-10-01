# XV6 Boot Regression Test Status

## Current Status: **KNOWN FAILURE** (2026-08-14)

### Symptoms
The xv6 kernel (`boot_images/xv6.img`) boots but gets stuck in a tight PC loop:
- **PC cycling**: 0x80000c7c → 0x80000c78 → 0x80000c7e → repeat
- **RA stuck**: 0x80000a2a
- **No interrupts**: timer_irq=0, total_irq=0
- **Execution**: 200M instructions per dispatch, infinite loop

### Root Cause
The `boot_images/xv6.img` kernel is compiled with RVC (RISC-V Compressed Instructions):
```
$ file boot_images/xv6.img
boot_images/xv6.img: ELF 64-bit LSB executable, UCB RISC-V, RVC, double-float ABI
```

The current GPU RISC-V emulator (`RISCV_CPU_MMU.wgsl`) appears to have incomplete or buggy RVC instruction support, causing it to misinterpret 16-bit compressed instructions at the PC cycling address.

### Evidence
```
Iter     0: PC=0x0000000080000c7c, RA=0x0000000080000a2a, instr=2000000, timer_irq=0
Iter     1: PC=0x0000000080000c78, RA=0x0000000080000a2a, instr=4000000, timer_irq=0
Iter     2: PC=0x0000000080000c7e, RA=0x0000000080000a2a, instr=6000000, timer_irq=0
Iter     3: PC=0x0000000080000c7c, RA=0x0000000080000a2a, instr=8000000, timer_irq=0
...
```

### Solution Path
According to `CARRY_FORWARD_LEVEL6.md`:
1. Build xv6 **without RVC extension** using the correct toolchain:
   ```sh
   git clone --depth 1 https://github.com/mit-pdos/xv6-riscv /tmp/xv6
   make -C /tmp/xv6 TOOLPREFIX=riscv64-unknown-elf- kernel/kernel fs.img
   ```

2. The non-RVC kernel lives at `/tmp/xv6-riscv/kernel/kernel` and should be used for regression testing.

3. **DO NOT** use `boot_images/xv6.img` for GPU emulator testing - it's an RVC-enabled build from an older toolchain.

### Test Harness Status
The regression test (`tests/test_xv6_boot_regression.py`) has fallback logic:
- **Primary**: `/tmp/xv6-riscv/kernel/kernel` (non-RVC, correct)
- **Fallback**: `boot_images/xv6.img` (RVC, known broken)

Once the non-RVC kernel is built, the test should pass and become a valid regression guard.

### Next Steps
1. Build xv6 without RVC following the instructions above
2. Run the regression test to verify the fix
3. If it passes, commit the test to CI
4. Consider adding RVC support to the GPU emulator (future work) or explicitly reject RVC binaries

---

**Last Updated**: 2026-08-14
**Issue Type**: Incompatible Toolchain (RVC instruction set not fully supported)
**Severity**: Blocks regression testing