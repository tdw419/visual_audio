# Carry Forward — Level 6 (U-mode) + xv6 Interactive Shell

## Status

| Component | Status | Verified |
|-----------|--------|----------|
| 6a (sret to U-mode + ecall delegation) | ✅ | QEMU + GPU emulator |
| 6b (SUM/MXR fault isolation) | ✅ | QEMU + GPU emulator |
| 6c (U-mode page fault via stval) | ❌ Not started | Deferred |
| 7a (SBI timer relay) | ✅ | QEMU + GPU emulator |
| **xv6 boot to shell** | ✅ | **GPU emulator — shell prompt confirmed** |
| **Interactive command injection** | ✅ | **`ls` injected, 23-file listing returned** |
| **Console (console=3) device** | ✅ | Appears in ls output |
| **VirtIO disk I/O** | ✅ | fs.img read successfully |
| **Timer interrupts (50+)** | ✅ | Flow through SBI relay |

## Key Facts

- **Kernel binary**: `/tmp/xv6-riscv/kernel/kernel` — compiled with `-march=rv64ima_zicsr_zifencei` (no RVC)
- **Do NOT use** `boot_images/xv6.img` — that's an older RVC-enabled build from a different toolchain
- **fs.img** at `/tmp/xv6-riscv/fs.img`, loaded at physical address 0x81000000
- **Inject_command()** works: writes to UART input buffer, resets `uart_input_ptr=0`, sets `uart_input_len`

## xv6 Boot + Interactive I/O Verified Commands

```bash
# Quick diagnostic (15 dispatches)
python3 tools/diagnose_xv6_boot2.py

# Full test with ls injection
python3 tools/test_xv6_ls.py
# Expect: boots to $ prompt, injects ls, 23 files listed, returns to $
```

## Level 6a Architecture

The page table uses 4 pages (16KB of BSS) for a 4-tier SV39 layout:

| Page | Role | Content |
|------|------|---------|
| 0 | Root (VPN[2]) | [0]->user_mid, [1..3]->code_mid |
| 1 | Code mid (VPN[1]) | S-mode mappings: code@0x80000000 U=0, UART@0x10000000 U=0 |
| 2 | User mid (VPN[1]) | U-mode mappings: [0]->L3 branch, [128]->UART@0x10000000 U=1 |
| 3 | User L3 (VPN[0]) | 4KB leaf: [16]->utramp page U=1 |

User code lives in `.utext` section placed at a 4KB boundary (0x80001000) in the ELF. The page table maps VA 0x00010000→PA 0x80001000 with U=1,RWX. UART is accessed at 0x10000000 through user_mid[128] (2MB leaf, U=1).

The trampoline (`u_trampoline()`) writes 'U\n' to UART via 0x10000000, stores 42 in a7, and ecalls. medeleg[8]=1 delegates ECALL_U to S-mode stvec.

## Key Patterns

**M-mode → S-mode via mret:**
- Set MPP=S in mstatus, mepc=&s_mode_main
- mret drops to S-mode with SV39 active
- M-mode bypassed translate_va entirely (stall bug from 5b final fix)

**S-mode → U-mode via sret:**
- Clear SPP in sstatus, set sepc=USER_CODE_VA (0x00010000)
- Set SPIE=1 so SIE auto-enables when sret restores
- sret drops to U-mode; hardware lowers privilege, starts translation at sepc

**U-mode → S-mode via ecall:**
- medeleg[8]=1 routes ECALL_U to S-mode stvec
- Handler reads a7 for caller cookie, advances sepc+4, srets back
- S-mode must adjust sepc manually (ecall doesn't increment PC)

## Permission Enforcement (in translate_va)

Added `check_pte_permission()` in tools/RISCV_CPU_MMU.wgsl:

1. **U-bit rule**: U-mode cannot access pages with PTE_U=0 → page fault
2. **SUM rule**: S-mode accessing U=1 pages: allowed only for data access (not fetch) when mstatus.SUM=1
3. **RWX rules**: Fetch needs X=1, Store needs W=1, Load needs R=1 or (X=1 && MXR=1)
4. **AME**: Checked as W-only (W bit), not R+W (approximation — acceptable)

## Next Steps (Options)

1. **Autonomous shell driving** — Wire `boot_xv6_gpu.py --autonomous` to run a loop of Ollama-chosen commands
2. **Multiple commands** — Test `cat`, `echo`, `wc`, `grep` for pipe/redirection
3. **usertests** — Run the full `usertests` suite on GPU (stress-test fork/exec/sbrk)
4. **RVC support** — Add 16-bit compressed instruction decode for running arbitrary RISC-V binaries
