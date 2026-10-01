"""Affordance check (non-gate, single runs): does the BK-76-twin refusal
generalize to the syscall path (OPCODE_SYSCALL executes, E-K2 vector, then
a handler-side ST to a locked vector word)?

H1a (BK-76-twin closed hole, sanity reproduction): handler ST to KSYS -> refusal.
H2 (proposed): handler PARS KSYS (fault vector word 8193) -> refusal or lands?
"""
import sys, tempfile, hashlib
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

WORD_KFAULT = 8193
WORD_KSYS = 8194
IDX = lambda w: w - 8192
PACKED_HANDLER = (0 << 16) | 3
TILE_SEED = {IDX(8280): 5, IDX(8281): 0, IDX(8282): 8, IDX(8283): 8}
FAULT_ADDR_MMIO_IDX = IDX(8199)

DISPATCHER_TEXT = (
    ":__entry\n"
    "SYSCALL r10 6\n"      # dispatch to ksys in SUPER
    "LDI r3 99\n"
    "HALT\n"
    "LDI r6 %d\n"          # handler start (SUPER) — payload value
    "LDI r7 %d\n"          # target vector word
    "ST r7 r6\n"           # the SUPER-window store under test
    "LDI r5 52\n"
    "PRT r5\n"
    "SYSRET\n"
)


def run_leg(name, target_word):
    import wgpu, wgpu.utils
    from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
    from tools.glyph_gpt.baker import bake_image
    from tools.glyph_gpt.runner import GlyphRunner
    from tools.glyph_isa_v2 import OpcodeMapV2

    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / f"{name}.png"
        bake_image(DISPATCHER_TEXT % (0xADF00D, target_word), cols_instrs=8,
                   out_path=png)
        image = GlyphRunner(png).image

    device = wgpu.utils.get_default_device()
    queue = device.queue
    n_pixels = image.shape[0] * image.shape[1]
    rgba = np.zeros((n_pixels, 4), dtype=np.uint32)
    rgba[:, 0:3] = image.reshape(n_pixels, 3)
    usage = (wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
             | wgpu.BufferUsage.COPY_SRC)
    cpu_state, cpu_dtype = make_cpu_state_array(1)
    cpu_state[0]["mode"] = 1
    mmio = np.zeros(160, dtype=np.uint32)
    mmio[IDX(WORD_KFAULT)] = 0
    mmio[IDX(WORD_KSYS)] = PACKED_HANDLER
    for k, v in TILE_SEED.items():
        mmio[k] = v
    ram = np.zeros(16384, dtype=np.uint32)
    dt = np.dtype([('image_width', np.uint32),
                   ('image_height', np.uint32),
                   ('output_buffer_size', np.uint32)])
    bufs = {}
    for nm, arr, extra in (
            ("img", rgba, 0), ("cpu", cpu_state, 0),
            ("out", np.zeros(256, np.uint32), 0), ("mmio", mmio, 0),
            ("u", np.array([(image.shape[1], image.shape[0], 64)], dt),
             wgpu.BufferUsage.UNIFORM), ("ram", ram, 0)):
        b = device.create_buffer(size=arr.nbytes, usage=usage | extra)
        queue.write_buffer(b, 0, arr.tobytes())
        bufs[nm] = b
    bgl = device.create_bind_group_layout(entries=[
        {'binding': i, 'visibility': wgpu.ShaderStage.COMPUTE,
         'buffer': {'type': 'storage' if i != 3 else 'uniform'}}
        for i in range(6)])
    bg = device.create_bind_group(layout=bgl, entries=[
        {'binding': 0, 'resource': {'buffer': bufs["img"], 'offset': 0,
                                    'size': rgba.nbytes}},
        {'binding': 1, 'resource': {'buffer': bufs["cpu"], 'offset': 0,
                                    'size': cpu_state.nbytes}},
        {'binding': 2, 'resource': {'buffer': bufs["out"], 'offset': 0,
                                    'size': 256}},
        {'binding': 3, 'resource': {'buffer': bufs["u"], 'offset': 0,
                                    'size': bufs["u"].size}},
        {'binding': 4, 'resource': {'buffer': bufs["mmio"], 'offset': 0,
                                    'size': mmio.nbytes}},
        {'binding': 5, 'resource': {'buffer': bufs["ram"], 'offset': 0,
                                    'size': ram.nbytes}}])
    sh = device.create_shader_module(code=build_shader(OpcodeMapV2()))
    pipe = device.create_compute_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[bgl]),
        compute={'module': sh, 'entry_point': 'main'})
    rb = None
    step = 0
    for step in range(1, 81):
        enc = device.create_command_encoder()
        p = enc.begin_compute_pass()
        p.set_pipeline(pipe)
        p.set_bind_group(0, bg)
        p.dispatch_workgroups(1)
        p.end()
        queue.submit([enc.finish()])
        rb = np.frombuffer(queue.read_buffer(bufs["cpu"]), dtype=cpu_dtype)[0]
        if rb['running'] == 0:
            break
    mmio_out = np.frombuffer(memoryview(queue.read_buffer(bufs["mmio"])),
                             dtype=np.uint32)
    out_words = [int(w) for w in np.frombuffer(
        queue.read_buffer(bufs["out"]), dtype=np.uint32) if w]
    return {
        "name": name,
        "halted": bool(rb['running'] == 0),
        "steps": step,
        "mode_final": int(rb['mode']),
        "target_word_val": int(mmio_out[IDX(target_word)]),
        "fault_addr_word": int(mmio_out[FAULT_ADDR_MMIO_IDX]),
        "output": out_words,
    }


if __name__ == "__main__":
    results = [
        run_leg("h1a_ksys_st_refusal", WORD_KSYS),
        run_leg("h2_kfault_pars", WORD_KFAULT),
    ]
    for r in results:
        print(r)
    print("RESULTS_MD5", hashlib.md5(
        repr(sorted(r.items() for r in results)).encode()).hexdigest())
