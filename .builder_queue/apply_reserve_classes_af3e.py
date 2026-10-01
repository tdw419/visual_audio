import re
from pathlib import Path
p = Path("systems/GLYPH_BACKLOG.md")
s = p.read_text()

# Add reserve-class labels to the five stale open rows (BK-53/54/55/57/60).
# Classes per DECISION_RULES.md §3:
#   BK-53: E-K1 hijack oracle-side — receipt chain says CLOSED by fence family (BK-40/41); needs re-verify + resolution tail, not a new decision -> class (a) verify-and-resolve
#   BK-54: ring saturation — quantified failure mode in receipt; policy choice bounded by precedent -> class (a)
#   BK-55: twin hijack residual — largely closed by BK-50/77; verify twin-side then resolve -> class (a) verify-and-resolve
#   BK-57: twin tile-LD divergence — parity-leak class with landed precedent (BK-51/77 consult patterns) -> class (a)
#   BK-60: paged-walker posture — gated vs documented-readable, has covering receipt -> class (a)
labels = {
    "BK-53": ("class (a) — verify-and-resolve: oracle-side chain measured DEAD at HEAD "
              "(BK-77 row cites probe stdout md5 8a8bcb6f 'CONFIRMED DEAD'); remaining work is "
              "re-verify + write RESOLUTION tail, no new decision needed (DECISION_RULES.md §3)"),
    "BK-54": ("class (a) — posture decision decidable from receipt + precedent: cursor bound "
              "policy; covering receipt quantifies the unbounded-append failure mode "
              "(DECISION_RULES.md §3/§6 — auto-claimable, file directive from receipt)"),
    "BK-55": ("class (a) — verify-and-resolve: twin residual closed by BK-77's box_confirmed() "
              "scope widening; re-run probe_wgsl_mmio_read/ek1 shapes at HEAD, write RESOLUTION "
              "tail (DECISION_RULES.md §3)"),
    "BK-57": ("class (a) — parity-leak class with landed precedent (twin gains the consult, "
              "BK-51/BK-77 pattern; DECISION_RULES.md §4 row 'Engine divergence, twin leaks'); "
              "auto-claimable — file directive from the measured divergence receipt"),
    "BK-60": ("class (a) — posture decision (gated vs documented-readable) with covering "
              "research receipt; precedent BK-56 decides the gated branch (DECISION_RULES.md "
              "§4 'Guest READ of kernel config words'); auto-claimable"),
}
count = 0
for bk, label in labels.items():
    # find the row's STATUS line and append the class marker inside it
    m = re.search(r"(## %s —.*?)- STATUS: open \((.*?)\)\n" % bk, s, re.S)
    if not m:
        print("MISS", bk); continue
    old = m.group(0)
    new = old.rstrip("\n")[:-1]  # drop trailing ')'
    new += f"; RESERVE CLASS: {label})\n"
    s = s.replace(old, new, 1)
    count += 1
p.write_text(s)
print("labeled:", count)
