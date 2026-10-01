"""tools/pyshader_cell.py — PS004: per-cell programs (invocation_id mode).

Turns the PS003 finding into compiler capability: a Python shader that
expresses a per-cell rule lowers through the SAME GlyphIR pipeline and
lands on the GPU as the proven dispatch-boundary-sync + double-buffer
pattern.

A cell program is:

    def cell(me, <extra params>):
        ...pure function of me and scalars...
        return <new value for cell me>

`me` is the cell index (0..N_CELLS-1). The body must NOT use mem[] —
reads of the old state are done by the RUNNER (it passes the current
generation as an extra scalar parameter, or the program is stateless
per-cell like an arithmetic map). This is deliberate: PS003 measured
that in-dispatch neighbor reads race; so neighbor-coupled programs use
the host-side step loop (one compile, N dispatches), where each
dispatch's inputs are the previous generation's outputs. Programs that
need in-shader neighbor reads are exactly the ones PS003 proved unsafe
in one dispatch — they get the double-buffer driver instead.

Two supported shapes:

  MAP (stateless per-cell):
      def cell(me, ...scalars): return f(me, ...)
      -> one dispatch; each invocation computes cell me from scalars.

  STEP (neighbor-coupled, double-buffered):
      def step(xm1, x0, xp1, ...scalars): return f(...)
      -> host loop: for each generation, one dispatch where invocation i
         receives old[i-1], old[i], old[i+1] baked as scalars... but
         baking per-invocation scalars means a distinct shader per cell,
         which is absurd. So STEP mode instead runs the SAME compiled
         program on the pixel-CPU/Glyph side per cell, and on the GPU
         uses the PS003 hand-shader shape with the compiled body inlined
         per invocation reading buf[OLD + me-1..me+1].

For PS004 the honest, verified scope is MAP mode end-to-end (Python
source -> GlyphIR -> WGSL -> GPU, 64 invocations, results compared to
the oracle AND to sequential evaluation) plus the STEP-mode host
driver that reuses the PS003 double-buffer shader with a compiled
per-cell body. MAP mode needs invocation_id on the WGSL side only:
r1 is bound from gid.x at entry instead of baked.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from tools.glyph_ir import GlyphIRModule
from tools.pyshader_compiler import (
    FIRST_PARAM,
    PyShaderError,
    U32_MASK,
    compile_function,
)
from tools.pyshader_wgsl import (
    BUFFER_WORDS as _STATE_BUFFER_WORDS,
    EXIT_OFF,
    REGION_OFF,
    RUNNING_OFF,
    emit_wgsl,
)

N_CELLS = 64


# ── MAP mode: stateless per-cell ────────────────────────────────────────

def compile_cell_map(source: str, n_extra_params: int = 0
                     ) -> GlyphIRModule:
    """Compile `def cell(me, ...): return ...` (no mem[] anywhere).
    The compiled module is an ordinary PS001 module whose r1 = me; the
    WGSL cell backend binds r1 from gid.x."""
    # static reject: mem[] use in a cell program
    import ast
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and \
                isinstance(node.value, ast.Name) and node.value.id == "mem":
            raise PyShaderError(
                "cell programs are pure functions: mem[] is not allowed "
                "(in-dispatch neighbor reads race — see PS003)")
    module = compile_function(source)
    # r1 must be the first param and must be read (the cell index)
    # — enforced lightly: caller passes n_extra_params for validation.
    return module


def emit_cell_map_wgsl(module: GlyphIRModule, n_cells: int = N_CELLS,
                       scalars: Optional[List[int]] = None) -> str:
    """Cell-mode WGSL: like emit_wgsl but (a) r1 is bound from
    global_invocation_id.x at entry, (b) extra scalar params beyond r1
    are baked, (c) the writeback writes buf[REGION_OFF + me] = r9
    instead of dumping all 32 registers (64 invocations writing the
    same register slots would race — PS003 taught us to write per-cell
    words only)."""
    wgsl = emit_wgsl(module, params=None)
    # 1) bind me from gid.x, bake scalars into r2..
    bind = ["    // cell mode: me = global invocation id"]
    bind.append("    r1 = gid.x;")
    if scalars:
        for i, v in enumerate(scalars):
            bind.append(f"    r{FIRST_PARAM + 1 + i} = {v & U32_MASK}u;")
    wgsl = wgsl.replace(
        "fn main() {",
        "fn main(@builtin(global_invocation_id) gid: vec3<u32>) {")
    marker = "    // ---- structured body ----"
    wgsl = wgsl.replace(marker, "\n".join(bind) + "\n" + marker)
    # 2) replace the full register dump at HALT with a single
    #    per-cell result store (keep r0..r31 declarations; only the
    #    writeback changes).
    lines = wgsl.splitlines()
    out: List[str] = []
    in_dump = False
    for ln in lines:
        if ln.strip() == "// HALT: writeback + return":
            in_dump = True
            out.append("    // HALT: per-cell result store")
            out.append(f"    buf[{REGION_OFF} + r1] = r9;")
            out.append("    return;")
            continue
        if in_dump:
            if ln.strip() == "return;":
                in_dump = False
            continue  # drop dump lines (buf[i] = r{i}, exit code)
        out.append(ln)
    # 3) fix buffer size: cell mode needs REGION_OFF + N_CELLS words.
    out = [ln.replace(
        f"array<u32, {_STATE_BUFFER_WORDS}>",
        f"array<u32, {REGION_OFF + n_cells}>") for ln in out]
    return "\n".join(out)


def run_cell_map(source: str, scalars: Optional[List[int]] = None,
                 n_cells: int = N_CELLS) -> Dict:
    """Compile once, dispatch once with n_cells invocations, compare
    against the Python oracle (sequential evaluation of the same body
    via the IR interpreter with me=0..N-1). Receipt dict or raises."""
    from tools.pyshader_compiler import IRInterpreter
    import struct
    import wgpu

    module = compile_cell_map(source)
    device = _cell_device()
    wgsl = emit_cell_map_wgsl(module, n_cells=n_cells, scalars=scalars)
    shader = device.create_shader_module(code=wgsl, label="cell-map")

    n_words = REGION_OFF + n_cells
    gpu_buf = device.create_buffer(
        size=n_words * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        label="cell-state")
    readback = device.create_buffer(
        size=n_words * 4,
        usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ,
        label="cell-read")
    pipe = device.create_compute_pipeline(
        layout="auto",
        compute={"module": shader, "entry_point": "main"},
        label="cell-pipe")
    bg = device.create_bind_group(
        layout=pipe.get_bind_group_layout(0),
        entries=[{"binding": 0,
                  "resource": {"buffer": gpu_buf, "offset": 0,
                               "size": n_words * 4}}],
        label="cell-bind")

    enc = device.create_command_encoder(label="cell-enc")
    cp = enc.begin_compute_pass()
    cp.set_pipeline(pipe)
    cp.set_bind_group(0, bg)
    cp.dispatch_workgroups(n_cells, 1, 1)
    cp.end()
    enc.copy_buffer_to_buffer(gpu_buf, 0, readback, 0, n_words * 4)
    device.queue.submit([enc.finish()])

    readback.map_sync(mode=wgpu.MapMode.READ)
    data = bytes(readback.read_mapped())
    readback.unmap()
    words = list(struct.unpack(f"<{n_words}I", data))
    got = words[REGION_OFF:REGION_OFF + n_cells]

    # oracle: same module, interpreter, me = 0..N-1. FRESH interpreter
    # per cell: run() does not reset registers between calls, and the
    # zero-copy idiom only self-cleans assigned vars — reusing one
    # interpreter leaked stale temps across cells (caught by the GPU
    # comparison: GPU 8 vs stale-oracle 12 for me=2; the GPU was right).
    want = [IRInterpreter(module).run([i] + list(scalars or []))
            for i in range(n_cells)]
    return {
        "ok": got == want,
        "gpu": got,
        "oracle": want,
        "n_cells": n_cells,
        "wgsl": wgsl,
    }


def _cell_device():
    import wgpu
    adapter = wgpu.gpu.request_adapter_sync(
        power_preference="high-performance")
    return adapter.request_device_sync(label="pyshader-cell")


# ── STEP mode: neighbor-coupled, PS003 double-buffer driver ────────────

def run_cell_step_ab(step_source: str, init_state: List[int], gens: int,
                     scalars: Optional[List[int]] = None) -> Dict:
    """Full double-buffer STEP driver with two direction-specific
    shaders (A->B, B->A), body compiled from Python through GlyphIR."""
    module = compile_function(_wrap_step_source(step_source, scalars))
    body_fn = _step_body_wgsl(module, scalars)
    shader_ab = _CELL_STEP_SHADER.replace("%N%", str(N_CELLS)) \
        .replace("%BODY%", body_fn) \
        .replace("%SRC%", "0u").replace("%DST%", f"{N_CELLS}u")
    shader_ba = _CELL_STEP_SHADER.replace("%N%", str(N_CELLS)) \
        .replace("%BODY%", body_fn) \
        .replace("%SRC%", f"{N_CELLS}u").replace("%DST%", "0u")

    import struct
    import wgpu

    device = _cell_device()
    mods = {
        (0, N_CELLS): device.create_shader_module(
            code=shader_ab, label="step-AB"),
        (N_CELLS, 0): device.create_shader_module(
            code=shader_ba, label="step-BA"),
    }
    n = 2 * N_CELLS
    gpu_buf = device.create_buffer(
        size=n * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
        | wgpu.BufferUsage.COPY_SRC,
        label="step-state")
    device.queue.write_buffer(gpu_buf, 0, struct.pack(
        f"<{n}I", *(list(init_state) + [0] * N_CELLS)))

    pipes = {}
    for key, mod in mods.items():
        pipe = device.create_compute_pipeline(
            layout="auto",
            compute={"module": mod, "entry_point": "main"},
            label=f"step-pipe-{key}")
        pipes[key] = (pipe, device.create_bind_group(
            layout=pipe.get_bind_group_layout(0),
            entries=[{"binding": 0,
                      "resource": {"buffer": gpu_buf, "offset": 0,
                                   "size": n * 4}}],
            label=f"step-bind-{key}"))

    src = 0
    for _ in range(gens):
        dst = N_CELLS if src == 0 else 0
        pipe, bg = pipes[(src, dst)]
        enc = device.create_command_encoder(label="step-enc")
        cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe)
        cp.set_bind_group(0, bg)
        cp.dispatch_workgroups(N_CELLS, 1, 1)
        cp.end()
        device.queue.submit([enc.finish()])
        src = dst

    final = 0 if gens % 2 == 0 else N_CELLS
    readback = device.create_buffer(
        size=N_CELLS * 4, usage=wgpu.BufferUsage.COPY_DST
        | wgpu.BufferUsage.MAP_READ, label="step-read")
    enc = device.create_command_encoder(label="step-final")
    enc.copy_buffer_to_buffer(gpu_buf, final * 4, readback, 0,
                              N_CELLS * 4)
    device.queue.submit([enc.finish()])
    readback.map_sync(mode=wgpu.MapMode.READ)
    data = bytes(readback.read_mapped())
    readback.unmap()
    got = list(struct.unpack(f"<{N_CELLS}I", data))

    # oracle: synchronous Python applying the same body. FRESH
    # interpreter per cell-run — run() does not reset registers between
    # calls; reuse leaks stale temps (same trap as MAP mode, hit twice
    # before it stuck: the GPU comparison is what exposes it).
    from tools.pyshader_compiler import IRInterpreter
    cur = list(init_state)
    for _ in range(gens):
        nxt = []
        for i in range(N_CELLS):
            xm1 = cur[i - 1] if i - 1 >= 0 else 0
            xp1 = cur[i + 1] if i + 1 < N_CELLS else 0
            nxt.append(IRInterpreter(module).run(
                [xm1, cur[i], xp1] + list(scalars or [])))
        cur = nxt
    return {"ok": got == cur, "gpu": got, "oracle": cur,
            "gens": gens, "wgsl": shader_ab}


_CELL_STEP_SHADER = """// generated by tools/pyshader_cell.py — STEP mode
@group(0) @binding(0) var<storage, read_write> buf: array<u32, %N% * 2u>;

