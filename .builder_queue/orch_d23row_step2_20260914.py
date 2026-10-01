import re

path = "/home/jericho/projects/zion/projects/visual_audio/systems/GLYPH_SELF_HOSTING_ROADMAP.md"
lines = open(path).readlines()
out = []
done = False
for line in lines:
    if not done and line.startswith("| DEFECT-23-ROOT |"):
        cells = line.rstrip("\n").split("|")
        cells[-2] = (
            "⏳ queued 2026-09-14 → step 2 LANDED 2026-09-14, commit `13d94a9` "
            "(orchestrator: delegated to agy exit 0/954 s from "
            "`.builder_queue/brief_defect23root_step2_window_tag.md`, every gate re-run "
            "on the merged tree; delegate defect found+repaired by orchestrator regression: "
            "two baker.py tag insertions clobbered r14/r15 before a dangling ST, killing "
            "GH-17 flat64k page-255 PTE — see commit body). Gate "
            "`tests/test_defect23_pte_acceptance.py` + pt_identity + pfn_ceiling: "
            "**10 passed / 2 xfailed (strict)**; probe still `SILENT_MISDIRECTION_CONFIRMED` "
            "on G2 (in-window slot case — open BY DESIGN per ruling); GH-17/25/par 29 "
            "passed/2 xfail; GH-21/23/18 (not live_smoke) 30 passed/1 desel. Receipt "
            "`systems/RECEIPT_DEFECT23ROOT_WINDOW_TAG.md` (RED tail + GREEN tails + "
            "does-NOT-prove). Row REMAINS OPEN pending step-3 decision: the in-window slot "
            "vector (G2/G3) is the residual root cause; closing it needs a seat ruling — "
            "left open rather than auto-claiming done."
        )
        out.append("|".join(cells) + "\n")
        done = True
    else:
        out.append(line)
assert done, "DEFECT-23-ROOT row not found"
open(path, "w").writelines(out)
print("updated")
