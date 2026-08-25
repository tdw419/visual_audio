// Decode-tax isolation baseline: computes the EXACT same algorithm as
// multi_instance_rv32i.wgsl's assembled test program (sum 1..N per lane),
// same per-instance N value, same number of loop iterations - but as
// plain native WGSL with zero instruction fetch/decode. The only
// difference between this shader's time and the interpreter's time for
// the same workload IS the interpretation overhead - a measured number,
// not the asserted 15-30x from the external analysis.
@group(0) @binding(0)
var<storage, read_write> inputs: array<u32>;
@group(0) @binding(1)
var<storage, read_write> outputs: array<u32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) id: vec3<u32>) {
    let idx = id.x;
    if (idx >= arrayLength(&inputs)) {
        return;
    }
    let n = inputs[idx];
    var sum: u32 = 0u;
    var i: u32 = 1u;
    loop {
        if (i > n) {
            break;
        }
        sum = sum + i;
        i = i + 1u;
    }
    outputs[idx] = sum;
}
