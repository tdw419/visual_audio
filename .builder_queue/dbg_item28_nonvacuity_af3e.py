#!/usr/bin/env python3
"""item-28 gate NON-VACUITY probe (af3e): the gate must be able to FAIL.
R1-style sabotage at the IMPLEMENTATION level, not the input level:

  N1 — guard removed from sync() (the landed body): B4 must FAIL
       (that is the measured RED from probe d32_red_v15 this tick,
       re-checked here by importing the gate's own B4 sequence against
       a broken-copy module).
  N2 — mount() validation removed: R1's corrupt root must NOT be caught
       (proving the check is load-bearing).

Both sabotage checks run against source-rewritten COPIES in a temp dir,
never the tree.
"""
import sys, tempfile, os, shutil, subprocess
from pathlib import Path

WT = "/home/jericho/zion/worktrees/item28-rootinit"
work = tempfile.mkdtemp(prefix="item28_nv_af3e_")

GUARD = '''                    if not self._image_dir_exists(partial):
                        _run(["debugfs", "-w", "-R",
                              f'mkdir "{partial}"', self._disk_path])'''
UNGUARDED = '''                    _run(["debugfs", "-w", "-R",
                          f'mkdir "{partial}"', self._disk_path])'''
MOUNT_CHECK = '''        if vfs.vfs_read(INIT_PATH, 64) is None:
            raise RootInitError(f"root {self.png_path} has no {INIT_PATH}")
'''

results = {}

for name, replacements in (
    ("N1_unguarded_sync", [(GUARD, UNGUARDED)]),
    ("N2_no_mount_check", [(MOUNT_CHECK, "")]),
):
    pkg = os.path.join(work, name, "tools")
    os.makedirs(pkg)
    code = Path(WT, "tools/glyph_vfs.py").read_text()
    root_code = Path(WT, "tools/glyph_root_init.py").read_text()
    for old, new in replacements:
        if old in code:
            code = code.replace(old, new)
        elif old in root_code:
            root_code = root_code.replace(old, new)
        else:
            print(f"{name}: SABOTAGE TARGET NOT FOUND"); sys.exit(1)
    open(os.path.join(pkg, "__init__.py"), "w").close()
    open(os.path.join(pkg, "glyph_vfs.py"), "w").write(code)
    open(os.path.join(pkg, "glyph_root_init.py"), "w").write(root_code)
    shutil.copy(os.path.join(WT, "tools/png_vfs.py"), os.path.join(pkg, "png_vfs.py"))
    shutil.copy(os.path.join(WT, "tools/hilbert_reference_verify.py"),
                os.path.join(pkg, "hilbert_reference_verify.py"))
    # glyph_root_init pulls in the assembler/process modules too.
    shutil.copy(os.path.join(WT, "tools/glyph_isa_v2.py"), os.path.join(pkg, "glyph_isa_v2.py"))
    shutil.copy(os.path.join(WT, "tools/glyph_process.py"), os.path.join(pkg, "glyph_process.py"))
    shutil.copy(os.path.join(WT, "tools/wordbase.py"), os.path.join(pkg, "wordbase.py"))
    probe = os.path.join(work, name, "probe.py")
    open(probe, "w").write(
        "import sys\n"
        f"sys.path.insert(0, {os.path.join(work, name)!r})\n"
        "from tools.glyph_vfs import GlyphVfs\n"
        "from tools.glyph_root_init import GlyphRootFs, RootInitError, Kernel\n"
        "import tempfile, os\n"
    )
    if name == "N1_unguarded_sync":
        open(probe, "a").write(
            "work = tempfile.mkdtemp(prefix='nv1_')\n"
            "png = os.path.join(work, 'root.png')\n"
            "GlyphRootFs.format(png)\n"
            "v1 = GlyphVfs(png)\n"
            "v1.vfs_write('/etc/motd', b'motd-v0')\n"
            "assert v1.sync() == 0\n"
            "v2 = GlyphVfs(png)\n"
            "v2.vfs_write('/etc/motd', b'motd-v1')\n"
            "rc = v2.sync()\n"
            "print('N1 resync rc:', rc, '(gate B4 expects 0 -> sabotage FAILS the gate)' if rc == 0 else '(unguarded body: rc=-1, so B4 WOULD FAIL — sabotage caught)')\n"
            "sys.exit(0 if rc != 0 else 2)\n"
        )
    else:
        open(probe, "a").write(
            "work = tempfile.mkdtemp(prefix='nv2_')\n"
            "sabotaged = os.path.join(work, 'sabotaged.png')\n"
            "# mirror the gate's R1 scenario: hostname present, init absent\n"
            "bad = GlyphVfs.format(sabotaged)\n"
            "bad.vfs_write('/etc/hostname', b'no-init\\n')\n"
            "assert bad.sync() == 0\n"
            "try:\n"
            "    GlyphRootFs(sabotaged).mount()\n"
            "    print('N2: init-less root MOUNTED (check removed — R1 would fail)')\n"
            "    sys.exit(0)\n"
            "except RootInitError:\n"
            "    print('N2: still refused — sabotage did not remove the check')\n"
            "    sys.exit(2)\n"
        )
    r = subprocess.run([sys.executable, probe], capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print("  stderr:", (r.stderr or "")[-300:])
    results[name] = (r.returncode == 0)

print()
print("N1 unguarded-sync makes B4 fail:", results["N1_unguarded_sync"])
print("N2 check-removal makes R1 fail:", results["N2_no_mount_check"])
ok = results["N1_unguarded_sync"] and results["N2_no_mount_check"]
print("NON-VACUITY:", "GATE IS DISCRIMINATING" if ok else "NOT PROVEN")
shutil.rmtree(work)
sys.exit(0 if ok else 1)
