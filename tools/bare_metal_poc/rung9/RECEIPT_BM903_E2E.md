# RECEIPT — BM903 step 3: the end-to-end row gate (and the race it had to measure first)

Closes `.builder_queue/brief_bm903_e2e_pixel_boot.md` steps 2 and 3. Step 1's
gate is `rung9/run_bm903_step1.sh`; step 2 is recorded in
`rung9/RECEIPT_BM903_STEP2.md`. This file is the record for the row gate.

## Command and result

```bash
bash tools/bare_metal_poc/rung9/run_bm903_e2e.sh
```

Two consecutive clean runs, both green: `BM903 E2E TALLY: 42 pass, 0 red`
(runs 5 and 6). Every RED leg fired inside the same run that went green, as the
brief's RED-first requirement demands.

## Files (all inside the brief's declared scope, `rung9/`)

| file | role |
|---|---|
| `run_bm903_e2e.sh` | the row gate: S0 pins → S0b lane → S1 dual build → L1 → L1b → L2 → L3 → L4 → L5 → L6 → R1 |
| `bm903_anchor_boot.py` | boots a medium with no debugger, timestamps every checkpoint, exits non-zero if the anchor is not reached inside the budget |
| `bm903_norm_transcript.py` | the only normalizations a transcript may undergo (T1–T4), each counted and printed |
| `bm903_px_corrupt.py` | L6 fixture: flips ONE payload byte at its PXC1 medium offset and *predicts* the CRC the guest must compute |
| `bm903_tty_race.py` | the measurement behind L3/L4's attempt policy (below) |
| `bm903_lane.py` | boot-lane guard: refuses to start beside another bm903 qemu |
| `bm903_px_memcmp.py`, `bm903_dbg_*.py`, `bm903_time_to_prompt.py` | step-2 evidence probes, moved here from the repo `output/` directory because the brief scopes this row to `rung9/` ONLY |

Step 2's guest and host artifacts (`bm903_stage2_px.asm`, `bm903_px_layout.inc`,
`bm903_crc32tab.inc`, `bm903_pxcodec.py`, `bm903_mkimg_px.py`) and step 1's
(`bm903_stage2.asm`, `bm903_mkimg.py`, `bm903_capture.py`, `bm903_differ.py`,
`bm903_consts.py`, `BM903_FIELD_PLAN_ADDENDUM.md`) are unchanged by this gate
apart from `bm903_capture.py`'s optional `[medium] [prefix] [gdb_timeout]`
arguments, which default to step-1 behaviour.

## What each leg is allowed to prove

| leg | brief item | mechanism |
|---|---|---|
| S0 | input pins | sha256 of the 6 trusted inputs; `EXPECTED_CRC` == codec meta; the probes the gate needs exist |
| S0b | serialization | `bm903_lane.py` refuses to start beside any other bm903 qemu |
| S1 | build | both media from source; pixel sector count == layout (every plane chunk inside the file) |
| L1 | executed-vs-constructed | boot the PIXEL medium, `hbreak *0x100000`, differ vs the BM902 oracle, whitelist-only |
| L1b | cross-medium | px handoff dumps == step-1 contiguous-medium handoff dumps, byte-for-byte |
| L2 | registers | re-pin 26 load-bearing register values from the captured register json |
| L3 | serial anchor | plain boot (no debugger) reaches the pinned `tc@box` inside a named per-boot budget; step-1 medium as a live control |
| L4 | ×2 byte-identical | two anchor boots of the pixel medium: transcripts byte-identical after T1–T4; handoff dumps byte-identical strictly |
| L5 | RED | flip zp[0x244] outside every whitelist row → differ exits non-zero naming the offset; control flip of whitelisted 0x210 stays green |
| L6 | RED | corrupt ONE medium payload byte → CRC refusal in rung-4 format with host cross-check, no `HANDOFF BUILT`, no anchor, no gdb stop at `0x100000` |
| R1 | regression | `run_bm903_step1.sh` re-run inside the same gate |

## The thing that was actually flaky, and what it cost to find out

Run 3 of this gate was `40 pass, 2 red`: L3 and L4's second boot failed to reach
`tc@box` in 180 s — on the pixel medium, while the step-1 control booted green
in the same run at 11.0 s. The gate's own wording at that time asserted "an L3
RED is the pixel path, not the rig". **The data disproved that sentence, so the
sentence is gone.** Unpacking the initrd (`/tmp/bm903_initrd`, from
`../rung7/core.gz`, read-only) shows why the leg cannot be single-shot:

