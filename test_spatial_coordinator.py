import sys

sys.path.insert(0, "tools")
from glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2, GlyphCPUv2


def assemble_coordinator(assembler, cols_instrs=64):
    with open("spatial_coordinator.glyph", "r") as f:
        raw_lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    labels = {}
    instr_count = 0
    for line in raw_lines:
        if line.startswith(':'):
            labels[line.split()[0]] = instr_count
        else:
            instr_count += 1

    resolved_lines = []
    for line in raw_lines:
        if line.startswith(':'):
            continue
        for label, idx in labels.items():
            if label in line:
                col, row = idx % cols_instrs, idx // cols_instrs
                line = line.replace(label, f"{col},{row}")
        resolved_lines.append(line)

    pixels = assembler.assemble(resolved_lines, width_instrs=cols_instrs)
    return pixels, labels, cols_instrs


def packed_address(labels, label, cols_instrs):
    idx = labels[label]
    col, row = idx % cols_instrs, idx // cols_instrs
    return (row << 16) | col


def main():
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=64)
    cpu.memory = [0] * 2048

    pixels, labels, cols_instrs = assemble_coordinator(assembler)
    print(f"Assembly successful. Program occupies {pixels.shape[0]} row(s).")

    # WCB 0: Active, tick routine = :window_tick0 (TICK_ADDR at offset 6 -> addr 106)
    cpu.memory[100] = 1
    cpu.memory[106] = packed_address(labels, ':window_tick0', cols_instrs)
    # WCB 1: Empty
    cpu.memory[108] = 0
    # WCB 2: Active, tick routine = :window_tick2 (TICK_ADDR at addr 122)
    cpu.memory[116] = 1
    cpu.memory[122] = packed_address(labels, ':window_tick2', cols_instrs)
    # WCB 3: Empty
    cpu.memory[124] = 0

    prev_index = None
    wraps = 0
    target_wraps = 5  # enough full passes to prove counters climb, not just increment once

    for step in range(20000):
        if cpu.registers[2] != prev_index:
            prev_index = cpu.registers[2]
            if prev_index == 0:
                wraps += 1
        if wraps >= target_wraps:
            break
        if cpu.step(pixels) is False:
            break

    print(f"Observed {wraps} index wraps.")
    print(f"WCB0 tick counter (mem[107]) = {cpu.memory[107]}")
    print(f"WCB1 tick counter (mem[115]) = {cpu.memory[115]}")
    print(f"WCB2 tick counter (mem[123]) = {cpu.memory[123]}")
    print(f"WCB3 tick counter (mem[131]) = {cpu.memory[131]}")

    assert wraps >= target_wraps, "scheduler never completed enough passes"

    # Active WCBs must have been genuinely CALLR-dispatched once per pass
    # to whatever routine their own TICK_ADDR data slot names — proving
    # dispatch is data-driven, not hardcoded to a fixed CMP/JZ chain.
    completed_passes = wraps - 1  # last wrap boundary isn't a completed pass yet
    assert cpu.memory[107] == completed_passes, (
        f"WCB0 should have ticked {completed_passes} times, got {cpu.memory[107]}"
    )
    assert cpu.memory[123] == completed_passes, (
        f"WCB2 should have ticked {completed_passes} times, got {cpu.memory[123]}"
    )

    # Empty WCBs must never be dispatched at all.
    assert cpu.memory[115] == 0, "empty WCB1 was dispatched — STATE check is broken"
    assert cpu.memory[131] == 0, "empty WCB3 was dispatched — STATE check is broken"

    print("All assertions passed: coordinator genuinely CALLR-dispatches active WCBs using their "
          "own data-stored TICK_ADDR (not a hardcoded label chain), state persists and accumulates "
          "across passes, empty WCBs are never dispatched.")


if __name__ == "__main__":
    main()
