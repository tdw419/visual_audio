import sys

sys.path.insert(0, "tools")
from glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2
from glyph_wgpu_bridge import assemble_with_labels, decode_program, run_shader_model


def main():
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)

    pixels, n_instrs, labels = assemble_with_labels("spatial_coordinator.glyph", assembler)
    program = decode_program(pixels, op_map, n_instrs)
    print(f"Decoded {len(program)} instructions for the WGSL numeric buffer.")

    data_memory = [0] * 2048
    data_memory[100] = 1   # WCB0 active
    data_memory[106] = labels[':window_tick0']  # TICK_ADDR — linear index, this shader's pc convention
    data_memory[108] = 0   # WCB1 empty
    data_memory[116] = 1   # WCB2 active
    data_memory[122] = labels[':window_tick2']  # TICK_ADDR
    data_memory[124] = 0   # WCB3 empty

    # spatial_coordinator.glyph loops forever (:reset_loop -> JMP :main_loop),
    # so cap steps to a budget known from test_spatial_coordinator.py to
    # cover several full passes, then check accumulated tick counts rather
    # than waiting for a HALT that never comes in normal operation.
    result = run_shader_model(program, data_memory, max_steps=6000)

    print(f"WCB0 tick counter (mem[107]) = {data_memory[107]}")
    print(f"WCB1 tick counter (mem[115]) = {data_memory[115]}")
    print(f"WCB2 tick counter (mem[123]) = {data_memory[123]}")
    print(f"WCB3 tick counter (mem[131]) = {data_memory[131]}")

    # Same invariants test_spatial_coordinator.py verifies against the real
    # GlyphCPUv2 interpreter: this proves the WGSL shader's *semantics*
    # (mirrored here line-for-line) reproduce the already-execution-verified
    # scheduler behavior, independent of whether the GPU itself can run it
    # in this sandbox.
    assert data_memory[107] > 0, "WCB0 was never dispatched by the shader-model"
    assert data_memory[123] > 0, "WCB2 was never dispatched by the shader-model"
    # A fixed step budget (unlike the wrap-counting used in
    # test_spatial_coordinator.py) can cut off mid-pass, so WCB0 (ticked
    # earlier in the loop) may be exactly one ahead of WCB2 at the
    # boundary. More than a 1-tick gap would mean the round-robin isn't
    # actually fair.
    assert abs(data_memory[107] - data_memory[123]) <= 1, (
        "active WCBs should tick at the same rate (±1 for step-budget cutoff) in a fair round-robin, "
        f"got WCB0={data_memory[107]} vs WCB2={data_memory[123]}"
    )
    assert data_memory[115] == 0, "empty WCB1 was dispatched — STATE check broken in shader model"
    assert data_memory[131] == 0, "empty WCB3 was dispatched — STATE check broken in shader model"

    print("All assertions passed: glyph_coordinator.wgsl's mirrored semantics reproduce the "
          "verified scheduler behavior. NOTE: this does not confirm actual GPU execution — "
          "device.queue.submit() hangs in this sandbox (confirmed 2026-08-16); only naga "
          "structural validation and this semantic mirror have been checked.")


if __name__ == "__main__":
    main()
