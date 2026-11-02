#!/usr/bin/env python3
"""BM653's pinned references: land BM903's executed-handoff dumps as bytes this
row owns, instead of reading them out of rung9's working directory.

Why a pin and not the original (the defect this fixes, found by running the row
from `git archive HEAD` on 2026-09-20): `rung9/bm903_px_{zp,cmdline}_leg0.bin`
are the dumps `rung9/run_bm903_e2e.sh` WRITES at its capture legs. They are not
in git, so a clean checkout has none -- and where the lane does have them, a
later rung-9 run can rewrite them. Either way "identical to the handoff BM903
gated" would be comparing against a file that can move or vanish. So the copy
this row checks against lives in `evidence/refs/`, is committed, and its sha256
is re-checked by `bm653_identity.py` before a single byte of it is trusted.

  usage: python3 bm653_refs.py [--from <dir>]   # default: ../rung9
         python3 bm653_refs.py --check         # verify evidence/refs/ only

Idempotent: re-running over a correct set of refs is a no-op that prints the
table. If a pinned file already on disk differs from rung9's, or from refs.json,
this REFUSES and exits 1 -- re-pinning is a deliberate edit to refs.json, not a
side effect of a build.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'evidence' / 'refs'
META = OUT / 'refs.json'
# (filename, what it is) -- leg0 only: the reference is one clean boot.
WANT = (
    ('bm903_px_zp_leg0.bin',
     'zero page (4,096 B) at the kernel entry, PXC1 medium, BM903 leg 0'),
    ('bm903_px_cmdline_leg0.bin',
     'command line (512 B) at the kernel entry, PXC1 medium, BM903 leg 0'),
    ('bm903_px_regs_leg0.json',
     '25 register fields at the kernel entry, PXC1 medium, BM903 leg 0'),
)
# Fixed, not time.localtime(): re-pinning the same bytes must not churn refs.json.
PINNED = '2026-09-20'
SOURCE = 'rung9/bm903_px_*_leg0.{bin,json}, the dumps rung9/run_bm903_e2e.sh ' \
         'captures at its pixel-medium legs (RECEIPT_BM903_E2E.md)'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check() -> int:
    """Verify evidence/refs/ against its own manifest. Needs no source dir, so a
    clean checkout can ask the same question the lane can."""
    if not META.exists():
        print(f'  [RED ] {META.relative_to(HERE.parent.parent)} missing: run '
              '`python3 bm653_refs.py` where rung9\'s dumps exist')
        return 1
    m = json.loads(META.read_text())
    files, bad = m['files'], 0
    for name, ent in files.items():
        p = OUT / name
        if not p.exists():
            print(f'  [RED ] {name}: listed in refs.json, not on disk')
            bad += 1
            continue
        got = sha256(p)
        if got != ent['sha256']:
            print(f'  [RED ] {name}: sha256 {got[:16]}... != pinned '
                  f'{ent["sha256"][:16]}...')
            bad += 1
        elif p.stat().st_size != ent['bytes']:
            print(f'  [RED ] {name}: {p.stat().st_size:,} B on disk, '
                  f'{ent["bytes"]:,} B pinned')
            bad += 1
        else:
            print(f'  [PASS] {name:32s} {ent["bytes"]:>6,} B  sha256 {got[:16]}...')
    for name in sorted({p.name for p in OUT.iterdir() if p.is_file()}
                       - set(files) - {META.name}):
        print(f'  [RED ] {name}: on disk but not in refs.json')
        bad += 1
    print(f'\nrefs: {len(files)} pinned, {bad} problem(s)')
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if '--check' in argv:
        return check()
    src = Path(argv[argv.index('--from') + 1]).resolve() if '--from' in argv \
        else HERE.parent / 'rung9'
    assert src.is_dir(), f'{src} is not a directory'
    OUT.mkdir(parents=True, exist_ok=True)

    rows, skipped, problems = {}, set(), []
    for name, what in WANT:
        s = src / name
        if not s.exists():
            problems.append(f'{name}: source {s} missing -- nothing to pin')
            skipped.add(name)
            continue
        d = OUT / name
        got = sha256(s)
        if d.exists():
            if sha256(d) != got:
                problems.append(f'{name}: the pinned copy and {src.name}\'s '
                                f'current copy disagree ({sha256(d)[:16]}... vs '
                                f'{got[:16]}...) -- resolve by hand, do not re-pin')
                skipped.add(name)
                continue
        else:
            shutil.copyfile(s, d)
        rows[name] = {'sha256': got, 'bytes': d.stat().st_size, 'what': what}

    prior = json.loads(META.read_text())['files'] if META.exists() else {}
    for name, ent in prior.items():
        if name in skipped:
            pass                       # already reported above
        elif name not in rows:
            problems.append(f'{name}: in refs.json but not in WANT -- the pin '
                            'table changed shape')
        elif ent['sha256'] != rows[name]['sha256']:
            problems.append(f'{name}: newly pinned bytes differ from the '
                            f'recorded sha256 ({ent["sha256"][:16]}... -> '
                            f'{rows[name]["sha256"][:16]}...)')

    if problems:
        for p in problems:
            print(f'  [RED ] {p}')
        print(f'\n{len(problems)} problem(s); refs.json unchanged.')
        return 1

    META.write_text(json.dumps({
        'convention': 'pinned read-only references BM653 compares its executed '
                      'handoff against; sha256 re-checked by bm653_identity.py '
                      'before use',
        'pinned': PINNED,
        'source': SOURCE,
        'files': rows,
    }, indent=2) + '\n')

    for name, ent in rows.items():
        print(f'  [PASS] {name:32s} {ent["bytes"]:>6,} B  sha256 '
              f'{ent["sha256"][:16]}...  {ent["what"]}')
    print(f'\nwrote {META.relative_to(HERE.parent.parent)} '
          f'({len(rows)} files pinned from {src.name})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