```
# /etc/inittab — both entries exec the SAME autologin:
tty1::respawn:/sbin/getty -nl /sbin/autologin  38400 tty1
ttyS0::respawn:/sbin/getty -nl /sbin/autologin 115200 ttyS0

# /sbin/autologin
if [ -f /var/log/autologin ] ; then exec /sbin/getty 38400 tty1
else touch /var/log/autologin ; exec login -f root ; fi
```

Whichever getty touches the flag file first owns `login -f root`, and `login`
names its own terminal in the syslog line that *both* outcomes print on serial:
`root login on 'ttyS0'` (the console gets the banner and `tc@box:~$`) or
`root login on 'tty1'` (the loser is re-execed onto **tty1 unconditionally**, so
serial never draws a prompt again). Measured with `bm903_tty_race.py`, one line
per boot:

| arm | boots | reached `tc@box` |
|---|---|---|
| pixel, 90 s budget | 3 (run aborted once the pattern was clear) | 1 |
| pixel, baseline device model | 8 + 8 | 5 + 5 |
| pixel, `-vga none` (kill the tty1 rival) | 8 | 6 |
| step-1 contiguous medium, baseline | 8 | 3 |

Three conclusions, each of which changed the gate:

1. **A longer budget does not rescue a lost boot.** A lost boot sits silent
   forever after the tty1 record; 90 s and 180 s both bought nothing. So
   `BOOT_BUDGET=180` on a single boot was the wrong shape of timeout.
2. **`-vga none` does not remove the rival** (6/8 — indistinguishable from
   baseline), because the guest's VT layer exists without a display adapter.
   The device model is not the lever.
3. **It is not the pixel medium's fault**: the step-1 medium loses the same race
   (3/8), and L1b already proves the two media hand the kernel byte-identical
   memory.

So L3 and L4 now share `boot_attempts`: up to `BOOT_ATTEMPTS=8` boots, each
under its own named `ATTEMPT_TIMEOUT=45` s — the same worst-case wall clock the
single 180 s boot had, and all of it nominal: a systematic failure pays it in
full and still goes RED, and every losing attempt is printed. What the leg
*requires* is unchanged: the pinned anchor string, on serial, inside a stated
timeout. Nothing was OR'd, nothing was relabelled as passing, and `tc@box` was
never re-chosen.

Finding the race also exposed a second, subtler bug — in the L4 normalizer:

* T4 cut "at the first `login[PID]` record", but run 4 showed both orders
  occurring (a boot that logged tty1 *before* the /etc/issue banner, and one that
  drew the banner first), so the cut position itself moved 129 B between two
  legitimate boots and L4 compared different amounts of transcript. Fixed by
  cutting at the **earliest** race-onset line (login record or banner) snapped
  back to the start of its line. Verified beyond the pair that found it: five
  independent anchor-reaching boots from the race survey all normalize to the
  same **881 B** prefix, whether the cut fired on the login record or the banner.

## RED-first evidence (verbatim, run 5 — the same run that went green)

```
L5  RED — flip ONE zeropage byte outside the whitelist; the differ must name it
  mutant: 0x244 0x00 -> 0x01 (outside every whitelist row)
      L2 PASS: cmdline byte-identical all 512 B (82 chars)
      L2b PASS: ramdisk_image=0x10000000 ramdisk_size=0x8d4f07 == bm903_layout.json (constructed, not copied)
      L3 PASS: all 25 registers match the oracle, including rsp=0x1f784 (BM902 whitelisted it)
      L1 FAIL: 1 zeropage diff(s) vs bm902_zp.bin outside whitelist: 0x244
      RED LEG OK: differ exited non-zero as required
  [PASS] L5 green: mutant caught, differ exits non-zero naming 0x244
      control L1 PASS: 5 zeropage byte(s) differ from bm902_zp.bin, all inside the whitelist union (517 offsets): 0x210, 0x21b, 0x21c, 0x21d, 0x21e
  [PASS] L5 control: a whitelisted change stays green
```

