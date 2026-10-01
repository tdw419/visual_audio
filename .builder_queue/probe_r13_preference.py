"""R1.3 preference probe (P1.3 kill switch) — GPU-OS lane vs Ubuntu lane.

TASK (both lanes, identical): 4 co-resident agent tasks per batch with
seeds 2/3/4/5, each computing y = x*(x+1) (expected 6/12/20/30 —
exactly RES_FLEET_ARGV_SEEDS / RES_FLEET_EXPECT from the R1.2 fleet
image), plus tenant C being an ADVERSARY that attempts a cross-tenant
store of 0xDEAD into B's result slot. Success criterion (identical on
both lanes): A/B/D results correct, adversary contained (B's slot not
0xDEAD), C may fault.

GPU lane: the R1.2 fleet image — tile-ABI box isolation, per-leg arming
(BOX0/BOX1/BOX2-split), GH-16 preemption at quantum 6, executed on the
CPU-oracle substrate (GlyphCPUv2; the gated path — WGSL twin is
functionally divergent on this image family, recorded datum).
Ubuntu lane: 4 systemd-run --user sandboxes in parallel (the only
working isolation mechanism on this host: userns/bwrap are EPERM under
apparmor_restrict_unprivileged_userns=1), each a cold `python -c`.
  U1 sandbox + adversarial C: C attempts an out-of-bounds store via
    ctypes (SIGSEGV) — the OS address space is the containment.
  U2 NO-ISOLATION control: 4 processes in shared memory
    (multiprocessing.shared_array) — C's 0xDEAD store must LAND,
    proving the failure-rate leg is the isolation mechanism, not the
    task being trivial. Mirrors the GPU --naive control.

GATE (PRODUCT_ROADMAP.md R1.3, AMENDED): GPU must win-or-tie on
FAILURE RATE plus at least one of {wall-clock, cost}.

RED legs (gate must be shown able to fail):
  --corrupt  GPU expectations corrupted -> probe MUST exit 1
  --naive    fleetnaive image: the adversarial store LANDS in-guest ->
             proves the GPU zero-failure leg is the arming MECHANISM.
  (U2 is itself the Ubuntu-side RED control.)

HONESTY: "GPU lane" = Glyph stack (image+kernel+tile-ABI) on the
CPU-oracle substrate, in-process steps, ~2us/step — NO calibrated floor
exists for this path (floors_authoritative measures SpatialRV32ICore.step
and the WGSL protocol; different code paths), so check_regime is
EXPECTED-inadmissible here and the wall-clock legs are same-process
symmetric measurements, not floor-derived rates. WGSL divergence datum:
the true shader path cannot run the fleet (halts early, all fleet words
0) — the wall-clock win is NOT a shader-path claim. Cost: both lanes are
local compute only (electricity) — recorded as a TIE, not a win.
"""
import multiprocessing as mp
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from tools.glyph_gpt.atlas import build_default_atlas          # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402
from tools.glyph_gpt.agent_resident import (                   # noqa: E402
    resident_image, RES_FLEET_EXPECT, RES_FLEET_RCPT, RES_DONE_WORD,
    RES_FAULT_WORD, RES_FLEET_DONE, RES_KERNEL_OK,
    RES_FLEET_ADVERSARY_TARGET, RES_FLEET_ADVERSARY_PAYLOAD,
)

GPU_BATCHES = 20
UBU_BATCHES = 20
QUANTUM = 6
STEP_BUDGET = 200_000
SEEDS = (2, 3, 4, 5)                    # A, B, C, D
ADV_INDEX = 2                           # C is the adversarial tenant
TASK_SRC = "import sys; x={seed}; sys.stdout.write(str(x*(x+1)))"
# adversarial C: attempt a cross-tenant store then do its own task
ADV_SRC = ("import sys, ctypes; ctypes.memmove(0x10, b'\\xad\\xde', 2); "
           "x={seed}; sys.stdout.write(str(x*(x+1)))")

corrupt = "--corrupt" in sys.argv
naive = "--naive" in sys.argv

if corrupt:
    EXPECT = dict(RES_FLEET_EXPECT)
    EXPECT[728] = RES_FLEET_ADVERSARY_PAYLOAD  # what a naive run yields
else:
    EXPECT = RES_FLEET_EXPECT

mode = "fleetnaive" if naive else "fleet"

# ================= GPU lane =================
gpu_fail = 0
with tempfile.TemporaryDirectory() as d:
    img = Path(d) / f"{mode}.npy"
    t_bake0 = time.perf_counter()
    resident_image(build_default_atlas(), mode=mode, timer_quantum=QUANTUM,
                   out_path=img)
    bake_ms = (time.perf_counter() - t_bake0) * 1000
    runner = GlyphRunner(img, ram_words=16384)

    gpu_total = 0.0
    last_steps = 0
    for _b in range(GPU_BATCHES):
        cpu = runner.get_cpu()          # fresh zeroed RAM = cold boot
        t0 = time.perf_counter()
        cpu.running = True
        steps = 0
        while cpu.running and steps < STEP_BUDGET:
            cpu.step(runner.image)
            steps += 1
        gpu_total += time.perf_counter() - t0
        last_steps = steps
        if naive:
            ok = (not cpu.running
                  and cpu.memory[RES_FLEET_ADVERSARY_TARGET]
                  == RES_FLEET_ADVERSARY_PAYLOAD
                  and cpu.memory[RES_DONE_WORD] == 0b1111
                  and cpu.memory[RES_FAULT_WORD] == 0)
        else:
            ok = (not cpu.running
                  and cpu.memory[RES_FLEET_RCPT] == RES_FLEET_DONE
                  and cpu.memory[RES_DONE_WORD] == 0b1011
                  and cpu.memory[RES_FAULT_WORD] == 0xFA026
                  and all(cpu.memory[w] == v for w, v in EXPECT.items()))
        if not ok:
            gpu_fail += 1

