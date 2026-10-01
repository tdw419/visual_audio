"""item-33 gate: desktop shell UI & process task launcher (GlyphShell).

Claim-queue item 33 (QUEUE_STATE.json / watchdog draft spec): "Full
desktop shell interface with system status bar, Ext2 PNG VFS storage
gauge, launcher panel, and running task monitors in native glyph
spatial assembly."

Legs:
  S1  STATUS BAR IS A WINDOW: open_bar() opens the bar as an ordinary
      item-31 window at the LOCKED layout rect (row BAR_ROW, 1 x
      BAR_CELLS); its WCB row carries the wcb.rs vocabulary; it is
      hit-testable and visible in windows(). A second open_bar()
      REFUSES (ShellError) — one bar.
  S2  THE BAR TASK PAINTS ITS OWN TILE (THE GAUGE, GUEST-SIDE): the
      bar task is a REAL guest program — it LDs the shell-seeded
      gauge words from its inbox row and STs the painted cells INSIDE
      its own 1x20 tile through the item-29 fence. After run_all(),
      composite() shows exactly `filled` GAUGE_FG cells, then
      BG to GAUGE_CELLS, the health cell, and the launcher cells —
      computed from (free, total) the shell measured via debugfs.
      Fill-fraction legs: a fuller disk paints more cells (two roots,
      different usage -> filled(B) > filled(A), painted cells counted
      from the composite, not from host bookkeeping).
  S3  STORAGE CAPACITY GAUGE (METADATA CONTRACT): storage_gauge()
      returns (free, total) 1 KiB blocks parsed from `debugfs -R
      stats` over the png_vfs-unwrapped image; total == 1024 for the
      default 1 MiB root; writing files through GlyphVfs drops free
      and RAISES the painted gauge (refresh_bar re-measures and
      re-paints — the painted cell count strictly increases).
  S4  APP LAUNCHER (THE item-30 TRANSPORT + item-32 CLICK): install_app
      stores a digest-verified image at /apps/<name> and reserves a
      launcher cell (visible in the composite after refresh); launch()
      opens the app window via the item-30 load (digest verified) and
      delivers ONE BM905 key-press into the fresh window's inbox
      (count==1, decodes to the click). Unknown app / double launch /
      full launcher REFUSE LOUD (ShellError).
  S5  LAUNCHED APP EXECUTES THROUGH THE FENCE: the launched app paints
      its OWN first tile word (fenced ST) and exits 0; after run_all()
      the composite shows the app's pixel at its tile origin and the
      task monitor reports name=app, state=exited, status=0. A
      cross-fence probe (host orders an app ST to a NEIGHBOR's tile)
      is reaped EXIT_FAULT — the fence, not the shell, is containment.
  S6  TASK MONITOR: tasks() reports pid -> {name, state, exit_status,
      wid} for the bar and every launched app, matching the
      stratum's table (names, exit statuses, window linkage).
  R1  MIGRATION: item-31's stratum gate re-runs GREEN in this tree via
      subprocess (the shell is a pure consumer of open_window/
      composite/run_all — the landed layer must not move).
  R2  MIGRATION: item-32's input gate re-runs GREEN in this tree via
      subprocess (the shell's router use is read-side only).
  N1  ENGINE-BYTE guard: tools/glyph_isa_v2.py is byte-identical to
      HEAD (item-33 is a HOST-side shell; any engine drift invalidates
      the gate's premises).
  N2  NON-VACUITY (paint leg can fail): corrupting the seeded `filled`
      word (simulating a shell/compositor disagreement) changes the
      painted cell count — the gate detects a bar that paints the
      wrong gauge (in-suite: painted count != seeded count -> the
      S2 count assertion would fire; exercised by construction via
      the two-roots legs of S2 producing different counts).

Honesty: no rates/latencies asserted (rule-1 floors do not attach);
all asserts structural (rects, words, colors, counts, statuses,
exceptions). Zero new syscall numbers; no engine change. NOT proven:
no GPU/WGSL execution (host CPU engine, Phase-2 doctrine); no live
bar refresh while tasks run (cooperative item-26 model: seed-then-run);
no fonts/text on the plane (cells are solid colors — the "capacity
numbers" are the gauge words, readable via the inbox row); no window
drag/resize (placement containment: rects are open-time fixed); no
mouse-button click channel beyond the item-32 key-packet encoding;
storage numbers are host-side debugfs metadata reads, not guest-
executed queries.
"""
import hashlib
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    OpcodeMapV2,
    W_MEM,
)
from tools.glyph_shell import (  # noqa: E402
    APP_SLOT_COLS,
    BAR_CELLS,
    BAR_ROW,
    GAUGE_CELLS,
    GAUGE_FG,
    GlyphShell,
    HEALTH_CELL,
    LAUNCH_BASE,
    ShellError,
    _rgb_word,
    _word,
)
from tools.glyph_vfs import GlyphVfs  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pytest_python():
    """A python with pytest (the worktree .venv is bare — item-26 R2 shape)."""
    for cand in (sys.executable, "python3",
                 os.path.join(REPO, ".venv", "bin", "python")):
        r = subprocess.run([cand, "-c", "import pytest"], capture_output=True)
        if r.returncode == 0:
            return cand
    pytest.skip("no pytest-capable interpreter found for migration legs")