```
L6  RED — corrupt ONE medium byte: gate refuses, host arithmetic cross-checks, NO jump
      corrupt: payload byte 4000000 (inside the pm kernel) at medium offset 0xf6440, 0xe5 -> 0xe4  (1 byte of 13640192 changed)
      host decode cross-check: clean medium -> 393950AA == EXPECTED; corrupt medium -> 6AB8F2D3
      wrote /tmp/bm903_medium_px_corrupt.raw (13640192 B) and /tmp/bm903_medium_px_corrupt.crc
        [+   1.0s] stage2 enter
        [+   1.0s] a20 ok
        [+   1.0s] walk done
        [+   1.0s] gate verdict
        walk done    seen
        gate line    seen
                     computed=6AB8F2D3 expected=393950AA MISMATCH
        pass verdict MISSING
        handoff      MISSING
        anchor       MISSING
      medium=bm903_medium_px_corrupt.raw log=/tmp/bm903_e2e_l6.log elapsed=1.0s rc=1
      guest printed: BM903-S2 GATE2 CRC=6AB8F2D3 EXP=393950AA
      host predicted: BM903-S2 GATE2 CRC=6AB8F2D3 EXP=393950AA
  [PASS] L6 cross-check: the guest's computed CRC == the host's independent prediction, and != EXPECTED
  [PASS] L6 refusal present (rung-4 format: computed then expected, then the verdict)
  [PASS] no 'HANDOFF BUILT' after the refusal
  [PASS] no anchor from the corrupted medium
        leg 0: last-checkpoint=BM903-S2 GATE2 (5/6) stop=NO STOP (timeout or hung loader) wall=20.0s
      leg 0: NO CAPTURE (gdb never stopped on the handoff)
        leg 1: last-checkpoint=BM903-S2 GATE2 (5/6) stop=NO STOP (timeout or hung loader) wall=20.0s
      leg 1: NO CAPTURE (gdb never stopped on the handoff)
  [PASS] L6 no-jump proven under gdb: no stop at 0x100000 within 20s x2 legs (rc=1)
```

Run 5 exercised the new attempt policy for real — L3's first boot lost the race
and was printed as a loss, the second won:

```
L3  the kernel speaks on serial and reaches 'tc@box'
    (up to 8 boots x 45s — which tty autologin wins is Tiny Core's, not ours)
      boot 1/8 rc=1: no tc@box on serial (45s budget; guest autologin race)
  [PASS] L3 green: pixel medium -> kernel -> tc@box on boot 2 of 8 (45s each, rc=0)
      control medium=bm903_medium.raw log=/tmp/bm903_e2e_ctrl.log elapsed=11.0s rc=0
  [PASS] control: the contiguous medium reaches tc@box (boot 1, rc=0) — the rig boots
L4  ...
  [PASS] second pixel boot reached tc@box (boot 1 of 8, rc=0)
        bm903_e2e_leg0.log: 1318 B -> 881 B compared   fired: T2 login pid=2, T3 spinner cycles=2, T4 cut=881 B, at the first issue banner
        bm903_e2e_leg1.log: 1308 B -> 881 B compared   fired: T2 login pid=2, T3 spinner cycles=2, T4 cut=881 B, at the first login record
  [PASS] transcripts byte-identical after T1-T4 (compared up to the getty race)
```

## GREEN tail (verbatim, run 5)

```
BM903 E2E TALLY: 42 pass, 0 red
BM903 ROW GREEN: the PXC1 pixel medium carries bzImage+initrd, executed
stage2 builds the BM902 handoff (4 whitelisted bytes), CRC32 gate v2 is
the only path to it (and refuses on a single corrupted byte, with the
guest's own arithmetic matching the host's), and the kernel reaches
'tc@box' on serial (guest-autologin-race allowance: 8 boots x
45s, each named). Both RED legs fired.
```

Load-bearing numbers, same run:

```
leg 0: last-checkpoint=BM903-S2 HANDOFF BUILT (6/6) stop=stopped on the handoff wall=0.7s
L1 PASS: 4 zeropage byte(s) differ ... all inside the whitelist union (517 offsets): 0x21b, 0x21c, 0x21d, 0x21e
L2b PASS: ramdisk_image=0x10000000 ramdisk_size=0x8d4f07 == bm903_layout.json (constructed, not copied)
L2  pinned rsp=0x1f784 cr0=0x11 eflags=0x46 cs=0x10 ss/ds/es=0x18 rsi=0x13ab0 rip=rax=0x100000; 15 more = 0 -> ALL 26 MATCH
L1b bm903_px_zp_leg0.bin == bm903_zp_leg0.bin ; bm903_px_cmdline_leg0.bin == bm903_cmdline_leg0.bin
```

