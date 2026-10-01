"""tools/pyshader_ca_probe.py — PS003: CA propagation as parallel invocations.

THE question this rung tests (see PS001_PS002_PYSHADER_RECEIPT.md):
does cellular-automaton propagation — each cell's next state a function
of its NEIGHBORS' current state — survive the parallel GPU invocation
model, or does it only work scalar-sequentially?

Probe: 1D elementary rule 90 over 64 u32 cells, 64 generations.
    new[i] = old[i-1] XOR old[i+1]
    boundary: fixed-0 (i-1 < 0 and i+1 >= 64 read 0) — SAME rule in
    oracle and shaders, stated here so an edge mismatch can never be
    mistaken for a parallelism bug.
    initial state: 64 random u32 words, Python random.seed(20260917).

Launch shape (identical for both variants):
    @workgroup_size(1,1,1), dispatch_workgroups(64,1,1)
    invocation #w owns cell w. One invocation per workgroup = zero
    lockstep shielding between cells (subgroup SIMD could otherwise
    mask the race by making all reads precede all writes in-lockstep).

Variants:
  A double-buffer (predicted PASS): two storage arrays; shader does ONE
    synchronous step per dispatch (reads buf_old, writes buf_new); host
    swaps and re-dispatches per generation. Cross-workgroup sync is the
    dispatch boundary itself — the only sound cross-workgroup sync
    WebGPU offers. This is the "pay for the buffer swap" answer.
  B single-buffer in-place (predicted FAIL / race): ONE array; each
    invocation loops 64 generations internally reading and writing the
    same cells. No cross-workgroup barrier exists in WGSL, so neighbor
    reads race with neighbor writes. NOT proven-correct by any
    schedule; any divergence from the oracle is a measured race.

Engines compared:
    1. sync_oracle       — scrupulous synchronous Python: reads
                           ENTIRELY from the old list, writes a NEW
                           list. Never mutates in place, so it cannot
                           share the single-buffer race by construction.
    2. GPU double-buffer — variant A.
    3. GPU single-buffer — variant B, run TRIALS=100 times: a race can
                           pass by scheduling luck, so one run proves
                           nothing in either direction.
    4. seq_inplace_pred  — deterministic prediction for "what if the 64
                           invocations happened to run in index order"
                           (sequential in-place update). Classifies a
                           variant-B failure: matching THIS means
                           "serialized, wrong for a named reason";
                           matching NEITHER oracle nor this means
                           "genuinely raced, nondeterministic".

Receipt discipline: variant A must equal the oracle (hard assertion in
tests). Variant B results are characterized, not hidden: match counts
vs oracle and vs the in-place prediction are printed and stored.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

N_CELLS = 64
N_GENS = 64
TRIALS = 100
SEED_STATE_SEED = 20260917

BUF_A = 0                # word offset of buffer A
BUF_B = N_CELLS          # word offset of buffer B
BUFFER_WORDS = 2 * N_CELLS


# ── engines 1 and 4: pure Python ────────────────────────────────────────

def initial_state() -> List[int]:
    import random
    rng = random.Random(SEED_STATE_SEED)
    return [rng.getrandbits(32) for _ in range(N_CELLS)]


def _step(read: List[int]) -> List[int]:
    """One rule-90 step. `read` is never mutated; returns a fresh list.
    Fixed-0 boundary: neighbors outside [0, 64) are 0."""
    out = [0] * N_CELLS
    for i in range(N_CELLS):
        left = read[i - 1] if i - 1 >= 0 else 0
        right = read[i + 1] if i + 1 < N_CELLS else 0
        out[i] = (left ^ right) & 0xFFFFFFFF
    return out


def sync_oracle(state: List[int], gens: int) -> List[int]:
    """Engine 1 — scrupulously synchronous: every generation reads the
    ENTIRE old generation and writes an entirely new list."""
    cur = list(state)
    for _ in range(gens):
        cur = _step(cur)
    return cur


def seq_inplace_predict(state: List[int], gens: int) -> List[int]:
    """Engine 4 — what variant B produces IF invocations serialize in
    index order (cell 0 fully updates before cell 1 ever reads it).
    Not a claim about hardware; a classification reference."""
    mem = list(state)
    for _ in range(gens):
        for i in range(N_CELLS):
            left = mem[i - 1] if i - 1 >= 0 else 0
            right = mem[i + 1] if i + 1 < N_CELLS else 0
            mem[i] = (left ^ right) & 0xFFFFFFFF
    return mem


# ── engines 2 and 3: WGSL variants ──────────────────────────────────────

_CA_COMMON = f"""
const N: u32 = {N_CELLS}u;

