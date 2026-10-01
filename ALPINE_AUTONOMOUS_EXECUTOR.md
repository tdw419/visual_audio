# Autonomous Alpine RV64 Boot Executor

## Overview

This autonomous program fixes the RV64 emulator so it boots Alpine Linux successfully. The emulator currently stalls at ~35M steps during initramfs unpack.

## Quick Start

### Manual Execution

```bash
cd /home/jericho/projects/zion/projects/visual_audio
python3 autonomous_alpine_boot.py
```

### Cron Job (Automated)

A cron job is scheduled to run every 6 hours. It will:
- Run the autonomous boot executor
- Iterate up to 50 times applying fixes
- Report success or failure

To check cron job status:
```bash
hermes cron list
```

To run immediately:
```bash
hermes cron run 681ee1661437
```

## How It Works

The executor follows a 4-phase autonomous loop:

### Phase 1: Boot Test
- Runs Alpine to identify current stall point
- Tracks steps executed and boot status
- Detects if Alpine has booted successfully

### Phase 2: State Capture
- Captures detailed CSR state (scause, stval, sepc, satp)
- Analyzes stall mode from CSRs:
  - `load_page_fault` (code 13)
  - `store_page_fault` (code 15)
  - `instruction_page_fault` (code 12)
  - `timer_loop` (interrupt code 5)
  - `unknown`

### Phase 3: Apply Fixes
Applies targeted fixes based on stall mode:

#### Permission Fix (for page faults)
- Adds U-bit/SUM checks to `check_perm()` in SPATIAL_RV64I.wgsl
- Ensures S-mode properly validates user page access
- Backs up original shader before modification

#### TLB Fix (for timer loops)
- Improves `sfence.vma()` implementation
- Supports single-entry invalidation (not just all)
- Adds memory barriers for proper synchronization

### Phase 4: Report Progress
- Saves state to `alpine_boot_state.json`
- Tracks iterations, fixes applied, and progress
- Detects when no progress is made (3 iterations without improvement)

## Known Issues Being Fixed

From STATUS_RV64I_STALL.md:

1. **Permission checks missing U-bit/SUM** (line 738 in SPATIAL_RV64I.wgsl)
   - Current `check_perm()` only checks R/W/X bits
   - Missing validation for S-mode accessing user pages

2. **TLB invalidation timing**
   - `sfence.vma` calls `tlb_invalidate_all()` but may be too coarse
   - Stale TLB entries may persist after PTE updates

3. **Direct-mapped TLB collisions**
   - 256 entries for 27-bit VPN space
   - Multiple VPNs map to same TLB entry
   - Can cause wrong translations during initramfs unpack

## State File

After each iteration, state is saved to `alpine_boot_state.json`:

```json
{
  "state": {
    "iteration": 5,
    "last_working_step": 35000000,
    "stall_step": 0,
    "csr_state": {...},
    "tlb_stats": {...},
    "applied_fixes": ["permission_fix", "tlb_fix"],
    "boot_log": [...]
  },
  "results": [
    {
      "iteration": 1,
      "status": "stalled",
      "steps": 35000000,
      "stall_mode": "store_page_fault",
      "fixes": [],
      "time": 45.2
    },
    ...
  ],
  "timestamp": "2026-08-27 12:34:56"
}
```

## Success Criteria

Alpine is considered booted when output contains:
- `login:` prompt
- `shell` prompt
- `#` command prompt

The executor will:
- Report success with total iterations
- List all fixes applied
- Provide verification commands

## Safety Limits

- Max iterations: 50
- Timeout per boot: 2 hours
- Auto-detects when no progress is made (3 iterations stalled)
- Backs up original WGSL shader before modifications

## Manual Intervention

If autonomous executor exhausts all fixes:

1. Check state file:
   ```bash
   cat alpine_boot_state.json | jq '.results[-1]'
   ```

2. Review WGSL shader changes:
   ```bash
   diff -u tools/SPATIAL_RV64I.wgsl.backup tools/SPATIAL_RV64I.wgsl
   ```

3. Manual boot test:
   ```bash
   python3 standalone_alpine_boot.py --max-steps 100000000
   ```

4. Capture detailed state:
   ```bash
   python3 debug_csr_state.py --capture
   ```

## Related Files

- `autonomous_alpine_boot.py` - Main autonomous executor
- `standalone_alpine_boot.py` - Boot test harness
- `debug_csr_state.py` - CSR state capture tool
- `tools/SPATIAL_RV64I.wgsl` - GPU shader with MMU implementation
- `STATUS_RV64I_STALL.md` - Detailed stall investigation
- `INVESTIGATION_STATUS.md` - EFAULT investigation notes
- `pixel_emulator/ROADMAP.md` - RV64 implementation roadmap

## Verification

After successful boot, verify with:

```bash
# Check boot reached shell
python3 standalone_alpine_boot.py --max-steps 200000000 | grep -E "(login:|#|shell)"

# Verify kernel messages
python3 standalone_alpine_boot.py --max-steps 200000000 | grep -E "(Alpine Linux|Linux version)"

# Check for no errors
python3 standalone_alpine_boot.py --max-steps 200000000 | grep -iE "(panic|error)" | head -20
```

## Cron Job Details

Job ID: `681ee1661437`
Name: Autonomous Alpine RV64 Boot Fixer
Schedule: Every 6 hours
Repeat: Forever
Deliver: All channels

Created: 2026-08-27
Next run: ~6 hours from creation