## Other defects found RED-first in this gate's own rig

The very first execution returned `32 pass, 7 red`. All seven traced to the
gate, not the boot ladder, and they are pasted rather than glossed:

1. `ROOT="$(cd ../.. && pwd)"` resolved to `tools/`, not the repo root, so
   `$OUT/bm903_anchor_boot.py` pointed at a path that did not exist and L3, L4
   and L6 all failed on `can't open file … [Errno 2]`. L1/L1b/L2/L5/R1 stayed
   green in the same run. Fix: correct the path, plus three S0 rows asserting
   the probes exist — a missing hand must name itself as a broken gate before a
   boot can dress it up as a leg failure.
2. A false RED of the opposite polarity: L6's no-jump check grepped for
   `stopped on the handoff`, and the capture's failure line `gdb never stopped
   on the handoff` contains that substring — so a *correct* refusal read as "the
   corrupted medium DID stop on the kernel entry". Fix: match the capture's
   positive marker `stop=stopped on the handoff`.

Neither fix touched a comparison, a budget or a whitelist, and both predate the
first green run.

## Serialization contract (measured in step 2, enforced here)

QEMU write-locks the image even for a read-only boot, and concurrent TCG guests
turned an 11 s boot into an apparent >240 s stall. The gate runs legs strictly
one at a time and S0b refuses to start if any other bm903 qemu is alive. Every
boot leg carries a wall-clock timeout, so a hang is a FAIL that names its
budget — never a stuck gate.

## Honest boundary

- The anchor is Tiny Core's `tc@box` prompt on ttyS0. It proves the kernel
  decompressed, mounted the initrd, ran init and drew a login prompt — it does
  not prove pixel-frame writeback from this guest; nothing in this row paints a
  container.
- L3/L4 tolerate a *guest-side* coin flip, and say so per attempt. They do not
  tolerate a missing anchor: eight named 45 s boots is the same worst-case wall
  clock the original single 180 s boot had, and it ends in RED.
- L1's 4-byte diff is the constructed `ramdisk_image`/`ramdisk_size` pair,
  licensed by the BM903 field-plan addendum and re-derived by
  `bm903_layout.json` — whitelisted, not waved through.
- L4's transcript comparison stops at the first race-onset line. The discarded
  tail is reported (length + sha256), never silently dropped; the compared
  prefix still covers the entire stage2 trace, the whole kernel boot and all of
  init's bootcode.
- The CRC gate proves the medium decodes to the bytes the host wrote. That the
  bytes are *a kernel* is carried by the oracle diff and the `tc@box` anchor,
  not by the checksum.

## Reproducing this gate on another machine (measured, 2026-09-19)

`git status` on a clean clone is NOT enough to run it. Checked which inputs the
build actually reads:

| input | in git? | who needs it |
|---|---|---|
| `rung9/bm903_stage2_px.asm`, `bm903_px_layout.inc`, `bm903_crc32tab.inc`, the probes and both gate scripts | **yes** (commit `d27f46c6`) | everything below |
| `rung9/vmlinuz64.extracted` (4,295,328 B) | **yes** | `bm903_pxcodec.build_payload` |
| `rung9/oracle_{zp,cmdline}_leg{0,1}.bin`, `oracle_pins.txt` | **yes** (force-added past `*.bin`) | L1/L2 differ |
| `rung9/bm903_medium_px.raw`, `bm903_stage{1,2}*.bin` | no — `.gitignore:71-72` | regenerated by the gate itself, fine |
| **`rung7/core.gz`** (9,260,807 B initrd) | **NO — untracked, and not ignored** | `bm903_pxcodec.build_payload` reads it directly |
| **`rung7/TinyCore-current.iso`** (28,135,424 B) | **NO** | BM901's oracle, and the only source `core.gz` can be re-extracted from |

So the row is green-and-committed but **not self-hosting from git alone**: two
large blobs that `TASK_BM001` keeps out of the tree are load-bearing inputs.
That is a scope fact for Jericho's BM001 ratification, recorded here rather
than resolved — landing 37 MB of third-party binaries under a hold gate is his
call, not a side effect of closing BM903.
