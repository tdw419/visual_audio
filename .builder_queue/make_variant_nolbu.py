"""Build variant = WIP minus the DEFECT-16c LBU/LHU hunks.

Answers: does the BK-11 coreutils gate actually NEED the LBU/LHU PUSH/POP
hunk (the one that regresses BK-1 leg2)?
"""
import re
import sys

wip = open("/tmp/rv64i_wip.py").read()

# strip the LBU/LHU push blocks (f-string based) and their pop blocks
txt = wip
push_block = '''                _pop = [r for r in (28, 29, 30) if r != rd]
                for _r in (28, 29, 30):
                    lines.append(f"PUSH r{_r}")
'''
pop_block = '''                for _r in reversed(_pop):
                    lines.append(f"POP r{_r}")
'''
print("push blocks:", txt.count(push_block), "pop blocks:", txt.count(pop_block))
txt = txt.replace(push_block, "")
txt = txt.replace(pop_block, "")

open("tools/rv64i_to_glyph.py", "w").write(txt)
print("wrote variant 'no-LBU/LHU'")