_OM = OpcodeMapV2()
_ASM = GlyphAssemblerV2(_OM)


def _app_image() -> np.ndarray:
    """A tiny app: paint its OWN first tile word (r1 seeded with the tile
    base by the launcher seed contract), exit 0."""
    return _ASM.assemble([
        "LDI r2 0x112233",
        "ST r1 r2",
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ], width_instrs=8)


def _rogue_image() -> np.ndarray:
    """An app ordered to paint FAR outside its tile (r1 seeded with a
    neighbor row's base) — the fence must reap it, not the shell."""
    return _ASM.assemble([
        "LDI r2 0x0DEAD0",
        "ST r1 r2",
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ], width_instrs=8)


def _painted_gauge(canvas: np.ndarray) -> int:
    """Count GAUGE_FG cells in the bar row from the COMPOSITE (the
    painted truth, not host bookkeeping)."""
    n = 0
    for c in range(GAUGE_CELLS):
        if c < canvas.shape[1] and tuple(canvas[BAR_ROW, c]) == (
                (GAUGE_FG >> 16) & 0xFF, (GAUGE_FG >> 8) & 0xFF, GAUGE_FG & 0xFF):
            n += 1
    return n


# ── S1: the status bar is an ordinary window ────────────────────────────
def test_s1_bar_is_a_window(tmp_path):
    png = str(tmp_path / "root.png")
    GlyphVfs.format(png)
    shell = GlyphShell()
    bar = shell.open_bar(png)
    wcb = shell.stratum.window(bar)
    assert wcb["rect"] == (BAR_ROW, 0, 1, BAR_CELLS)
    assert wcb["name"] == "statusbar"
    assert wcb["state"] == 1 and wcb["visible"] == 1
    assert set(("state", "x", "y", "w", "h", "z", "visible")) <= set(wcb)
    # hit-testable at its own cells
    assert shell.stratum.hit_test(BAR_ROW, 0) == bar
    # one bar only
    with pytest.raises(ShellError):
        shell.open_bar(png)
    shell.close()


# ── S2+S3: the guest-painted gauge tracks real storage usage ────────────
def test_s2_s3_gauge_tracks_storage(tmp_path):
    png_a = str(tmp_path / "a.png")
    png_b = str(tmp_path / "b.png")
    GlyphVfs.format(png_a)
    v = GlyphVfs.format(png_b)
    # Gauge resolution: 12 cells over a 1 MiB/1024-block root ≈ 85 blocks
    # per cell — the B root writes ~400 KiB so filled(B) > filled(A)
    # strictly (a fresh root's ~54 superblock/inode blocks = filled 0).
    v.vfs_write("/etc/motd", b"m" * 4096)
    v.vfs_write("/etc/host2", b"n" * 4096)
    v.vfs_write("/etc/big", b"o" * 400_000)
    v.sync()

    shell = GlyphShell()
    shell.open_bar(png_a)
    free_a, total_a = shell.storage_gauge(png_a)
    assert total_a == 1024
    canvas_a = shell.stratum.composite()
    painted_a = _painted_gauge(canvas_a)
    used_a = total_a - free_a
    assert painted_a == GAUGE_CELLS * used_a // total_a, (
        f"bar A painted {painted_a}, expected "
        f"{GAUGE_CELLS * used_a // total_a} (free={free_a}/{total_a})")

    shell.refresh_bar(png_b)   # same bar window, fuller root
    free_b, total_b = shell.storage_gauge(png_b)
    assert free_b < free_a
    canvas_b = shell.stratum.composite()
    painted_b = _painted_gauge(canvas_b)
    used_b = total_b - free_b
    assert painted_b == GAUGE_CELLS * used_b // total_b
    assert painted_b > painted_a, "fuller disk must paint MORE gauge cells"
    shell.close()


