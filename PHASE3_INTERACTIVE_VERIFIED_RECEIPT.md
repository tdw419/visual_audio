# Phase 3 Interactive Path — END-TO-END VERIFIED (2026-08-24)

**Verdict: Phase 3 (interactive window coordinator) is CONFIRMED WORKING via real
device-emulation input.** The prior session's conclusion ("input cannot reach the
guest; needs a human with a real mouse") was **wrong**. The input path works; the
real problems were (a) a VMware VMMouse protocol mismatch and (b) a batch-delta bug
in `evdev_input.rs` — both found and fixed this session.

---

## What was verified (all levels, real measurements)

| Level | Evidence |
|-------|----------|
| Kernel IRQ | `i8042` IRQ 12 increments on every injected packet (15 → 24 → 42 → 51 → 92 → 110 → 128 → 137 ...) |
| evdev events | Python reader on `/dev/input/event2` captured the exact injected sequence: REL_X=50, REL_Y=50, BTN_LEFT down/up, REL_X=30, REL_Y=20, BTN_LEFT down/up |
| App dispatch | Instrumented `v5_interactive` logs `EVENT: type=1 x=50 y=50` (click) and `EVENT: type=2 x=260 y=150 dx=40 dy=30` (diagonal drag) |
| GPU WCB mutation | Read-back after each event: click → RED `z: 1→3`; drag → GREEN `x,y: (100,100)→(140,130)` |
| Framebuffer pixels | screendump analysis: RED/GREEN overlap flips green→red after click raise, red→green after GREEN raise; window bboxes shift by exact drag deltas |

### The user's test script, executed:
1. **Click on RED window (50,50)** → RED raised to top (z 1→3; overlap region
   (100,100)-(249,199) went 14,751 green pixels → 14,751 red pixels) ✓
2. **Click-drag GREEN window** → GREEN raised (z 2→5) and moved diagonally
   (100,100)→(140,130); pixel probes confirm old spot is RED, new spot is GREEN ✓
3. Extra: click at (100,100) after RED raised correctly hit RED again (z 3→4) —
   topmost-wins z-order is behaving correctly. BLUE drag also verified (y 20→50).

---

## Root cause of the prior session's false negative

1. **Their VM had no working NIC** (no e1000/virtio-net probe in the serial log) →
   SSH to the guest never worked → the "/proc/interrupts = 1497 unchanged"
   guest-side measurement could not have been taken as described.
2. **QEMU monitor injection DOES reach the guest.** `mouse_move`/`mouse_button`
   inject at the PS/2 controller emulation layer, completely independent of the
   SDL display backend. IRQ 12 proves delivery.
3. **The real blocker: VMware VMMouse absolute protocol.** The guest's Linux
   `psmouse` driver (proto=auto) detects QEMU's "VirtualPS/2 VMware VMMouse" and
   switches the controller to absolute mode, registering TWO devices (event2=ABS,
   event3=REL). In that mode the driver consumes standard PS/2 relative packets
   without producing evdev events — IRQ fires, nothing delivered.
   **Fix:** `modprobe -r psmouse && modprobe psmouse proto=imps` → single standard
   REL device at `/dev/input/event2` (note: the deploy script's hardcoded
   `/dev/input/event3` became stale after the fix).
4. **Batch-delta bug in `evdev_input.rs`** (found by this verification): a single
   `fetch_events()` containing REL_X + REL_Y (normal for diagonal motion) produced
   only ONE `WindowEvent` — the last axis delta — silently dropping the first
   (e.g. `dx=0 dy=30` when the input was `+40,+30`). **Fixed:** accumulate
   `acc_dx`/`acc_dy` across the batch and emit one drag with both deltas, anchored
   at the pre-batch position. Re-verified: diagonal drag now applies both deltas.

---

## Evidence artifacts (all on host)

```
/tmp/v5_base3.ppm            baseline framebuffer (3 windows, z-order GREEN>RED>BLUE)
/tmp/v5_click_ok.ppm         after click on RED — overlap flipped to RED (raised)
/tmp/v5_drag_ok.ppm          after RED drag (y 50→80)
/tmp/v5_green_drag.ppm       after GREEN raise + BLUE drag (BLUE y 20→50)
/tmp/v5_diag_fixed.ppm       after diagonal GREEN drag (100,100)→(140,130)
/tmp/gpu_coordinator_verify_20260823_220159.log   (GPU coordinator, prior session)
```

Guest-side log: `/tmp/v5_instr.log` on the VM (EVENT + WCB read-back lines).

---

## How to reproduce

```bash
# 1. Boot desktop VM (detached, monitor socket, working virtio-net)
bash launch_v5_vm.sh                      # setsid qemu; wait for ssh on :2222

# 2. Force standard PS/2 protocol in the guest (kills VMMouse absolute mode)
bash fix_psmouse_proto.sh                 # modprobe -r psmouse; modprobe psmouse proto=imps

# 3. Build + push + run instrumented v5_interactive on /dev/input/event2
bash run_v5_instrumented.sh               # V5_INPUT_DEVICE=/dev/input/event2

# 4. Inject real input via QEMU monitor (never send `quit` — it shuts the VM!)
bash qemu_mon.sh "mouse_move 50 50" "mouse_button 1" "mouse_button 0"
bash qemu_mon.sh "screendump /tmp/shot.ppm"

# 5. Verify
grep -A8 EVENT /tmp/v5_instr.log          # app-side events + WCB state
```

**Pitfall discovered:** the QEMU monitor `quit` command shuts down the VM, not the
monitor session. Two VMs were lost to this before the helper `qemu_mon.sh` was
written (it never sends `quit`).

---

## Status

- Phase 3 interactive path: **VERIFIED END-TO-END** (click→raise, drag→move, z-order)
- `evdev_input.rs` batch-delta bug: **FIXED** + re-verified on GPU
- 29/29 `geos_v5` lib tests pass; `v5_interactive` builds with
  `--features gpu,evdev`
- Pre-existing (unrelated) breakage: `examples/wc008_gui.rs` fails to build
  (`use geos_v5::window` but that module is cfg'd behind the `gpu` feature; the
  example's Cargo.toml lacks `required-features`). Not touched — out of scope.
- VM left running (QEMU PID from `launch_v5_vm.sh`) with gdm stopped; restart gdm
  in the guest if a normal desktop session is wanted again.

**Last Updated**: 2026-08-24