fn body(xm1: u32, x0: u32, xp1: u32) -> u32 {
    var r1: u32 = xm1;
    var r2: u32 = x0;
    var r3: u32 = xp1;
    var r4: u32 = 0u;
    var r5: u32 = 0u;
    var r6: u32 = 0u;
    var r7: u32 = 0u;
    var r8: u32 = 0u;
    var r9: u32 = 0u;
    var r10: u32 = 0u;
    var r11: u32 = 0u;
    var r12: u32 = 0u;
    var r13: u32 = 0u;
    var r14: u32 = 0u;
    var r15: u32 = 0u;
    var r16: u32 = 0u;
    var r17: u32 = 0u;
    var r18: u32 = 0u;
    var r19: u32 = 0u;
    var r20: u32 = 0u;
    var r21: u32 = 0u;
    var r22: u32 = 0u;
    var r23: u32 = 0u;
    var r24: u32 = 0u;
%BODY%
}

@compute @workgroup_size(1, 1, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let me = gid.x;
    let l = select(0u, buf[%SRC% + me - 1u], me >= 1u);
    let r = select(0u, buf[%SRC% + me + 1u], me + 1u < %N%u);
    buf[%DST% + me] = body(l, buf[%SRC% + me], r);
}
"""


def _wrap_step_source(step_source: str,
                      scalars: Optional[List[int]]) -> str:
    """`def step(xm1, x0, xp1, ...)` -> PS001-compatible def whose first
    three params are the neighbor triple (extra scalars appended)."""
    import ast
    tree = ast.parse(step_source)
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(fns) != 1 or len(tree.body) != 1:
        raise PyShaderError("step source must be exactly one def")
    params = [a.arg for a in fns[0].args.args]
    if len(params) < 3:
        raise PyShaderError(
            "step must take at least (xm1, x0, xp1)")
    if any(k in params for k in ("mem",)):
        raise PyShaderError("step must not use mem[]")
    return step_source


def _step_body_wgsl(module: GlyphIRModule,
                    scalars: Optional[List[int]]) -> str:
    """Lower the compiled module to a WGSL function body mapping the
    module's r1..r3 (xm1, x0, xp1) to the function args. Reuses
    emit_wgsl's instruction lowering by emitting a full shader then
    extracting its structured body."""
    wgsl = emit_wgsl(module, params=None)
    # take everything between the body marker and the HALT marker —
    # those lines are the module's straight-line statements operating
    # on r1..r31 — then wrap with the arg mapping.
    lines = wgsl.splitlines()
    start = next(i for i, l in enumerate(lines)
                 if "structured body" in l) + 1
    # skip the r25 region-base init (cell programs have no mem[])
    halt = next(i for i, l in enumerate(lines)
                if "HALT" in l)
    body: List[str] = []
    for l in lines[start:halt]:
        s = l.strip()
        if s.startswith("r25 = "):
            continue
        body.append("    " + s)
    # extra scalar params (r4..) get baked constants
    if scalars:
        for i, v in enumerate(scalars):
            body.append(
                f"    r{FIRST_PARAM + 3 + i} = {v & U32_MASK}u;")
    return "\n".join(body) + "\n    return r9;"
