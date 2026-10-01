"""BK-27: the shell-native bake cache (tests/test_bk27_shellnative_bake_cache.py).

The cache rides keyed on the FULL bake input vector — (verb, argv, data
len, sha256(data bytes)) — in GlyphL1Shell; a cache hit replays the same
baked image through GlyphRunner instead of re-running gcc+transpile+bake
(~1.6-1.8 s measured, RESEARCH_shellnative_turn_budget.md). The item-20
swap's loud-refusal contract is preserved unchanged.

Scope note (REPAIR_PENDING_BK27_L5_dogfood_budget.md): the backlog row's
original L5 leg ("BK-23 full suite <3500 ms") is UNREACHABLE via the bake
cache — the dogfood suite's two shell-native turns have distinct argv
(pattern rides the C seed block), so 0 cache hits exist inside one suite
run, and a (verb, data)-only key would COLLIDE them (the row's stated key
spec is wrong; the file's own `assert g2 == ""` fires). That rescope is a
skeleton-sign-off change, held out of this gate: THIS gate covers L1-L4/L6
as filed. No claim is made about BK-23's suite budget here.

Legs:
  L1  second identical native turn <= 300 ms (cache hit) — and first
      (fresh bake) turn strictly slower than the second by a margin.
  L2  parity: cache-hit output byte-identical to the fresh-bake output
      AND to a bypass (cache-off) run of the same turn.
  L3  invalidation: changed file bytes -> next turn reflects the new
      bytes (never serves the stale image).
  L4  non-vacuity: with the cache bypassed (_SHELLNATIVE_BAKE_CACHE
      False), L1's timing shape cannot be met (second turn stays in
      fresh-bake territory) — prove the cache is load-bearing.
  L5  family: the item-20 swap gates + L1 personality gates stay green
      (no regression in the refusal contract).
  L6  per-key separation: same data bytes, different argv -> DISTINCT
      cache entries, both served correctly (no collision).
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments.glyph_l1_shell import GlyphL1Shell  # noqa: E402

GCC = "riscv64-unknown-elf-gcc"

pytestmark = pytest.mark.skipif(
    os.system(f"which {GCC} > /dev/null 2>&1") != 0,
    reason="riscv64-unknown-elf-gcc not installed — shell-native swap inactive",
)


def _write(sh: GlyphL1Shell, name: str, content: str) -> None:
    sh.turn(f"echo {content} > {name}")


# ── L1: second identical native turn is a fast cache hit ─────────────────

def test_l1_second_turn_uses_cache():
    sh = GlyphL1Shell()
    _write(sh, "sample.txt", "alpha record1\nbeta record2\ngamma record3\n")

    t0 = time.perf_counter()
    out1 = sh.turn("grep record2 sample.txt")
    t1 = time.perf_counter()
    out2 = sh.turn("grep record2 sample.txt")
    t2 = time.perf_counter()

    fresh_ms = (t1 - t0) * 1000.0
    cached_ms = (t2 - t1) * 1000.0

    assert "record2" in out1, f"fresh turn broken: {out1!r}"
    assert out2 == out1, "cached turn must return identical output"
    assert cached_ms <= 300.0, (
        f"second turn {cached_ms:.1f}ms > 300ms budget — cache not hit")
    # ordering sanity: fresh bake (gcc+bake ~1.6s) must dominate the hit
    assert fresh_ms > cached_ms + 200.0, (
        f"fresh {fresh_ms:.1f}ms vs cached {cached_ms:.1f}ms — "
        "no measurable cache win; cache is not load-bearing here")


# ── L2: parity — cached output == fresh-bake output == bypass output ─────

def test_l2_cached_output_matches_fresh_and_bypass():
    sh_a = GlyphL1Shell()
    _write(sh_a, "data.txt", "one two two three\n")
    fresh = sh_a.turn("grep two data.txt")          # fresh bake
    cached = sh_a.turn("grep two data.txt")         # cache hit
    assert cached == fresh

    sh_b = GlyphL1Shell()                            # new session, cache empty
    sh_b._SHELLNATIVE_BAKE_CACHE = False             # bypass
    _write(sh_b, "data.txt", "one two two three\n")
    bypass = sh_b.turn("grep two data.txt")          # fresh bake, no cache
    assert bypass == fresh, (
        f"bypass {bypass!r} != fresh {fresh!r} — cached image not parity")


# ── L3: invalidation — new file bytes, next turn reflects them ───────────

def test_l3_invalidation_on_new_bytes():
    sh = GlyphL1Shell()
    _write(sh, "live.txt", "v1 marker\n")
    out1 = sh.turn("grep marker live.txt")
    assert "v1" in out1

    _write(sh, "live.txt", "v2 marker\n")            # bytes changed
    out2 = sh.turn("grep marker live.txt")
    assert "v2" in out2, (
        f"stale cache served: {out2!r} — invalidation broken")
    assert "v1" not in out2


# ── L4: non-vacuity — bypass makes L1's shape unmeetable ─────────────────

def test_l4_bypass_makes_l1_shape_unmeetable():
    sh = GlyphL1Shell()
    sh._SHELLNATIVE_BAKE_CACHE = False
    _write(sh, "nv.txt", "k1 k2 k3\n")
    t0 = time.perf_counter()
    sh.turn("grep k2 nv.txt")
    t1 = time.perf_counter()
    sh.turn("grep k2 nv.txt")
    t2 = time.perf_counter()
    a_ms, b_ms = (t1 - t0) * 1000.0, (t2 - t1) * 1000.0
    assert b_ms > 300.0, (
        f"bypassed second turn {b_ms:.1f}ms <= 300ms — the cache would be "
        "vacuous (both turns fast without it)")
    assert abs(a_ms - b_ms) < max(800.0, 0.5 * a_ms), (
        "bypass turns diverge wildly — engine timing unstable, gate unreliable")


# ── L5: family — refusal contract + L1 personality stay green ────────────

def test_l5_family_refusal_and_personality():
    sh = GlyphL1Shell()
    _write(sh, "fam.txt", "x\n")
    # cross-toolchain refusal preserved (fresh shims unchanged, no crash)
    assert sh.turn("grep nomatch fam.txt") == ""     # honest no-hit, no ERR
    out = sh.turn("grep x fam.txt")
    assert "x" in out
    # ERR:SHELLNATIVE refusal arm unchanged: unknown verb is not routed
    assert "ERR:UNKNOWN_CMD" in sh.turn("zig foo.txt")


# ── L6: per-key separation — different argv, same bytes: no collision ────

def test_l6_per_key_separation():
    sh = GlyphL1Shell()
    _write(sh, "words.txt", "apple pie\nbanana split\n")
    a = sh.turn("grep apple words.txt")
    b = sh.turn("grep banana words.txt")             # same file bytes, other argv
    assert "apple" in a and "banana" not in a
    assert "banana" in b and "apple" not in b, (
        f"argv collision — one turn served the other's image: {b!r}")
    a2 = sh.turn("grep apple words.txt")
    b2 = sh.turn("grep banana words.txt")
    assert a2 == a and b2 == b, "re-run after both cached diverged"
    # both turns cached under DISTINCT keys (full-argv keying, not
    # (verb, data) — the row's original one-line key spec would collide)
    assert len(sh._bake_cache) == 2, (
        f"expected 2 distinct cache keys, got {len(sh._bake_cache)}")
    # non-vacuity: force the collision the (verb, data)-only key would
    # create — point banana's key at apple's image — and prove the test
    # discriminates (the served output flips to apple's line).
    k1, k2 = list(sh._bake_cache.keys())
    sh._bake_cache[k2] = sh._bake_cache[k1]
    forced = sh.turn("grep banana words.txt")
    assert forced == a and forced != b, (
        "collision simulation did NOT flip the output — L6 cannot catch "
        "a (verb, data)-key collision; gate is vacuous")
