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


def run_memcpy(src_addr, dst_addr, count, seed_values, cols_instrs=64):
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=cols_instrs)
    cpu.memory = [0] * 2048

    for i, v in enumerate(seed_values):
        cpu.memory[src_addr + i] = v

    pixels = assemble("memcpy.glyph", assembler, cols_instrs)

    cpu.registers[1] = src_addr
    cpu.registers[2] = dst_addr
    cpu.registers[3] = count
    cpu.pc = (0, 0)
    cpu.running = True

    for _ in range(count * 20 + 50):
        if cpu.step(pixels) is False:
            break

    return cpu


def main():
    seed = [11, 22, 33, 44, 55]
    cpu = run_memcpy(src_addr=200, dst_addr=300, count=len(seed), seed_values=seed)

    copied = [cpu.memory[300 + i] for i in range(len(seed))]
    print(f"src = {seed}")
    print(f"dst = {copied}")
    assert copied == seed, f"memcpy mismatch: expected {seed}, got {copied}"

    src_untouched = [cpu.memory[200 + i] for i in range(len(seed))]
    assert src_untouched == seed, "memcpy corrupted its own source region"

    # Zero-count copy must be a no-op and must not crash on CMP/JZ with count already 0.
    cpu2 = run_memcpy(src_addr=200, dst_addr=300, count=0, seed_values=[])
    assert cpu2.memory[300] == 0, "zero-count memcpy wrote something anyway"

    print("All assertions passed: memcpy.glyph correctly copies N words and leaves source intact.")


if __name__ == "__main__":
    main()
