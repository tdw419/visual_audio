"""Drop a SE021 re-ruling request into Jericho's mailbox (GH-26 emit path).

The SE021 red leg (37th consecutive red, tests/test_glyph_app_glyph_on_glyph.py:158)
needs a re-ruling of the staged fix options because option (a)'s premise was
measured false (addendum 49) — see .builder_queue/SE021_RED_LEG_RCA_20260916.md.
The orchestrator holds no signing authority over the alternatives, so this
maildrop asks for the ruling; it does NOT land a fix.

Run: /usr/bin/python3 .builder_queue/maildrop_se021_reruling.py
Exits 0 with the committed word + surface on stdout.
"""
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

from tools.geos_emit import GeosEmitter  # noqa: E402

MSG = (
    "SE021 re-ruling requested by builder cron af3e62239ce2 (addendum 57): "
    "RED leg 37 consecutive, RCA .builder_queue/SE021_RED_LEG_RCA_20260916.md. "
    "Option (a) premise FALSE (aliasing structural, not path-length). "
    "Pick (a) variant, (b)+, or (c); or route via GH-25 paging. Holding."
)


def main() -> int:
    # Arg guard (added 2026-09-16, addendum 67): this script's ONLY action is to
    # emit. Any argument (--check, --help, typo) must refuse loudly instead of
    # re-running the emit as a side effect — this bit addenda 65 and 67.
    if len(sys.argv) > 1:
        print(f"refused: unknown argument {sys.argv[1]!r}; "
              "this script takes no arguments and always emits. Not run.",
              file=sys.stderr)
        return 2
    em = GeosEmitter()
    rc = em.emit({
        "kind": "post",
        "box": 0,
        "op": 0x11,
        "payload": 0x2A,
        "note": MSG[:240],
    })
    print("emit rc:", rc)
    committed = rc.get("committed")
    print("committed:", committed)
    return 0 if committed else 1


if __name__ == "__main__":
    sys.exit(main())
