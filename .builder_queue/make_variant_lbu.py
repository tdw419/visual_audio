"""Build variant transpiler files for the BK-11 hunk bisect.

variant "lbu": HEAD + only the DEFECT-16c LBU/LHU PUSH/POP hunks
               (drops the DEFECT-16/16b branch hunks).
Writes tools/rv64i_to_glyph.py in place; the caller restores from backup.
"""
import subprocess
import sys

head = subprocess.run(["git", "show", "HEAD:tools/rv64i_to_glyph.py"],
                      capture_output=True, text=True, check=True).stdout

LBU_PUSH = '''        elif op == OP_LBU:
            if rd != 0:
                _pop = [r for r in (28, 29, 30) if r != rd]
                for _r in (28, 29, 30):
                    lines.append(f"PUSH r{_r}")
'''
LBU_POP = '''                lines.append("LDI r29 0xff")
                lines.append(f"AND r{rd} r29")
                for _r in reversed(_pop):
                    lines.append(f"POP r{_r}")
'''
LHU_PUSH = '''        elif op == OP_LHU:
            if rd != 0:
                _pop = [r for r in (28, 29, 30) if r != rd]
                for _r in (28, 29, 30):
                    lines.append(f"PUSH r{_r}")
'''
LHU_POP = '''                lines.append("LDI r29 0xffff")
                lines.append(f"AND r{rd} r29")
                for _r in reversed(_pop):
                    lines.append(f"POP r{_r}")
'''

old_lbu = '        elif op == OP_LBU:\n            if rd != 0:\n'
old_lhu = '        elif op == OP_LHU:\n            if rd != 0:\n'
old_pop_b = '                lines.append("LDI r29 0xff")\n                lines.append(f"AND r{rd} r29")\n'
old_pop_h = '                lines.append("LDI r29 0xffff")\n                lines.append(f"AND r{rd} r29")\n'

txt = head
for old, new in ((old_lbu, LBU_PUSH), (old_lhu, LHU_PUSH),
                 (old_pop_b, LBU_POP), (old_pop_h, LHU_POP)):
    n = txt.count(old)
    if n != 1:
        sys.exit(f"anchor not unique ({n}): {old!r}")
    txt = txt.replace(old, new)

open("tools/rv64i_to_glyph.py", "w").write(txt)
print("wrote variant 'lbu' (HEAD + LBU/LHU hunks only)")
