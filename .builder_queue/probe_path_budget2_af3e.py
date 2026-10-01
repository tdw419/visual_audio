# probe_path_budget2_af3e.py — empirical maxima for the FS-window path budget
import sys

sys.path.insert(0, "experiments")
sys.path.insert(0, "tools")
from glyph_interactive_shell import build_dispatch_shell  # noqa: E402

try:
    from glyph_l1_shell import PATH_CAP, DISPATCH_BUF_CAP  # type: ignore
    print(f"l1_shell PATH_CAP={PATH_CAP} DISPATCH_BUF_CAP={DISPATCH_BUF_CAP}")
except Exception as e:  # noqa: BLE001
    print("l1_shell import:", e)

import glyph_interactive_shell as gis  # noqa: E402
print("interactive_shell DISPATCH_BUF_CAP =", getattr(gis, "DISPATCH_BUF_CAP", "?"))


def builds(n_w: int, n_a: int) -> bool:
    w = "/tmp/x/" + "d" * max(1, n_w - 7)
    a = "/tmp/x/" + "o" * max(1, n_a - 7)
    w = w[:n_w]
    a = a[:n_a]
    try:
        build_dispatch_shell(write_path=w, audio_path=a)
        return True
    except AssertionError:
        return False


# binary search the max write-path length with audio path short (14)
lo, hi = 1, 4096
while lo < hi:
    mid = (lo + hi + 1) // 2
    if builds(mid, 14):
        lo = mid
    else:
        hi = mid - 1
print(f"max write_path length (audio=14): {lo}")

# and the max audio path with write short (13)
lo2, hi2 = 1, 4096
while lo2 < hi2:
    mid = (lo2 + hi2 + 1) // 2
    if builds(13, mid):
        lo2 = mid
    else:
        hi2 = mid - 1
print(f"max audio_path length (write=13): {lo2}")

# combined budget: both equal length
lo3, hi3 = 1, 4096
while lo3 < hi3:
    mid = (lo3 + hi3 + 1) // 2
    if builds(mid, mid):
        lo3 = mid
    else:
        hi3 = mid - 1
print(f"max EQUAL path length (write==audio): {lo3}")