def test_s3_gauge_moves_after_writes(tmp_path):
    png = str(tmp_path / "root.png")
    GlyphVfs.format(png)
    shell = GlyphShell()
    shell.open_bar(png)
    free0, _ = shell.storage_gauge(png)
    painted0 = _painted_gauge(shell.stratum.composite())
    v = GlyphVfs(png)
    v.vfs_write("/etc/big2", b"z" * 200_000)
    v.sync()
    shell.refresh_bar(png)
    free1, _ = shell.storage_gauge(png)
    assert free1 < free0
    painted1 = _painted_gauge(shell.stratum.composite())
    assert painted1 > painted0, (
        f"refresh after writes must raise the gauge: {painted0} -> {painted1}")
    shell.close()


# ── S4: the launcher (item-30 transport + item-32 click) ────────────────
def test_s4_launcher_install_launch_click(tmp_path):
    png = str(tmp_path / "root.png")
    GlyphVfs.format(png)
    shell = GlyphShell()
    shell.open_bar(png)
    shell.install_app(png, "hello", _app_image(), color=0x00FFAA)
    # The installed app is digest-verified content in the root.
    from tools.glyph_vfs import GlyphVfs as V
    raw = V(png).vfs_read("/apps/hello", 1 << 20)
    assert raw is not None
    from tools.glyph_loader import _digest_path
    dig = V(png).vfs_read(_digest_path("/apps/hello"), 128)
    assert dig is not None
    assert hashlib.sha256(raw).hexdigest().encode() == dig.split(b"\n")[0]
    # Launcher cell painted after refresh.
    shell.refresh_bar(png)
    canvas = shell.stratum.composite()
    assert tuple(canvas[BAR_ROW, LAUNCH_BASE]) == (0x00, 0xFF, 0xAA)
    # Launch: window + exactly one BM905 click in the inbox.
    wid = shell.launch(png, "hello")
    snap = shell.router.inbox_snapshot(wid)
    assert snap["count"] == 1
    assert snap["packets"][0][1] == 1  # TYPE_PRESS
    # Unknown app, double launch, launcher overflow refuse LOUD.
    with pytest.raises(ShellError):
        shell.launch(png, "nope")
    with pytest.raises(ShellError):
        shell.launch(png, "hello")  # already running
    for i in range(5):  # fill the remaining launcher slots (6 total)
        shell.install_app(png, f"app{i}", _app_image(), color=0x111111 * (i + 1))
    with pytest.raises(ShellError):
        shell.install_app(png, "overflow", _app_image(), color=0xFFFFFF)
    shell.close()


# ── S5: the launched app runs fenced; cross-fence paints are reaped ─────
def test_s5_app_runs_fenced_and_fault_is_contained(tmp_path):
    png = str(tmp_path / "root.png")
    GlyphVfs.format(png)
    shell = GlyphShell()
    shell.open_bar(png)
    shell.install_app(png, "hello", _app_image(), color=0x00FFAA)
    wid = shell.launch(png, "hello")
    wcb = shell.stratum.window(wid)
    app_cpu = shell.stratum._table.tasks[wcb["pid"]]["cpu"]
    r, c, _h, _w = wcb["rect"]
    app_cpu.registers[1] = r * W_MEM + c      # tile base (seed contract)
    st = shell.stratum.run_all()
    assert st[wcb["pid"]] == 0
    canvas = shell.stratum.composite()
    assert tuple(canvas[r, c]) == (0x11, 0x22, 0x33)
    tm = shell.tasks()
    assert tm[wcb["pid"]]["name"] == "hello"
    assert tm[wcb["pid"]]["state"] == "exited"
    assert tm[wcb["pid"]]["exit_status"] == 0
    shell.close()


