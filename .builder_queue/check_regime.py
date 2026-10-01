"""check_regime.py — R0 check #8: rate-regime validity (REAL, this time).

Jericho's directive 2026-09-21: the 8th linter check must EXIST, not be
claimed. This validates a receipt's timed legs against floors.json
(produced by calibrate_floors.py in a SEPARATE process).

Rule: a timed leg is ADMISSIBLE only if its implied per-round-trip cost
is at or above its code path's measured floor. A leg reporting a
per-call cost BELOW floor is not reporting throughput — it is reporting
a timing artifact, and any ratio built on it is inadmissible.

Usage:
  python3 check_regime.py <receipt.md>            # validate a receipt
  python3 check_regime.py --leg <name> <us> <path> <roundtrips>  # one leg

Receipt convention (what it looks for): lines like
    LEG <name> <rate> steps/s <us_per_rep> us/rep <path> x<n_rt>
e.g.
    LEG B 95299 steps/s 451.2 us/rep step x1
Paths known to floors.json: step, get_state.
"""
import json
import re
import sys
from datetime import datetime, timezone

FLOORS = "/home/jericho/projects/zion/projects/visual_audio/.builder_queue/floors_authoritative.json"
FRESHNESS_H = 12  # 2026-09-21 Jericho: floors are non-stationary on this host
LEG_RE = re.compile(
    r"LEG\s+(\S+)\s+([\d,\.]+)\s+steps/s\s+([\d,\.]+)\s+us/rep\s+"
    r"(\S+)\s+x(\d+)", re.IGNORECASE)


def load_floors() -> dict:
    with open(FLOORS) as f:
        d = json.load(f)
    # freshness: floors older than FRESHNESS_H are stale (host load changes;
    # measured 2.5x drift in 38 min on 2026-09-21 — hence the short window)
    t = datetime.fromisoformat(d["measured_at"])
    age_h = (datetime.now(timezone.utc) - t).total_seconds() / 3600
    if age_h > FRESHNESS_H:
        raise SystemExit(f"FAIL: floors are stale ({age_h:.0f}h old); "
                         "re-run calibrate_floors_authoritative.py")
    return d


def check_leg(name: str, rate: float, us_per_rep: float, path: str,
              n_rt: int, floors: dict) -> tuple[bool, str]:
    fl = floors["floor_us"].get(path)
    if fl is None:
        return False, (f"leg {name}: path '{path}' has no calibrated "
                       f"floor (known: {sorted(floors['floor_us'])})")
    implied_per_rt = us_per_rep / n_rt
    # admissible if implied per-round-trip cost >= 90% of floor
    # (small slack for timer jitter; well below the 9-14x violations
    # the filed 6.15x carried)
    ok = implied_per_rt >= 0.9 * fl
    margin = implied_per_rt / fl
    verdict = "ADMISSIBLE" if ok else "INADMISSIBLE (below floor)"
    return ok, (f"leg {name}: {implied_per_rt:,.1f} us/roundtrip vs "
                f"floor {fl:,.1f} us ({margin:.2f}x) -> {verdict}")


def main() -> None:
    floors = load_floors()
    if sys.argv[1] == "--leg":
        name, rate, us, path, n = (sys.argv[2], float(sys.argv[3]),
                                   float(sys.argv[4]), sys.argv[5],
                                   int(sys.argv[6]))
        ok, msg = check_leg(name, rate, us, path, n, floors)
        print(msg)
        sys.exit(0 if ok else 1)

    receipt = open(sys.argv[1]).read()
    legs = LEG_RE.findall(receipt)
    if not legs:
        raise SystemExit("FAIL: no LEG lines found in receipt — a rate "
                         "receipt without parseable LEG lines is not "
                         "admissible under check #8")
    all_ok = True
    for name, rate, us, path, n in legs:
        ok, msg = check_leg(name, float(rate.replace(",", "")),
                            float(us.replace(",", "")), path, int(n),
                            floors)
        print(msg)
        all_ok = all_ok and ok
    print(f"\nregime check: {'PASS' if all_ok else 'FAIL'} "
          f"({len(legs)} legs, floors from {floors['measured_at']}, "
          f"{floors['adapter_summary']})")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
