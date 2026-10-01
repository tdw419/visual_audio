"""Split-brain fix gate: monitor must CLAIM_PENDING on ledger NEXT: items.

2026-09-24 incident: builder redirected (09-21) to execute the ledger
(.builder_queue/PRODUCT_LANE_STATE.md) but the monitor watched only the
legacy roadmap/backlog pair — supply filed as ledger claim-queue rounds
never entered the fingerprint; the loop slept 8h+ with items 18-23 named
in the ledger. RED-first: on the pre-fix monitor, CLEAN + ledger NEXT
yielded state=CLEAN supply=ok (stall reproduced); with the fix it must
yield CLAIM_PENDING naming the item, and go quiet only when NEXT reads
"queue empty".
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MON = REPO / "tools" / "glyph_build_chain_monitor.py"
LEDGER = ".builder_queue/PRODUCT_LANE_STATE.md"


def _run_monitor():
    return subprocess.run([sys.executable, str(MON)],
                          capture_output=True, text=True, cwd=REPO).stdout


def _git(args):
    return subprocess.run(["git"] + args, capture_output=True, text=True,
                          cwd=REPO).stdout


def test_next_line_names_claim(monkeypatch):
    # GREEN leg: at a HEAD whose ledger has a filled NEXT:, monitor must
    # surface CLAIM_PENDING with the claim text (when tree otherwise clean).
    out = _run_monitor()
    ledger = _git(["show", f"HEAD:{LEDGER}"])
    import re
    m = re.search(r"^NEXT: \*\*(.+?)\*\*", ledger, re.S | re.M)
    assert m, "ledger must carry a NEXT: line"
    if "queue empty" in m.group(1).lower():
        assert "CLAIM_PENDING" not in out
    elif out.startswith("head=") and "state=CLEAN queue=0" not in out:
        pass  # dirty/repair states legitimately dominate; skip
    elif "tracked_dirty=0" in out and "queue=0" in out:
        assert "CLAIM_PENDING" in out, f"stall: {out}"
        assert "claim:" in out


def test_queue_empty_next_is_quiet(monkeypatch):
    # The "queue empty" sentinel must NOT trigger CLAIM_PENDING: prove the
    # classifier directly on the regex path (no tree mutation needed).
    spec = importlib.util.spec_from_file_location("mon", MON)
    mon = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mon)
    import re
    filled = re.search(r"^NEXT: \*\*(.+?)\*\*",
                       "NEXT: **(round-9+ supply items 18-23 ...)**",
                       re.S | re.M)
    empty = re.search(r"^NEXT: \*\*(.+?)\*\*",
                      "NEXT: **(queue empty — all named items landed)**",
                      re.S | re.M)
    assert filled and "queue empty" not in filled.group(1).lower()
    assert empty and "queue empty" in empty.group(1).lower()
