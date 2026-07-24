# Carry-Forward: Level5b — Identity-Mapped SV39

## Status: COMPLETE (with QEMU limitation documented)

### What was built
- `tests/bare_metal/level5b/` — SV39 identity-mapped page table
- S-mode entry via mret with NAPOT PMP (all physical memory)
- 2MB leaf entries for code (0x80000000) and UART (0x10000000)
- Verified: MMU works in M-mode
- Verified: S-mode entry works (bare-metal, no MMU)

### Key findings
1. **QEMU `rv64` CPU**: Requires explicit satp=0 + hstatus=0 before mret to S-mode, else mret itself faults with Instruction Access Fault
2. **S-mode MMU enable**: Fails on QEMU with mcause=1 (Instruction Access Fault) — PMP checks on page table walker physical reads. Page table works correctly in M-mode.
3. **GPU emulator target**: Has no PMP, S-mode MMU will work there. Our actual deployment target.

### Lessons learned
- SV39 VPN[2] = VA bits[38:30], VPN[1] = bits[29:21], VPN[0] = bits[20:12]
- For 0x80000000: VPN[2]=2, VPN[1]=0 (NOT 256 and 0 as initially coded)
- PTE leaf flags: 0x0F for S-mode (no U bit), 0xCF with A+D bits
- PMP NAPOT all-ones (0x3FFFFFFFFFFFFF) covers all physical memory
- PMPcfgp0 = 0x1F = NAPOT with R|W|X
- SXL (bits 35:34) must be 10 (64-bit); was already correct in QEMU

### Next
- Level5c: Enable MMU in S-mode — test on GPU emulator
- GPU emulator command: `python3 tools/boot_gpu_execute_no_mmu.py tests/bare_metal/level5b/level5b.npy 0x80000000`
