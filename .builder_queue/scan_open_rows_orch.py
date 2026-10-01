#!/usr/bin/env python3
"""DEPRECATED shim (2026-09-20, builder cron af3e62239ce2).

This v1 scanner false-positived CLOSED rows as open because it read only
cells[-2]: SUITE-FIX-1 (systems/GLYPH_SELF_HOSTING_ROADMAP.md:359) carries
its closing verdict ("-> done 2026-09-13 22:4x (closing verdict sweep)",
258/0/0, systems/RECEIPT_SUITE_FIX1_CLOSING_VERDICT.md) in the LAST cell,
while cells[-2] still begins with the historical "queued" marker. Every
addendum quoting this path reported a phantom open row (e.g. ADDENDUM 98
needed a manual-tail note to explain it away).

Fixed by delegating to the corrected v3 scanner scan_rows_orch.py
(.builder_queue/, addendum 187: last status occurrence in the ROW wins,
adjacent-cell + mid-cell verdicts handled). Same stdout contract:
matching rows, then "OPEN_COUNT <n>". Extra argv is forwarded, so
`python3 .builder_queue/scan_open_rows_orch.py GPU_CPU_EMULATOR_ROADMAP.md`
scans that roadmap instead of the default.
"""
import os
import runpy
import sys

_here = os.path.dirname(os.path.abspath(__file__))
runpy.run_path(os.path.join(_here, "scan_rows_orch.py"), run_name="__main__")
