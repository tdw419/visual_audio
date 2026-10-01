# Environment identity — read this first

**If your working directory is `/mnt/zion/projects/visual_audio`, you are
running *inside* the V5 guest VM itself** (the in-guest Claude Code CLI
described in `V5_VM_DEV_ENVIRONMENT.md`), not on the host. The host's copy of
this repo lives at a *different* path (`~/projects/zion/projects/visual_audio`,
no `/mnt/zion` prefix) — `/mnt/zion` only exists as a mount point inside the
guest.

Quick self-check if unsure:
```bash
hostname                  # "ubuntu" = you're in the guest
systemd-detect-virt        # "kvm" = you're in a VM (host would print "none")
ls /dev/dri /dev/input     # present directly = you're in the guest with real device access
```

**Do not run `boot_v5_vm.sh` or any `qemu-system-x86_64` command from in
here to "start V5"** — you are already inside it. Launching another QEMU
instance against `ubuntu-desktop-v5.raw` while this live session is running
*from that same disk file* means two OS instances writing to one raw disk
concurrently — this caused real EXT4 corruption (aborted journal, remount
read-only) on 2026-08-24. If a task seems to need booting or rebooting V5,
that has to happen from the **host** session, not from here.

See `V5_VM_DEV_ENVIRONMENT.md` for the full V4/V5 setup, the shared
`/mnt/zion` 9p folder, and how host vs. guest sessions are meant to divide work.

# Verification — always use `.venv`, never bare `python3`

This repo's canonical interpreter is `.venv/bin/python` (`.venv/bin/pytest`
for the suite), not the system `python3`. They differ (as of 2026-09-25:
`.venv` is 3.11.14, system is 3.12.3) and that difference is not cosmetic —
system Python's user-site `pytest-asyncio` emits a deprecation warning on
stderr that can get picked up by last-line error-truncation logic (e.g.
`GlyphL1Shell._run_python_proc` in `experiments/glyph_l1_shell.py`) and
produce a false failure that does not reproduce under `.venv`. This already
cost one session a false "regression" report (2026-09-25,
`test_bk25_stage_workbench.py`). Always run tests and any ad hoc
verification via `.venv/bin/python` / `.venv/bin/pytest`, not bare
`python3`/`pytest`.
