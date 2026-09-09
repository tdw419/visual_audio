// SFR -- Stigmergic Field Routing : GPU forward (routing) step.
// Mirrors sfr_reference.py::SFR._route bit-for-bit (Q16 fixed-point scoring,
// K deflection rounds, deterministic N/S/E/W tie-break, age guard).
//
// Field diffusion is NOT here -- it is verified separately with tolerance.
// This kernel consumes a read-only Q16 field snapshot and is fully integer,
// so GPU and CPU routing decisions are identical.
//
// Dispatch order per frame (driver-orchestrated, one dispatch each):
//   deliver
//   for r in 0..K_ROUNDS:  clear_claims ; claim_round(r) ; resolve ; apply_vacate
//   pick_oldest ; find_p ; displace          -- one forced move per frame
//   age_tick
//
// Grid is GRID x GRID, linear index = y*GRID + x, workgroups 8x8.

override GRID       : u32 = 64u;
override K_ROUNDS    : u32 = 3u;
override AGE_STRICT  : u32 = 24u;
override W_FIELD_Q   : i32 = 1;
override W_HILB_Q    : i32 = 1966;
override W_CONG_Q    : i32 = 16384;

// packet: vec4<u32> = (destX, destY, age, hp)  ; hp==0 => empty
// hp = hnd<<5 | chan<<3 | prio     (chan selects the field channel, 0..3)
@group(0) @binding(0) var<storage, read_write> pk       : array<vec4<u32>>;
// Q16 field snapshot (i32), 4 channels/cell, read-only for routing
@group(0) @binding(1) var<storage, read>       fieldq   : array<vec4<i32>>;
// hilbert index per cell, precomputed on host (guarantees curve match)
@group(0) @binding(2) var<storage, read>       hidx     : array<i32>;
// per-cell flags
@group(0) @binding(3) var<storage, read_write> placed   : array<u32>;   // moved/delivered this frame
@group(0) @binding(4) var<storage, read_write> settled  : array<u32>;   // cell holds a committed packet
@group(0) @binding(5) var<storage, read_write> claim    : array<atomic<u32>>; // per target: winner key
@group(0) @binding(6) var<storage, read_write> vacate   : array<u32>;   // src cells to clear after resolve
// round index + delivered counter
@group(0) @binding(7) var<storage, read_write> ctrl     : array<atomic<u32>>;
// ctrl[0]=round  [1]=delivered  [2]=oldest disp_key  [3]=P linear index

fn lin(x: u32, y: u32) -> u32 { return y * GRID + x; }

fn n4(k: u32) -> vec2<i32> {
  // N, S, E, W  -- must match _N4 in the reference
  switch k {
    case 0u: { return vec2<i32>( 0, -1); }
    case 1u: { return vec2<i32>( 0,  1); }
    case 2u: { return vec2<i32>( 1,  0); }
    default: { return vec2<i32>(-1,  0); }
  }
}

// score for stepping into neighbour cell (nx,ny), Q16; higher = better
fn score(nx: u32, ny: u32, dtar: i32, strict: bool, chan: u32) -> i32 {
  let wh = select(W_HILB_Q, 0, strict);
  let wc = select(W_CONG_Q, 0, strict);
  let ni = lin(nx, ny);
  let hterm = (wh * abs(hidx[ni] - dtar)) / i32(GRID * GRID);   // mul before div, match ref
  let cterm = wc * i32(settled[ni]);
  return W_FIELD_Q * fieldq[ni][chan] - hterm - cterm;
}

// ranked list of in-bounds neighbour directions, best first (score desc, then k asc)
fn ranked(x: u32, y: u32, dtar: i32, strict: bool, chan: u32,
          out: ptr<function, array<u32, 4>>) -> u32 {
  var sc : array<i32, 4>;
  var kk : array<u32, 4>;
  var m : u32 = 0u;
  for (var k: u32 = 0u; k < 4u; k = k + 1u) {
    let d = n4(k);
    let nx = i32(x) + d.x;
    let ny = i32(y) + d.y;
    if (nx < 0 || ny < 0 || nx >= i32(GRID) || ny >= i32(GRID)) { continue; }
    sc[m] = score(u32(nx), u32(ny), dtar, strict, chan);
    kk[m] = k;
    m = m + 1u;
  }
  // insertion sort: score desc, tie -> smaller k first
  for (var i: u32 = 1u; i < m; i = i + 1u) {
    let s0 = sc[i]; let k0 = kk[i];
    var j: i32 = i32(i) - 1;
    loop {
      if (j < 0) { break; }
      let better = (sc[j] < s0) || (sc[j] == s0 && kk[j] > k0);
      if (!better) { break; }
      sc[j + 1] = sc[j]; kk[j + 1] = kk[j];
      j = j - 1;
    }
    sc[j + 1] = s0; kk[j + 1] = k0;
  }
  for (var i: u32 = 0u; i < m; i = i + 1u) { (*out)[i] = kk[i]; }
  return m;
}

fn key_of(age: u32, src: u32) -> u32 {
  // older wins; then lower linear index wins  (matches (age, -srcIdx) in ref)
  return (age << 21u) | ((0x1FFFFFu) - src);
}

