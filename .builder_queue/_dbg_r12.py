"""Debug the fleet-image PC-35x stall. Throwaway — replicates the two-pass flow."""
import sys
for p in ('.', 'tools'):
    if p not in sys.path:
        sys.path.insert(0, p)

import tools.glyph_gpt.agent_resident as ar
from rv64i_to_glyph import assemble_glyph_to_pixels as ag2p

mode = 'fleet'

# pass 1 text (empty globals -> placeholder PCs, exactly like production)
txt1 = ar._resident_kernel_program_text(mode, ar.RES_STATUS_WORD, 6)
for phase in range(len(ar.RES_FLEET_BOXES)):
    txt1 = txt1.replace(f"__FLEET_ENTER_{phase}", "LDI r30 0", 1)
_, coords1 = ag2p(txt1, cols_instrs=8, min_rows=16)

def packed(lbl):
    c, r = coords1[lbl]
    return (c & 0xFFFF) | ((r & 0xFFFF) << 16)

ar._FLEET_COORDS.update(coords1)
ar._RES_FLEET_LEG0_PC = packed(":__fleg0")
for phase in range(len(ar.RES_FLEET_BOXES)):
    ar._RES_FLEET_BODIES[phase] = packed(f":__fleet_{phase}")

# pass 2 text
txt2 = ar._resident_kernel_program_text(mode, ar.RES_STATUS_WORD, 6)
for phase in range(len(ar.RES_FLEET_BOXES)):
    txt2 = txt2.replace(f"__FLEET_ENTER_{phase}",
                        f"LDI r30 {ar._RES_FLEET_BODIES[phase]}", 1)

lines = [l.strip() for l in txt2.splitlines() if l.strip() and not l.startswith('#')]
labels = {}
instrs = []
for l in lines:
    if l.startswith(':'):
        labels[l.split()[0]] = len(instrs)
    else:
        instrs.append(l)
inv = {v: k for k, v in labels.items()}
print('total instrs:', len(instrs))
for pc in (350, 353, 354, 355, 356, 357, 358, 359, 360, 361):
    print(pc, inv.get(pc, '-'), '|', instrs[pc] if pc < len(instrs) else 'OOB')
print('fleet labels:', {k: v for k, v in sorted(labels.items(), key=lambda kv: kv[1])
                        if k.startswith((':__f', ':__g18d', ':__fleet', ':__ksys', ':__g18f', ':__entry', ':__kmain'))})
print('LEG0_PC', ar._RES_FLEET_LEG0_PC, 'BODIES', ar._RES_FLEET_BODIES)