// fixed-0 boundary, identical to the oracle's rule:
fn nbr(base: u32, idx: i32) -> u32 {{
    if (idx < 0) {{ return 0u; }}
    let u = u32(idx);
    if (u >= N) {{ return 0u; }}
    return buf[base + u];
}}
"""

# Variant A: one synchronous step per dispatch; host swaps buffers.
# Two fixed shader texts (A→B and B→A) generated up front — no fragile
# string surgery at swap time.
_CA_STEP_AB = """// generated by tools/pyshader_ca_probe.py — variant A (A→B)
@group(0) @binding(0) var<storage, read_write> buf: array<u32, %d>;
%s
@compute @workgroup_size(1, 1, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let me = gid.x;
    let l = nbr(%d, i32(me) - 1);
    let r = nbr(%d, i32(me) + 1);
    buf[%d + me] = l ^ r;
}
""" % (BUFFER_WORDS, _CA_COMMON, BUF_A, BUF_A, BUF_B)

_CA_STEP_BA = """// generated by tools/pyshader_ca_probe.py — variant A (B→A)
@group(0) @binding(0) var<storage, read_write> buf: array<u32, %d>;
%s
@compute @workgroup_size(1, 1, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let me = gid.x;
    let l = nbr(%d, i32(me) - 1);
    let r = nbr(%d, i32(me) + 1);
    buf[%d + me] = l ^ r;
}
""" % (BUFFER_WORDS, _CA_COMMON, BUF_B, BUF_B, BUF_A)

# Variant B: all generations in one dispatch, one shared array, no sync.
_CA_RACE_SHADER = """// generated by tools/pyshader_ca_probe.py — variant B
@group(0) @binding(0) var<storage, read_write> buf: array<u32, %d>;
%s
@compute @workgroup_size(1, 1, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let me = gid.x;
    for (var g = 0u; g < %du; g = g + 1u) {
        // RACE (deliberate): reads and writes the same array with no
        // cross-workgroup synchronization of any kind.
        let l = nbr(%d, i32(me) - 1);
        let r = nbr(%d, i32(me) + 1);
        buf[%d + me] = l ^ r;
    }
}
""" % (BUFFER_WORDS, _CA_COMMON, N_GENS, BUF_A, BUF_A, BUF_A)


def _gpu_device():
    import wgpu
    adapter = wgpu.gpu.request_adapter_sync(
        power_preference="high-performance")
    return adapter.request_device_sync(label="ca-probe")


def _dispatch(device, shader_module, n_words: int) -> List[int]:
    """One dispatch(64,1,1) over the bound buffer; return readback."""
    import struct
    import wgpu

    gpu_buf = device.create_buffer(
        size=n_words * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        label="ca-state")
    readback = device.create_buffer(
        size=n_words * 4,
        usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ,
        label="ca-read")

    pipe = device.create_compute_pipeline(
        layout="auto",
        compute={"module": shader_module, "entry_point": "main"},
        label="ca-pipe")
    bg = device.create_bind_group(
        layout=pipe.get_bind_group_layout(0),
        entries=[{"binding": 0,
                  "resource": {"buffer": gpu_buf, "offset": 0,
                               "size": n_words * 4}}],
        label="ca-bind")

    enc = device.create_command_encoder(label="ca-enc")
    cp = enc.begin_compute_pass()
    cp.set_pipeline(pipe)
    cp.set_bind_group(0, bg)
    cp.dispatch_workgroups(N_CELLS, 1, 1)
    cp.end()
    enc.copy_buffer_to_buffer(gpu_buf, 0, readback, 0, n_words * 4)
    device.queue.submit([enc.finish()])

    readback.map_sync(mode=wgpu.MapMode.READ)
    data = bytes(readback.read_mapped())
    readback.unmap()
    return list(struct.unpack(f"<{n_words}I", data))


def run_variant_a(state: List[int]) -> List[int]:
    """Double-buffer: N_GENS dispatches, host swaps A/B between them.
    Cross-workgroup sync = the dispatch boundary — the only sound
    cross-workgroup synchronization WebGPU provides."""
    import struct
    import wgpu

    device = _gpu_device()
    mods = {
        (BUF_A, BUF_B): device.create_shader_module(
            code=_CA_STEP_AB, label="ca-step-AB"),
        (BUF_B, BUF_A): device.create_shader_module(
            code=_CA_STEP_BA, label="ca-step-BA"),
    }

    n = BUFFER_WORDS
    gpu_buf = device.create_buffer(
        size=n * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
        | wgpu.BufferUsage.COPY_SRC,
        label="ca-state")
    device.queue.write_buffer(gpu_buf, 0, struct.pack(
        f"<{n}I", *(list(state) + [0] * N_CELLS)))

    pipes = {}
    for key, mod in mods.items():
        pipe = device.create_compute_pipeline(
            layout="auto",
            compute={"module": mod, "entry_point": "main"},
            label=f"ca-pipe-{key[0]}to{key[1]}")
        pipes[key] = device.create_bind_group(
            layout=pipe.get_bind_group_layout(0),
            entries=[{"binding": 0,
                      "resource": {"buffer": gpu_buf, "offset": 0,
                                   "size": n * 4}}],
            label=f"ca-bind-{key[0]}to{key[1]}")
        pipes[key] = (pipe, pipes[key])

    src = BUF_A
    for _ in range(N_GENS):
        dst = BUF_B if src == BUF_A else BUF_A
        pipe, bg = pipes[(src, dst)]
        enc = device.create_command_encoder(label="ca-enc")
        cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe)
        cp.set_bind_group(0, bg)
        cp.dispatch_workgroups(N_CELLS, 1, 1)
        cp.end()
        device.queue.submit([enc.finish()])
        src = dst

    final_base = BUF_A if N_GENS % 2 == 0 else BUF_B
    readback = device.create_buffer(
        size=N_CELLS * 4, usage=wgpu.BufferUsage.COPY_DST
        | wgpu.BufferUsage.MAP_READ, label="ca-read")
    enc = device.create_command_encoder(label="ca-final")
    enc.copy_buffer_to_buffer(gpu_buf, final_base * 4,
                              readback, 0, N_CELLS * 4)
    device.queue.submit([enc.finish()])
    readback.map_sync(mode=wgpu.MapMode.READ)
    data = bytes(readback.read_mapped())
    readback.unmap()
    return list(struct.unpack(f"<{N_CELLS}I", data))


def run_variant_b_once(device, shader_module, state: List[int]
                       ) -> List[int]:
    """Single-buffer race: seed state into the shared array, dispatch
    once (all 64 generations happen inside the shader's internal loop,
    reading and writing one array with no synchronization)."""
    import struct
    import wgpu
    n = BUFFER_WORDS
    gpu_buf = device.create_buffer(
        size=n * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
        | wgpu.BufferUsage.COPY_SRC,
        label="ca-race")
    device.queue.write_buffer(gpu_buf, 0, struct.pack(
        f"<{n}I", *(list(state) + [0] * N_CELLS)))

    pipe = device.create_compute_pipeline(
        layout="auto",
        compute={"module": shader_module, "entry_point": "main"},
        label="ca-pipe-race")
    bg = device.create_bind_group(
        layout=pipe.get_bind_group_layout(0),
        entries=[{"binding": 0,
                  "resource": {"buffer": gpu_buf, "offset": 0,
                               "size": n * 4}}],
        label="ca-bind-race")

    enc = device.create_command_encoder(label="ca-enc")
    cp = enc.begin_compute_pass()
    cp.set_pipeline(pipe)
    cp.set_bind_group(0, bg)
    cp.dispatch_workgroups(N_CELLS, 1, 1)
    cp.end()
    device.queue.submit([enc.finish()])

    readback = device.create_buffer(
        size=N_CELLS * 4, usage=wgpu.BufferUsage.COPY_DST
        | wgpu.BufferUsage.MAP_READ, label="ca-read")
    enc2 = device.create_command_encoder(label="ca-race-read")
    enc2.copy_buffer_to_buffer(gpu_buf, BUF_A * 4, readback, 0,
                               N_CELLS * 4)
    device.queue.submit([enc2.finish()])
    readback.map_sync(mode=wgpu.MapMode.READ)
    data = bytes(readback.read_mapped())
    readback.unmap()
    return list(struct.unpack(f"<{N_CELLS}I", data))


def run_probe() -> Dict:
    """Full PS003 receipt. Returns the evidence dict; does NOT assert —
    the pytest suite owns the hard assertion on variant A and honest
    characterization of variant B."""
    import wgpu

    state = initial_state()
    oracle = sync_oracle(state, N_GENS)
    inplace = seq_inplace_predict(state, N_GENS)

    device = _gpu_device()
    race_shader = device.create_shader_module(code=_CA_RACE_SHADER,
                                              label="ca-race")

    a = run_variant_a(state)
    a_ok = a == oracle

    b_trials = []
    b_match_oracle = 0
    b_match_inplace = 0
    for _ in range(TRIALS):
        b = run_variant_b_once(device, race_shader, state)
        b_trials.append(b)
        if b == oracle:
            b_match_oracle += 1
        elif b == inplace:
            b_match_inplace += 1

    distinct_b = len({tuple(t) for t in b_trials})
    return {
        "oracle_head": oracle[:4],
        "double_buffer_matches_oracle": a_ok,
        "single_buffer_trials": TRIALS,
        "single_buffer_match_oracle": b_match_oracle,
        "single_buffer_match_inplace": b_match_inplace,
        "single_buffer_distinct_outputs": distinct_b,
        "inplace_matches_oracle": inplace == oracle,
    }


if __name__ == "__main__":
    import json
    import sys
    sys.path.insert(0, "/home/jericho/projects/zion/projects/visual_audio")
    print(json.dumps(run_probe(), indent=2))
