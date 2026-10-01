# RECEIPT_BM801_WRITE_VERIFY — the read-back discipline, as a tool

**Date:** 2026-09-21T21:04Z. Follows `RECEIPT_BM801_CHANNEL.md` on the same row:
`TASK_BM801` is blocked on a box Jericho designates, and both of its host-side
prerequisites were prose. This one was the sentence —

> after `dd` + sync, read the physical medium back and `cmp` against the
> gate-validated `.raw` BEFORE any boot attempt. Never boot an unverified medium.

— which had no implementation anywhere in the ladder.

## Files

| file | what it is |
|---|---|
| `rung8/bm801_write_verify.py` | `dd conv=fsync` + `sync`, then a byte-exact read-back against the source; refuses a block-device target without `--device`, and a target inside the repository tree without `--allow-in-repo` |
| `rung8/run_bm801_write_verify_gate.py` | seven legs, each predicting before it measures, five of them breaking the medium on purpose |

Exit codes are part of the contract: **0** verified, **1** MISMATCH (never boot),
**2** refused before writing, **3** tool failure. A caller that treats nonzero as
one answer has thrown the discipline away.

## Why the refusals come first

The dangerous failure of a bake tool is not a wrong verdict, it is writing
somewhere it should not. On this box the live pixel VM's only disk is
`ubuntu_desktop_pxc1_v3_selfhost/`, a file inside the repository, so leg 0b
points the tool at a path under git and requires `rc=2` **and that the path was
never created**. Leg 0a points it at a real block device and requires the guard's
own refusal, which is distinguishable because this user cannot write the device
at all: `os.access(W_OK)=False`, so had the open come before the check the error
would have been `PermissionError` from the kernel rather than `REFUSE-BLOCK-DEVICE`
from the tool. The leg names that reasoning in its output, and would go RED on a
box where `W_OK` is true instead of quietly weakening.

## Gate output, verbatim

```
# bm801 write-verify gate | run dir /tmp/bm801_wv.s4hdnezm | source gate-validated.raw (4194304 B)
--> 0a block-refusal     predicts: refusal by name, before any open, on a device this user could not write anyway -- so a PermissionError would prove the guard lost
PASS 0a block-refusal       /dev/loop0 rc=2 guard-fired=True os.access(W_OK)=False (the refusal is the tool talking, not the kernel)
--> 0b in-repo-refusal   predicts: rc=2, REFUSE-IN-REPO, and the path never created
PASS 0b in-repo-refusal     rc=2 refused=True target-created=False
--> 1 clean-bake         predicts: rc=0, VERIFIED, source and target digests equal
PASS 1 clean-bake           rc=0 ok=True size=4194304 sha=cc89d69cf3bf...
--> 2 late-flip          predicts: rc=1 and first_mismatch == the offset that was flipped
PASS 2 late-flip            rc=1 reported=2097153 flipped=2097153 n=1
--> 3 truncated          predicts: rc=1, caught by length, differing bytes counted to the end
PASS 3 truncated            rc=1 sizes 4194304/4190208 first_mismatch=4190208
--> 4 short-write        predicts: rc=1; a bake that wrote 1 MiB of 4 must not be called verified
PASS 4 short-write          rc=1 target_size=1048576
--> 5 after-sync-mutation predicts: rc=1 with the exact offset: dd said done, the read-back says otherwise, which is the whole point of the discipline
PASS 5 after-sync-mutation  rc=1 reported=4194297 expected=4194297
--> 6 real-medium        predicts: report-only: bake+cmp a ladder .raw; SKIP when the tree has no such artifact, so this gate still runs from the commit alone
INFO 6 real-medium            ../rung5/rung5_medium.raw 67108864 B rc=0 ok=True sha=028336884d0a...
RESULT 7/7 scored legs pass
```

rc=0. Leg 6 exercised the whole discipline on a **real** 67,108,864-byte
gate-validated ladder medium (`rung5/rung5_medium.raw`, read as a source only)
into a file standing in for a stick: bake, sync, read back, byte-exact, digest
`028336884d0a…`.

Two of the three bugs found while building this are worth keeping in the record,
because both are the class this lane audits:

- `--short-bytes 1048576` with `bs=4M` wrote **4 MiB** — `dd count=` counts
  *blocks*, so a "partial write" fault was silently a complete one, and the leg
  that exists to catch power-loss partial writes would have caught nothing.
  Short bakes now use `bs=4096`.
- The byte-flip helper opened the target `O_WRONLY` and then `pread` — `EBADF`.
  It was a bug in the *test*, and it surfaced as a crash rather than a pass,
  which is the only reason it was noticed.

## Re-run from the commit alone

Both BM801 gates were then exported (`git archive HEAD tools/bare_metal_poc | tar -x`) into a
directory outside every git tree and run there. The beacon gate still holds **7/7, rc=0**.
The write-verify gate scores **6/6 with two legs SKIP**, and both skips are the honest
answer rather than a pass wearing a costume: leg 6 skips because the real medium is not
tracked, which is what the leg predicted, and leg 0b skips because an exported copy is not
inside a repository, so there is no repo for the guard to refuse. 0b going RED there would
have been a gate that only passes in the one tree it was written in.

## What this does not cover

- **A lie from firmware is out of reach here.** Leg 5 emulates a target that
  changed after `sync` returned, by mutating it through a descriptor opened
  beforehand. Real "completion reported falsely" happens below the file layer;
  what the emulation buys is the guarantee that *any* divergence between source
  and medium is caught at its exact offset, whatever produced it.
- The read-back compares what the same host can see. A device with a write cache
  that flushes later still passes leg 1 while holding unflushed data — that is
  precisely the measured-outcome-per-box territory in ROADMAP's next bullet, and
  no host-side tool retires it.
- No boot was attempted with any medium produced here, verified or not.
