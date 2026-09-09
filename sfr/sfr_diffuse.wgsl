// SFR -- field diffusion on the GPU.  Mirrors sfr_reference.py::SFR._diffuse :
// a coarse-to-fine mip cascade of edge-corrected 5-point Jacobi sweeps with
// well re-pinning at every level.  Single-channel f32 (R32); written so that
// swapping f32 -> vec4<f32> later (per-destination fields) is a local change.
//
// Buffers are 1-D, row-major, one per mip level.  The driver picks in/out
// buffers per call and updates `u` (size / scale / nwells) each dispatch.
//
//   restrict   : lvl[i]  (size 2S) -> lvl[i+1] (size S)   2x2 mean
//   jacobi     : lvl[li] -> scratch                        one sweep
//                (driver copies scratch back with copy_buffer_to_buffer)
//   repin      : lvl[li][well/scale] = WELL
//   prolongate : lvl[li] (size S) -> lvl[li-1] (size 2S)   2x2 replicate

override WELL : f32 = 1.0;

struct U { size: u32, scale: u32, nwells: u32, _pad: u32 };

// 4 channels/cell = 4 independent per-destination fields, blurred together.
@group(0) @binding(0) var<storage, read>        src   : array<vec4<f32>>;
@group(0) @binding(1) var<storage, read_write>  dst   : array<vec4<f32>>;
@group(0) @binding(2) var<storage, read>        wells : array<vec4<u32>>;  // x,y,chan,_
@group(0) @binding(3) var<uniform>              u     : U;

@compute @workgroup_size(8, 8)
fn restrict_level(@builtin(global_invocation_id) g: vec3<u32>) {
  let S = u.size;                 // coarse size
  if (g.x >= S || g.y >= S) { return; }
  let F = S * 2u;                 // fine size
  let x0 = g.x * 2u; let y0 = g.y * 2u;
  let a = src[y0 * F + x0];
  let b = src[y0 * F + x0 + 1u];
  let c = src[(y0 + 1u) * F + x0];
  let d = src[(y0 + 1u) * F + x0 + 1u];
  dst[g.y * S + g.x] = (a + b + c + d) * 0.25;
}

@compute @workgroup_size(8, 8)
fn jacobi(@builtin(global_invocation_id) g: vec3<u32>) {
  let S = u.size;
  if (g.x >= S || g.y >= S) { return; }
  let i = g.y * S + g.x;
  var acc = src[i];
  var nb  = 1.0;
  if (g.y > 0u)      { acc = acc + src[i - S]; nb = nb + 1.0; }
  if (g.y + 1u < S)  { acc = acc + src[i + S]; nb = nb + 1.0; }
  if (g.x > 0u)      { acc = acc + src[i - 1u]; nb = nb + 1.0; }
  if (g.x + 1u < S)  { acc = acc + src[i + 1u]; nb = nb + 1.0; }
  dst[i] = acc / nb;
}

@compute @workgroup_size(64)
fn repin(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= u.nwells) { return; }
  let w = wells[g.x];
  let cx = w.x / u.scale;
  let cy = w.y / u.scale;
  var v = dst[cy * u.size + cx];
  v[w.z] = WELL;                       // pin only this well's channel
  dst[cy * u.size + cx] = v;
}

@compute @workgroup_size(8, 8)
fn prolongate(@builtin(global_invocation_id) g: vec3<u32>) {
  let F = u.size;                 // fine size
  if (g.x >= F || g.y >= F) { return; }
  let S = F / 2u;                 // coarse size
  dst[g.y * F + g.x] = src[(g.y / 2u) * S + (g.x / 2u)];
}

// coarse-grid subtract: dst = dst - src   (both `u.size` square)
@compute @workgroup_size(8, 8)
fn sub_inplace(@builtin(global_invocation_id) g: vec3<u32>) {
  let S = u.size;
  if (g.x >= S || g.y >= S) { return; }
  let i = g.y * S + g.x;
  dst[i] = dst[i] - src[i];
}

// V-cycle correction: dst_fine += upsample(src_coarse)   (dst is `u.size` square)
@compute @workgroup_size(8, 8)
fn prolong_add(@builtin(global_invocation_id) g: vec3<u32>) {
  let F = u.size;                 // fine size
  if (g.x >= F || g.y >= F) { return; }
  let S = F / 2u;                 // coarse size
  dst[g.y * F + g.x] = dst[g.y * F + g.x] + src[(g.y / 2u) * S + (g.x / 2u)];
}
