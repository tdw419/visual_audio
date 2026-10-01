# RV64I Stall Investigation - UPDATED (2026-08-25 20:30)

**Status**: Root cause identified - **No OpenSBI firmware loaded**

## Critical Bug Fixed (Validated)

**Problem**: `spatial_rv64i_cpu.py::read_csr()` was using `buffer_offset=addr * 8` instead of actual RiscvCPU struct field offsets from `CSR_OFFSETS` mapping.

**Impact**: All earlier `mcause`/`scause` readings were corrupted. The "page fault loop" diagnosis was based on garbage data.

**Fix**: Added CSR address → struct offset mapping table in `read_csr()`; verified in `csr_offsets.py`.

## Root Cause Identified

**GPU Boot Configuration:**
- `boot_alpine_lnx_gpu.py` loads bare PE/COFF kernel at 0x200000
- Sets up SV39 page tables
- **No OpenSBI firmware loaded**
- Jumps directly to kernel entry point in S-mode

**What Real RISC-V Boot Expects:**
1. OpenSBI runs first in M-mode
2. OpenSBI initializes:
   - `mtvec` (M-mode trap vector)
   - Hardware (CLINT timer, UART, etc.)
   - S-mode environment via `mstatus.MPP=S`, `mret`
3. Kernel runs in S-mode with OpenSBI SBI services available

**What GPU Boot Does:**
- Loads kernel **without OpenSBI**
- Sets `mstatus.MPP=S` but no `mtvec` setup
- Kernel executes in S-mode
- Kernel makes SBI `ecall` → traps to M-mode
- **mtvec=0 in M-mode** → **CPU halts** (WGSL line 512: `state.halted = 1u`)

**This Explains:**
- mcause=0x3 (breakpoint/exception) - kernel trapping to M-mode for SBI services
- scause=0x0 - no S-mode traps
- PCs in kernel text - kernel executing normally until first SBI call
- UART output stops - SBI console_putchar expects OpenSBI handler

## Signals After Fix (Verified Traces)

```
mcause: 0x3                  (exception in M-mode)
scause: 0x0                  (no active S-mode trap)
PC: 0xffffffff8037dd94       (kernel text)
PC: 0xffffffff8038dce8       (kernel text)
TLB hit rate: 98.8%          (healthy)
```

## RETRACTED Hypotheses

**RETRACTED**: "CPU crashed by jumping to NULL"
- WGSL semantics: CPU halts if mtvec=0, doesn't jump to NULL
- No NULL PC found in post-fix traces

**RETRACTED**: "Page fault loop"
- Based on corrupted mcause/scause readings
- Real signal is breakpoint/exception, not page faults

## Next Steps

**Option 1: Load OpenSBI Firmware**
1. Find or build OpenSBI binary for Alpine kernel
2. Load OpenSBI at M-mode entry point
3. Configure OpenSBI to transition to kernel
4. Test with OpenSBI + kernel

**Option 2: M-Mode Direct Kernel Boot**
1. Check if kernel can be built for direct M-mode boot
2. Skip OpenSBI layer entirely
3. Initialize hardware directly in kernel

**Option 3: SBI Service Stub**
1. Implement minimal SBI service handlers in WGSL
2. Handle console_putchar, set_timer, legacy SBI calls
3. Allow kernel to boot with GPU-native SBI

## Files Modified

- `tools/spatial_rv64i_cpu.py` - Fixed `read_csr()` offset calculation
- `csr_offsets.py` - CSR offset mapping documentation (created)

## Related Constants (Verified)

```
SSTATUS_MASK = 0x122     (SIE=bit1, SPIE=bit5, SPP=bit8)
MSTATUS_TRAP_MASK = 0x1888 (MIE=bit3, MPIE=bit7, MPP=bits11-12)
~0xA0 clears MTIP (bit7) and STIP (bit5) in MIP register
```

## History

**2026-08-25 15:40**: CSR offset bug discovered and fixed. Investigation shifted from "fault loop" to "NULL PC crash."

**2026-08-25 20:30**: Root cause identified - OpenSBI firmware not loaded, kernel traps to M-mode with mtvec=0.