# GUEST_PROBE_RECEIPT — 2026-11-02

The GPU Linux substrate as a factory verification oracle. `tools/guest_probe.py`
restores the snapshot seat, executes probe commands INSIDE the guest, and
checks the guest's own answers against pinned ground truth. Host Python and
guest busybox share no allocator, compiler, or libc — this is the
zero-shared-assumptions oracle.

## Pinned ground truth

```
/note.txt sha256 (guest-computed, busybox sha256sum):
a265e62cdc95e5855b1d0d687fb70506703138edf09a2fb46d86f47e35cb65be
```

## Runs (independent restores, same snapshot)

| Check | Run 1 (discover) | Run 2 (gate, --expect-sha) |
|---|---|---|
| guest exit code | 0 | 0 |
| /proc/uptime read twice | yes | yes |
| guest time advances | 100.56 → 103.11 | yes |
| guest computed sha | a265e62c… | a265e62c… |
| matches pinned truth | (established pin) | **true** |
| wall seconds | 199.7 | 198.3 |

Run 2's `GUEST_PROBE_SUMMARY` (machine-readable):
`/tmp/guest_probe/summary.json`; raw serial:
`/tmp/guest_probe/guest_probe_serial.log`.

## Checks enforced (exit 0 requires all)

- guest process exits 0
- /proc/uptime readable twice, second strictly greater than first
  (guest scheduler advancing, not a frozen image)
- guest computed a sha256 for /note.txt
- guest sha equals the pinned constant (when --expect-sha supplied)

## Guardrails (working as designed)

- Refuses to launch when GPU utilization > 5% unless --force; a parked
  idle session (0% util) does not block the probe.
- ~2 minutes per run (snapshot restore): milestone gates only, never
  routine cron ticks. Scripted commands only until Rung C (seat I/O
  router).

## Dogfood thesis

No GPU-lane rung should land without the substrate signing the receipt.
The probe makes that a mechanical gate: the guest kernel itself is the
witness, and its arithmetic is checked against a host-pinned constant it
cannot see.
