"""append_bk32_af3e.py - append the BK-32 backlog row (research landing, rule 5/6).
Run from repo root: python3 .builder_queue/append_bk32_af3e.py
"""
from pathlib import Path

p = Path('systems/GLYPH_BACKLOG.md')
t = p.read_text()
assert '| BK-32 ' not in t, 'BK-32 already present'
row = ("| BK-32 | **SW lowering: add the VALUE-side aliasing guard (rs2==x30 stores the ADDRESS, rs2==x29 stores the shift amount)** — the SW lowering's unguarded path (rs1 not in {29,30}) reads the value operand at `ST` time, AFTER the r30 address temp and the r29 shift scratch have been written (identity map: r30==RV x30, r29==RV x29). Measured at HEAD f4fe2946 (probe `.builder_queue/dbg_d31h_sw_value_side_alias_af3e.py`, 7 legs via the proven d31f harness, tree==HEAD lowering identical per pc, deterministic across 3 runs, all REDs silent halted=True faulted=False): sw x30,0(x18) -> mem[768]=0x300 (stores the ADDRESS) RED; sw x30,4(x18) -> 0x0 with word 769=0x301 (address INTO address slot — self-overwrite corruption beyond wrong-value) RED; sw x30,0(x0) -> 0x0 (stores base 0) RED; sw x29,0(x18) -> 0x2 (stores the shift amount) RED; controls (sw x9 normal; sw x9 base-x30 DEFECT-31 fix path; sw x30,0(x30) via fix path = 0xC00 PASS — the C07 pass fully attributes BK-31's confounded L03 to this class). Latent-only: no landed gate known to store x29/x30 as a VALUE through an unguarded base. Fix shape = DEFECT-31/DEFECT-30 PUSH/POP pattern on the value operand when rs2 in {29,30}; gate `tests/test_defect31h_sw_value_aliasing.py` RED-first + non-vacuity leg (neuter guard -> RED); worktree isolation (engine-core transpiler) per AGENTS.md | systems/GLYPH_BACKLOG.md | tools/rv64i_to_glyph.py:913-962 (SW unguarded path) | `.builder_queue/RESEARCH_defect31h_sw_value_side_aliasing.md` (2026-09-26, builder af3e62239ce2) |\n")
t = t.rstrip('\n') + '\n' + row
p.write_text(t)
print('appended; BK-32 rows now:', t.count('| BK-32 '))