gpu_us = gpu_total / GPU_BATCHES * 1e6
print(f"GPU lane [{mode}]: bake {bake_ms:.0f}ms once (amortized "
      f"{bake_ms / GPU_BATCHES:.1f}ms/batch), cold-boot+run "
      f"{gpu_total / GPU_BATCHES * 1000:.2f} ms/batch-of-4, "
      f"steps/boot={last_steps}, failures={gpu_fail}/{GPU_BATCHES} batches")

# ================= Ubuntu lane =================
py = sys.executable

# U1: sandboxed fleet with adversarial C (containment = OS address space)
# NOTE on reaping: procs[i] stays bound to tenant i; communicate() is
# called per process in tenant order — output attribution is positional,
# independent of completion order. C is EXPECTED to die (SIGSEGV on its
# cross-tenant store, journal shows code=dumped status=11/SEGV) — its
# containment is the lane doing its job, so C contributes no output and
# no failure; B/A/D correctness is the criterion, mirroring the GPU
# lane's criterion (A/B/D correct, B's slot not 0xDEAD, C faulted).
ubu_bad = 0
ubu_total = 0.0
for _b in range(UBU_BATCHES):
    t0 = time.perf_counter()
    procs = []
    for i, s in enumerate(SEEDS):
        src = ADV_SRC.format(seed=s) if i == ADV_INDEX else TASK_SRC.format(seed=s)
        procs.append(subprocess.Popen(
            ["systemd-run", "--user", "--pipe", py, "-c", src],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL))
    outs = []
    for p in procs:                    # tenant order, positional
        out, _ = p.communicate()
        outs.append(out)
    ubu_total += time.perf_counter() - t0
    # criterion: A/B/D results correct and B not the adversary's value;
    # C may be dead (its store was contained by the sandbox)
    b_out = outs[1].strip()
    contained = (outs[0].strip() == b"6"
                 and b_out == b"12"
                 and outs[3].strip() == b"30"
                 and b_out != b"57066")   # 0xDEAD as decimal, paranoia
    if not contained:
        ubu_bad += 1
ubu_us = ubu_total / UBU_BATCHES * 1e6
print(f"Ubuntu lane [systemd-run sandbox, adversarial C]: "
      f"{ubu_total / UBU_BATCHES * 1000:.2f} ms/batch-of-4 (4-wide), "
      f"failures={ubu_bad}/{UBU_BATCHES} batches")

# U2: NO-ISOLATION control — shared memory, C's store must LAND.
# Fork start method (this probe process IS the __main__ guard; mp default
# on Linux is fork, but we set it explicitly so the control is honest).
def _naive_worker(i: int, seed: int, arr) -> None:
    if i == ADV_INDEX:
        arr[1] = 0xDEAD                # cross-tenant store into B's slot
    else:
        arr[i if i < ADV_INDEX else i - 1] = seed * (seed + 1)

naive_bad = 0
naive_total = 0.0
_ctx = mp.get_context("fork")
for _b in range(UBU_BATCHES):
    arr = _ctx.Array("L", 3)           # 3 result slots: A, B, D (B = index 1)
    t0 = time.perf_counter()
    ps = [_ctx.Process(target=_naive_worker, args=(i, s, arr))
          for i, s in enumerate(SEEDS)]
    for p in ps:
        p.start()
    for p in ps:
        p.join()
    naive_total += time.perf_counter() - t0
    if arr[1] != 0xDEAD:               # control REQUIRES the corruption
        naive_bad += 1
naive_us = naive_total / UBU_BATCHES * 1e6
print(f"Ubuntu control [shared mem, NO isolation]: "
      f"{naive_total / UBU_BATCHES * 1000:.2f} ms/batch-of-4, "
      f"corruption landed={UBU_BATCHES - naive_bad}/{UBU_BATCHES} batches "
      f"(control REQUIRES corruption)")

# LEG lines (check_regime format). No calibrated floor exists for any of
# these paths (see HONESTY above); legs are same-process symmetric
# wall-clock measurements.
print(f"LEG gpu_fleet_batch {gpu_us:.1f} steps/s {gpu_us:.1f} us/rep step x1")
print(f"LEG ubuntu_sandbox_batch {ubu_us:.1f} steps/s {ubu_us:.1f} us/rep step x1")
print(f"LEG ubuntu_noiso_control {naive_us:.1f} steps/s {naive_us:.1f} us/rep step x1")

if corrupt:
    if gpu_fail == 0:
        print("RED FAIL: corrupted expectations still passed — gate is decoration")
        sys.exit(1)
    print("RED OK: corrupted expectations rejected — gate bites")
    sys.exit(0)

if naive:
    if gpu_fail != 0:
        print("NAIVE control did not corrupt — GPU isolation mechanism unproven")
        sys.exit(1)
    print("NAIVE OK: in-guest control corrupts (728=0xDEAD) — zero-failure leg is the mechanism")
    sys.exit(0)

if gpu_fail != 0:
    print("GPU lane failed its own GREEN run — probe invalid")
    sys.exit(1)
if naive_bad != 0:
    print("Ubuntu no-isolation control did NOT corrupt — control invalid")
    sys.exit(1)
print("PROBE OK")
