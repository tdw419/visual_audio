# MULTI_SEAT_RECEIPT — Two Seats, One Snapshot, One GPU (2026-11-02)

**Claim (measured):** two independent Linux sessions on one RTX 5090,
both restored from the SAME master machine-state snapshot, executing
concurrently with zero state leakage between seats.

This is the N=2 proof of the game-server thesis in
`GAME_SERVER_OS_CONCEPT.md`: provisioning a new user session is a
snapshot restore, not an OS installation.

## Invocation (reproducible)

```
GPU_POWER=high python tools/gpu_shell_multi_seat.py \
    --kernel   /tmp/h12/alpine_shell.lnx.bin \
    --snapshot /tmp/h12/shell_prompt_snapshot.npz \
    --seats 2 --outdir /tmp/h12_multiseat
```

Two `gpu_shell_live.py` processes launch concurrently. Each restores the
identical 18.5 MB snapshot (six buffers: memory 64 MB, registers, state,
CSR, UART ring, TLB) into its own private GPU buffer set (VRAM per seat
not re-measured in this specific multi-seat run; single-process baseline
observed at 1,858 MiB via nvidia-smi) and runs its own scripted command
stream at the prompt.

## Result: PASS — all_isolated: true

| Metric | Seat 1 (Alice) | Seat 2 (Bob) |
|---|---|---|
| exit code | 0 | 0 |
| steps | 83,100,000 | 82,400,000 |
| wall (concurrent) | 392.9 s | 392.9 s |
| saw own marker (output line) | yes | yes |
| leaked foreign markers | 0 | 0 |

Verbatim serial evidence:

```
# Seat 1 (Alice):
cat /seat1.txt
User 1: Alice
ls /
bin  init  newroot  root  seat1.txt  var  dev  lib  note.txt  run  sys ...

# Seat 2 (Bob):
cat /seat2.txt
User 2: Bob
ls /
bin  init  newroot  root  seat2.txt  var  dev  lib  note.txt  run  sys ...
```

Each seat's `ls /` lists ONLY its own seat file. Alice's full serial log
contains zero occurrences of `User 2`; Bob's contains zero of `User 1`.
Logs: `/tmp/h12_multiseat/seat{1,2}_*.log`. The step and wall numbers in
the table above are machine-readable provenance from
`/tmp/h12_multiseat/summary.json` (written by the orchestrator at run
end); the isolation verdict is the corrected verifier's output, also
recorded there.

## Honesty notes

1. **Concurrency is not free:** 392.9 s wall per seat vs 124 s for a
   single seat — the two seats share one GPU adapter and are
   dispatch-latency-bound. The claim proven here is isolation and
   provisioning (restore, not boot), not per-seat throughput at N=2.
2. **First run was a false positive, caught by reading the raw serial:**
   the minimal initramfs has no `/tmp` (`can't create /tmp/seat.txt:
   nonexistent directory`), and the original verifier matched the marker
   in the command *echo* rather than the file *content*. Fixed: seat
   files now live at `/seatN.txt` and verification parses standalone
   output lines only (`[live] sending:` and terminal-echo lines
   excluded). The receipted PASS is from the corrected verifier.
3. **Scope:** two host processes, each owning private buffer sets on one
   WebGPU device/adapter. The in-shader N-hart scheduler and shared
   compositor remain staked future work (ROADMAP post-deadline horizon).
4. **Auditor hardening (2026-11-02):** the adversarial receipt auditor
   (`factory audit`, Meta Model API) flagged the VRAM figure and the
   summary numbers as un-cited provenance. This section was hardened in
   response — the feedback loop (build auditor → auditor flags own
   team's receipt → provenance hardened) is itself part of the record.

## Verification gate added

`tools/gpu_shell_multi_seat.py` exits non-zero unless every seat shows
exit 0, its own marker as a parsed output line, and no foreign markers.
