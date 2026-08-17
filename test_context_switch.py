import sys

sys.path.insert(0, "tools")
from glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2, GlyphCPUv2


def assemble(path, assembler, cols_instrs=64):
    with open(path, "r") as f:
        raw_lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    labels = {}
    instr_count = 0
    for line in raw_lines:
        if line.startswith(':'):
            labels[line.split()[0]] = instr_count
        else:
            instr_count += 1

    resolved = []
    for line in raw_lines:
        if line.startswith(':'):
            continue
        for label, idx in labels.items():
            if label in line:
                line = line.replace(label, f"{idx % cols_instrs},{idx // cols_instrs}")
        resolved.append(line)

    return assembler.assemble(resolved, width_instrs=cols_instrs)


def main():
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=64)
    cpu.memory = [0] * 2048

    pixels = assemble("context_switch.glyph", assembler)
    cpu.pc = (0, 0)
    cpu.running = True

    for _ in range(500):
        if cpu.step(pixels) is False:
            break

    print(f"PRT output sequence: {cpu.output}")
    print(f"final counter in WCB memory[108] = {cpu.memory[108]}")

    # The whole point: the counter must climb 1 -> 2 -> 3 across three
    # *separate* CALLs into the window, not reset each time (which would
    # mean the window has no real persisted state) and not skip (which
    # would mean CALL/RET didn't actually round-trip).
    assert cpu.output == [1, 2, 3], f"expected [1, 2, 3], got {cpu.output}"
    assert cpu.memory[108] == 3, f"expected final counter 3, got {cpu.memory[108]}"

    print("All assertions passed: window state genuinely persists across separate CALL/RET dispatches.")


if __name__ == "__main__":
    main()
