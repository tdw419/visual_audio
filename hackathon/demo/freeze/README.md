# Freeze: demo baseline (h1)

This directory freezes the demo boot baseline: one command runs a bounded
Alpine GPU boot smoke and proves the canonical kernel still brings up banner +
SMP on the GPU-native RISC-V machine.

## Run the smoke (one command)

```bash
hackathon/demo/freeze/BOOT_SMOKE.sh
# BOOT_SMOKE PASS: kernel banner + SMP up (/tmp/hackathon_boot_smoke.XXXX.log)
```

~90s wall at the default 20M steps. Exit 0 = gate green; anything else = RED.
Override knobs (env): `BOOT_SMOKE_WORKTREE`, `BOOT_SMOKE_MAX_STEPS`,
`BOOT_SMOKE_TIMEOUT` (default 600s hard cap). No knob here authorizes the full
boot — see the warning below.

## What this freezes

- **Boot oracle**: the verified 1.4B-step Alpine GPU boot documented in
  `HACKATHON_DEMO_PREVERIFY_2026-10-20.md` (repo root): fresh checkout at
  worktree d77b9af4 reproduced `ALPINE_GPU_BOOT_RECEIPT.md` end to end —
  identical Linux build string, SBI v3.0, SMP bring-up, VFS panic at the
  block-device boundary.
- **Canonical kernel asset**:
  `~/zion/apps/linux/alpine/alpine-riscv64.lnx.bin`
  (67,112,960 bytes, md5 `0cad7ccf7111eef3c0bc1e903b947001`).
  `BOOT_SMOKE.sh` verifies this md5 before every run and refuses to smoke on
  mismatch.

## Symlink pattern (fresh checkouts)

`boot_images/` assets are **gitignored** — the kernel is NOT in git. Recreate
it with mkdir + symlink (the script does this for its own worktree):

```bash
mkdir -p boot_images
ln -s ~/zion/apps/linux/alpine/alpine-riscv64.lnx.bin \
      boot_images/alpine_riscv64.lnx.bin
```

Other runtime deps (from the PREVERIFY setup notes): OpenSBI at
`/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin` (system package), and
the repo `venv/bin/python` (wgpu 0.32.0; system python3 has no wgpu).

## HARD LIMIT — full boot is a manual day-marker

The full 1.4B-step boot (~35 min) is run **manually only** — never from lane
verify, never by raising `BOOT_SMOKE_MAX_STEPS`. The smoke (20M steps, ~90s)
proves banner + SMP; it does NOT prove the full boot reaches the VFS-panic
milestone. That claim lives in the PREVERIFY receipt, re-confirmed by hand on
kickoff day.