@compute @workgroup_size(8, 8)
fn deliver(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= GRID || g.y >= GRID) { return; }
  let i = lin(g.x, g.y);
  let p = pk[i];
  placed[i] = 0u;
  vacate[i] = 0u;
  settled[i] = select(0u, 1u, p.w != 0u);
  if (p.w != 0u && p.x == g.x && p.y == g.y) {
    pk[i] = vec4<u32>(0u);
    settled[i] = 0u;
    placed[i] = 1u;
    atomicAdd(&ctrl[1], 1u);
  }
}

@compute @workgroup_size(8, 8)
fn clear_claims(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= GRID || g.y >= GRID) { return; }
  let i = lin(g.x, g.y);
  atomicStore(&claim[i], 0u);
  vacate[i] = 0u;
}

@compute @workgroup_size(8, 8)
fn claim_round(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= GRID || g.y >= GRID) { return; }
  let i = lin(g.x, g.y);
  let p = pk[i];
  if (p.w == 0u || placed[i] != 0u) { return; }
  let r = atomicLoad(&ctrl[0]);
  let strict = p.z >= AGE_STRICT;
  let chan = (p.w >> 3u) & 3u;
  let dtar = hidx[lin(p.x, p.y)];
  var dirs : array<u32, 4>;
  let m = ranked(g.x, g.y, dtar, strict, chan, &dirs);
  if (r >= m) { return; }
  let d = n4(dirs[r]);
  let tx = u32(i32(g.x) + d.x);
  let ty = u32(i32(g.y) + d.y);
  let t = lin(tx, ty);
  if (settled[t] != 0u) { return; }
  // a strict packet never steps to lower-or-equal field: it waits here for
  // the forced-displacement phase instead of sustaining a deflection cycle.
  if (strict && fieldq[t][chan] <= fieldq[i][chan]) { return; }
  atomicMax(&claim[t], key_of(p.z, i));
}

@compute @workgroup_size(8, 8)
fn resolve(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= GRID || g.y >= GRID) { return; }
  let t = lin(g.x, g.y);
  let key = atomicLoad(&claim[t]);
  if (key == 0u) { return; }
  let src = (0x1FFFFFu) - (key & 0x1FFFFFu);
  pk[t] = pk[src];
  settled[t] = 1u;
  placed[t] = 1u;
  vacate[src] = 1u;
}

@compute @workgroup_size(8, 8)
fn apply_vacate(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= GRID || g.y >= GRID) { return; }
  let i = lin(g.x, g.y);
  if (vacate[i] != 0u) {
    pk[i] = vec4<u32>(0u);
    settled[i] = 0u;
  }
}

// ---- forced displacement: one packet per frame -------------------------------
// Guarantees the globally-oldest AGE_STRICT unplaced packet its steepest-
// descent move (into a free cell, else by swapping with the occupant).
// Single designated packet => race-free; provably livelock-free on a V-cycle
// field.  See SATURATION_LIVELOCK_NOTE.md.

fn disp_key(age: u32, hnd: u32) -> u32 {
  // (min(age,2047) << 20) | (0xFFFFF - hnd)   -- older, then lower hnd
  return (min(age, 2047u) << 20u) | (0xFFFFFu - (hnd & 0xFFFFFu));
}

@compute @workgroup_size(8, 8)
fn pick_oldest(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= GRID || g.y >= GRID) { return; }
  let i = lin(g.x, g.y);
  let p = pk[i];
  if (p.w == 0u || placed[i] != 0u || p.z < AGE_STRICT) { return; }
  atomicMax(&ctrl[2], disp_key(p.z, p.w >> 5u));
}

@compute @workgroup_size(8, 8)
fn find_p(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= GRID || g.y >= GRID) { return; }
  let i = lin(g.x, g.y);
  let p = pk[i];
  if (p.w == 0u || placed[i] != 0u || p.z < AGE_STRICT) { return; }
  if (disp_key(p.z, p.w >> 5u) == atomicLoad(&ctrl[2])) {
    atomicMin(&ctrl[3], i);         // handles are unique -> exactly one match
  }
}

@compute @workgroup_size(8, 8)
fn displace(@builtin(global_invocation_id) g: vec3<u32>) {
  let plin = atomicLoad(&ctrl[3]);
  if (plin == 0xFFFFFFFFu) { return; }        // no strict waiter this frame
  let i = lin(g.x, g.y);
  if (i != plin) { return; }                  // only P's cell acts
  let P = pk[i];
  let chan = (P.w >> 3u) & 3u;
  let dtar = hidx[i];
  var dirs : array<u32, 4>;
  ranked(g.x, g.y, dtar, true, chan, &dirs);  // rank-0 = max-field neighbour
  let d = n4(dirs[0]);
  let t = lin(u32(i32(g.x) + d.x), u32(i32(g.y) + d.y));
  if (settled[t] == 0u) {
    pk[t] = P;
    pk[i] = vec4<u32>(0u);
    settled[t] = 1u;  settled[i] = 0u;
    placed[t] = 1u;
  } else {
    let O = pk[t];                             // swap; both cells stay settled
    pk[t] = P;
    pk[i] = O;
    placed[t] = 1u;  placed[i] = 1u;
  }
}

@compute @workgroup_size(8, 8)
fn age_tick(@builtin(global_invocation_id) g: vec3<u32>) {
  if (g.x >= GRID || g.y >= GRID) { return; }
  let i = lin(g.x, g.y);
  if (pk[i].w != 0u) {
    pk[i].z = pk[i].z + 1u;
  }
}