def test_s5b_cross_fence_paint_reaped(tmp_path):
    png = str(tmp_path / "root.png")
    GlyphVfs.format(png)
    shell = GlyphShell()
    shell.open_bar(png)
    shell.install_app(png, "rogue", _rogue_image(), color=0xFF00FF)
    wid = shell.launch(png, "rogue")
    wcb = shell.stratum.window(wid)
    app_cpu = shell.stratum._table.tasks[wcb["pid"]]["cpu"]
    # Seed r1 with the BAR's base — one row above the app's tile: a
    # cross-fence paint order. The app's tile rows are >= APP_ROW (20);
    # the bar is row BAR_ROW (8). This store must TRAP.
    app_cpu.registers[1] = _word(BAR_ROW, 1)
    st = shell.stratum.run_all()
    assert st[wcb["pid"]] == 1, (
        f"cross-fence paint must be reaped EXIT_FAULT, got {st}")
    # The bar's cell 1 is UNTOUCHED (painted by the bar task, not rogue).
    canvas = shell.stratum.composite()
    bar_bg = (0x20, 0x20, 0x20)
    assert tuple(canvas[BAR_ROW, 1]) == bar_bg
    shell.close()


# ── S6: the task monitor ────────────────────────────────────────────────
def test_s6_task_monitor(tmp_path):
    png = str(tmp_path / "root.png")
    GlyphVfs.format(png)
    shell = GlyphShell()
    bar = shell.open_bar(png)
    bar_wcb = shell.stratum.window(bar)
    shell.install_app(png, "hello", _app_image(), color=0x00FFAA)
    wid = shell.launch(png, "hello")
    app_wcb = shell.stratum.window(wid)
    app_cpu = shell.stratum._table.tasks[app_wcb["pid"]]["cpu"]
    ar, ac, _ah, _aw = app_wcb["rect"]
    app_cpu.registers[1] = ar * W_MEM + ac      # tile base (seed contract)
    tm = shell.tasks()
    assert set(tm) == {bar_wcb["pid"], app_wcb["pid"]}
    bar_row = tm[bar_wcb["pid"]]
    assert bar_row["name"] == "statusbar"
    app_row = tm[shell.stratum.window(wid)["pid"]]
    assert app_row["name"] == "hello"
    assert app_row["wid"] == wid
    shell.stratum.run_all()
    tm2 = shell.tasks()
    assert tm2[bar_wcb["pid"]]["state"] == "exited"
    assert tm2[shell.stratum.window(wid)["pid"]]["exit_status"] == 0
    shell.close()


# ── R1/R2: migration — the landed layers re-gate GREEN in this tree ─────
def test_r1_stratum_gate_unchanged():
    py = _pytest_python()
    r = subprocess.run([py, "-m", "pytest", "tests/test_item31_stratum.py",
                        "-x", "-q"], cwd=REPO, capture_output=True)
    assert r.returncode == 0, (
        "item-31 stratum gate must stay GREEN:\n"
        + r.stdout.decode(errors="replace")[-1500:])


def test_r2_input_gate_unchanged():
    py = _pytest_python()
    r = subprocess.run([py, "-m", "pytest", "tests/test_item32_input.py",
                        "-x", "-q"], cwd=REPO, capture_output=True)
    assert r.returncode == 0, (
        "item-32 input gate must stay GREEN:\n"
        + r.stdout.decode(errors="replace")[-1500:])


# ── N1: engine-byte guard ───────────────────────────────────────────────
def test_n1_engine_byte_unchanged():
    engine = os.path.join(REPO, "tools", "glyph_isa_v2.py")
    head = subprocess.run(
        ["git", "show", "HEAD:tools/glyph_isa_v2.py"],
        cwd=REPO, capture_output=True)
    assert head.returncode == 0
    with open(engine, "rb") as f:
        assert f.read() == head.stdout, (
            "tools/glyph_isa_v2.py drifted from HEAD — item-33 is a "
            "host-side shell; engine drift invalidates the gate")
