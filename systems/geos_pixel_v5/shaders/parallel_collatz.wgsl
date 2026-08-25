// Stand-in for "many independent small interpreted programs running in
// parallel" - the SIMT-shaped alternative to the single-core RISC-V
// emulator (which runs one thread, sequential, branch-heavy: the worst
// case for a GPU). Each lane runs its own Collatz sequence to convergence
// - real, data-dependent branching and a variable-length loop per lane
// (some inputs take far more steps than others), which is a fair stand-in
// for divergent guest-program behavior, not an embarrassingly-parallel
// toy like vector add.
@group(0) @binding(0)
var<storage, read_write> data: array<u32>;

// dispatch_workgroups caps each dimension at 65535, so N > 65535*256 (~16.7M)
// needs a 2D dispatch grid. group_count_x lets us flatten (group_id.x,
// group_id.y) back into one linear index ourselves, since WGSL has no
// num_workgroups builtin.
struct Params { group_count_x: u32 }
@group(0) @binding(1)
var<uniform> params: Params;

// CPPM-style pressure counters (per "Integrating CPPM into PCM" -
// Computational Pressure Measurement for WebGPU/WGSL): one (sum, max) pair
// per workgroup - sum is real work done by that workgroup's lanes, max is
// the slowest lane's step count, i.e. the lockstep-serialized cost every
// lane in that workgroup pays if SIMT execution stalls the whole group on
// its longest branch path. The host sums these after readback:
// efficiency = sum(all sums) / (sum(all maxes) * workgroup_size)
// approximates SIMT utilization: 1.0 = no divergence cost, near 0 = mostly
// wasted lockstep waiting. This is a workgroup-granularity (256-wide)
// proxy, not a true per-hardware-warp (32/64-wide) measurement - WGSL has
// no portable subgroup/wave builtins in this toolchain, so real hardware
// divergence cost is likely somewhat lower than this pessimistic estimate.
// One slot per workgroup (not atomics) because naga's SPIR-V *importer*
// (the ShaderSource::SpirV path) doesn't support parsing atomic
// instructions back out of SPIR-V, even though it can compile WGSL
// atomics *into* SPIR-V - a real, narrow toolchain asymmetry.
@group(0) @binding(2)
var<storage, read_write> stats: array<vec2<u32>>;

var<workgroup> wg_steps: array<u32, 256>;

@compute @workgroup_size(256)
fn main(@builtin(workgroup_id) wid: vec3<u32>, @builtin(local_invocation_id) lid: vec3<u32>) {
    let flat_group = wid.y * params.group_count_x + wid.x;
    let idx = flat_group * 256u + lid.x;

    var steps: u32 = 0u;
    if (idx < arrayLength(&data)) {
        var n: u32 = data[idx];
        loop {
            if (n <= 1u) {
                break;
            }
            if (n % 2u == 0u) {
                n = n / 2u;
            } else {
                n = 3u * n + 1u;
            }
            steps = steps + 1u;
        }
        data[idx] = steps;
    }

    wg_steps[lid.x] = steps;
    workgroupBarrier();

    // Single lane per workgroup reduces the 256-element shared array -
    // cheap relative to the Collatz loop itself, and keeps the reduction
    // portable without subgroup builtins.
    if (lid.x == 0u) {
        var local_max: u32 = 0u;
        var local_sum: u32 = 0u;
        for (var i: u32 = 0u; i < 256u; i = i + 1u) {
            local_max = max(local_max, wg_steps[i]);
            local_sum = local_sum + wg_steps[i];
        }
        stats[flat_group] = vec2<u32>(local_sum, local_max);
    }
}
