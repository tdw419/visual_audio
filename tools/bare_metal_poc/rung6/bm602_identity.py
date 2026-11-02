#!/usr/bin/env python3
"""BM602 identity: does a medium that repaired itself boot BYTE-IDENTICAL to
the clean one -- transcripts AND handoff dumps?

BM601_ECC_SCOPING.md section 5, legs 1 and 2, do not stop at "it booted" and
"the counters say it recovered". The row's letter is "flip N specified corrupted
pixels and still boot byte-identical", and rung9's L4 discipline (RECEIPT_BM903
_E2E.md: transcripts byte-identical after T1-T4, handoff dumps byte-identical
strictly) is inherited unchanged. That is the claim this file checks, in two
halves.

  A. TRANSCRIPTS. The gate already left one serial file per leg in logs/
     (<fixture>.serial, written by qemu alone). They are normalized by rung9's
     OWN normalizer -- imported by path, not copied, so T1-T4 are the same three
     rules and the same cut that made BM903's L4 mean something. Then:
       * the ONLY permitted difference between the clean transcript and a
         repaired one is the ECC=/PAR= counters this rung added, and
       * every differing byte lies inside those two 8-hex fields, which sit at
         the same offset in both transcripts, at the same total transcript
         length; the values themselves are the ones bm602_mkimg.py predicted
         before any boot. (Measured: a repair count of 0xFF4 differs from
         0x00000000 in 3 bytes, not 8 -- the field is 25 B wide and the
         assertion is about CONTAINMENT, not width. Demanding the whole field
         differ was this file's own first bug.)
     Whitelisting that one line is stated here rather than buried in a regex,
     because a normalization that is not counted is how a differing transcript
     gets explained away.

  B. HANDOFF DUMPS. The executed machine state at the kernel's first
     instruction, captured by bm602_capture.py -- which is rung9's locked gdb
     session forked by ten named, round-tripped deltas (bm602_construct.py, D3),
     so "same capture, different medium" is true by construction. Compared:
       * leg0 vs leg1 of the SAME medium -- rung9's determinism half,
       * clean vs each repaired medium -- the identity this row claims,
       * and against BM903's LANDED PXC1 dumps, because the ECC medium carries
         the byte-identical payload and the same loader text, so its handoff
         must be indistinguishable from the medium that already passed 42 legs.
         Those three dumps are rung9's capture OUTPUTS, not its sources, so a
         verbatim copy is landed under this row's evidence/refs/ and each file
         is checked against the sha256 pinned below before a single byte of it
         is trusted as a reference.

  usage: python3 bm602_identity.py [--no-capture]   # A needs only the gate's logs
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNG9 = HERE.parent / 'rung9'
LOGS = HERE / 'logs'
CAPS = HERE / 'captures'
REFS = HERE / 'evidence' / 'refs'
NORM = RUNG9 / 'bm903_norm_transcript.py'
FIXJSON = HERE / 'bm602_fixtures.json'

# The line this rung added, and nothing else, may differ across media.
ECC_LINE = re.compile(rb'ECC=([0-9A-F]{8}) PAR=([0-9A-F]{8})')
CAPTURE_LEGS = ['clean', 'chunk_plane0_stuckff', 'erase_block_128k']

# BM903's leg-0 handoff dumps, pinned by sha256. These are rung9's capture
# OUTPUTS -- run_bm903_e2e.sh writes them at its pixel legs -- so "identical to
# the handoff the 42-leg medium produced" has to name the bytes, not just the
# path. BM653's pristine-checkout run of 2026-09-20 found that class of
# dependency from its side -- in a clean tree these files do not exist at all,
# and in a dirty one a later rung-9 run can rewrite them -- and rung6 reads the
# same three. A verbatim copy is therefore landed at evidence/refs/ (manifest:
# evidence/refs/refs.json) and read from there; re-pin by editing these three
# constants deliberately, never by a gate drifting onto new bytes.
RUNG9_REF_SHA = {
    'bm903_px_zp_leg0.bin':
        'bc2431d7be0ab1d2e74b38834b22aecf58cd15096905a55bdc62109b4c2984b7',
    'bm903_px_cmdline_leg0.bin':
        '30cd829f2a88c80cb80bfef1d056c9d0d85683cc9e58dbd7b9e4c62ce03c43c3',
    'bm903_px_regs_leg0.json':
        '935d5fe1c23f878eee9cc9bfc67f4ae6676243a02a13331603c8125024e64e27',
}

pass_n = fail_n = 0


def ok(msg):
    global pass_n
    print(f'  [PASS] {msg}')
    pass_n += 1


def bad(msg):
    global fail_n
    print(f'  [RED ] {msg}')
    fail_n += 1


def hr(t):
    print('-' * 64)
    print(t)
    print('-' * 64)


def norm(path: Path) -> bytes | None:
    """rung9's normalizer, run as a file so its rules stay rung9's rules."""
    r = subprocess.run([sys.executable, str(NORM), str(path)],
                       capture_output=True, text=True)
    if r.returncode:
        bad(f'normalizer failed on {path.name}: {r.stdout}{r.stderr}')
        return None
    out = path.with_suffix(path.suffix + '.norm')
    return out.read_bytes() if out.exists() else None


def diff_spans(a: bytes, b: bytes):
    """Contiguous (start, end) ranges where a and b disagree, over the shared
    length -- plus whether the lengths themselves matched."""
    n = min(len(a), len(b))
    spans, i = [], 0
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            spans.append((i, j))
            i = j
        else:
            i += 1
    if len(a) != len(b):
        spans.append((n, max(len(a), len(b))))
    return spans


def transcripts(fx):
    hr('A. TRANSCRIPTS: clean boot vs each repaired boot, rung9 T1-T4 applied')
    by = {f['name']: f for f in fx['fixtures']}
    clean = LOGS / 'clean.serial'
    if not clean.exists():
        bad(f'{clean.name} missing -- run the boot legs first; nothing here '
            'boots anything')
        return
    cbase = norm(clean)
    if cbase is None:
        return
    m = ECC_LINE.search(cbase)
    if m is None:
        bad('no ECC=/PAR= line in the normalized clean transcript -- the '
            'gate log is not what this leg thinks it is')
        return
    ok(f'clean transcript: {len(clean.read_bytes()):,} B raw -> {len(cbase):,} B '
       f'compared, ECC line at bytes {m.start()}-{m.end()}')
    for name, leg in by.items():
        if name == 'clean' or not leg['anchor_required'] or leg['verdict'] != 'PASS':
            continue
        p = LOGS / f'{name}.serial'
        if not p.exists():
            bad(f'{name}: no transcript at {p.name}')
            continue
        b = norm(p)
        if b is None:
            continue
        spans = diff_spans(cbase, b)
        raw = ', '.join(f'{s}-{e} ({e - s} B)' for s, e in spans) or 'none'
        nb = sum(e - s for s, e in spans)
        lo, hi = m.span()
        outside = [(s, e) for s, e in spans if s < lo or e > hi]
        if outside:
            bad(f'{name}: transcript differs from the clean boot OUTSIDE the '
                f'counters -- {", ".join(f"{s}-{e}" for s, e in outside)} '
                f'(ECC/PAR fields are {lo}-{hi})')
            continue
        if not spans:
            bad(f'{name}: the counters did not differ at all, yet the fixture '
                f'says ECC={leg["ecc"]} PAR={leg["par"]} -- one of the two is wrong')
            continue
        mb = ECC_LINE.search(b)
        if not mb or mb.span() != (lo, hi) or len(b) != len(cbase):
            bad(f'{name}: the counters sit at a different offset '
                f'({mb.span() if mb else None} vs {(lo, hi)}) or the '
                f'transcripts are different lengths ({len(b)} vs {len(cbase)})')
            continue
        if (mb.group(1), mb.group(2)) != \
           (leg['ecc'].encode(), leg['par'].encode()):
            bad(f'{name}: wire counters {mb.group(1).decode()}/'
                f'{mb.group(2).decode()} are not the predicted '
                f'{leg["ecc"]}/{leg["par"]}')
            continue
        a2 = ECC_LINE.sub(b'ECC=<HEX8> PAR=<HEX8>', cbase)
        b2 = ECC_LINE.sub(b'ECC=<HEX8> PAR=<HEX8>', b)
        if a2 != b2:
            bad(f'{name}: still differs after the one whitelisted line')
            continue
        ok(f'{name}: {len(spans)} differing span(s), {nb} B, all inside the '
           f'{hi - lo} B ECC=/PAR= field at bytes {lo}-{hi} ({raw}), and its '
           f'value is the predicted ECC={leg["ecc"]} PAR={leg["par"]} -- with '
           f'that one line tokenised the transcripts are BYTE-IDENTICAL '
           f'({len(a2):,} B compared, same length both sides)')


def capture(fixtures_dir_name: str, prefix: str) -> bool:
    med = HERE / 'fixtures' / fixtures_dir_name
    r = subprocess.run([sys.executable, str(HERE / 'bm602_capture.py'),
                        str(med), prefix, '60'],
                       capture_output=True, text=True, cwd=str(HERE))
    sys.stdout.write(''.join('        ' + l + '\n'
                             for l in r.stdout.strip().splitlines()))
    if r.returncode:
        bad(f'capture of {fixtures_dir_name} exited {r.returncode}: '
            f'{r.stderr.strip()[:200]}')
        return False
    return True


def dumps(fx):
    hr('B. HANDOFF DUMPS: executed state at the kernel entry, three media')
    by = {f['name']: f for f in fx['fixtures']}
    for name in CAPTURE_LEGS:
        if name not in by:
            bad(f'{name} is not a fixture -- cannot capture it')
            return
    CAPS.mkdir(exist_ok=True)
    for name in CAPTURE_LEGS:
        if not capture(by[name]['medium'], f'bm602_px_{name}'):
            return
    files = ('zp', 'cmdline', 'regs')
    # The landed PXC1 file sizes, asserted before they are used as references:
    # a rung9 evidence file that changed shape would silently void a comparison.
    sizes = {'zp': 4096, 'cmdline': 512, 'regs': 472}

    def path(kind, name, leg):
        return CAPS / f'bm602_px_{name}_{kind}_leg{leg}.json' \
            if kind == 'regs' else CAPS / f'bm602_px_{name}_{kind}_leg{leg}.bin'

    # rung9's L4 half: two boots of one medium must dump identically, strictly.
    for name in CAPTURE_LEGS:
        for kind in files:
            a, b = path(kind, name, 0), path(kind, name, 1)
            if not (a.exists() and b.exists()):
                bad(f'{name}: {kind} dump missing ({a.name} / {b.name})')
                continue
            if a.read_bytes() == b.read_bytes():
                ok(f'{name}: {kind} leg0 == leg1, strict, '
                   f'{a.stat().st_size:,} B -- deterministic capture')
            else:
                bad(f'{name}: {kind} differs between two boots of the SAME '
                    'medium -- the capture itself is non-deterministic')
    # this row's claim: the repaired medium hands off what the clean one does.
    def regs_cmp(a_bytes, b_bytes, label, want_meta):
        """`want_meta` is the set of loader_meta keys that MAY differ: none
        between two dumps made by the same fork, ['captured_by'] against
        rung9's landed file, whose provenance string names the file that ran.
        Getting that set wrong was this file's second bug: it demanded
        'captured_by' inside its own fork, found no meta movement at all, and
        printed it as if the REGISTERS had differed."""
        da, db = json.loads(a_bytes), json.loads(b_bytes)
        ma, mb = da.pop('loader_meta'), db.pop('loader_meta')
        moved = sorted(k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k))
        diff = {k: (da[k], db[k]) for k in da if da[k] != db[k]}
        if diff:
            bad(f'{label}: {len(diff)} register field(s) differ: '
                + ', '.join(f'{k} {v[0]:#x} vs {v[1]:#x}'
                            for k, v in sorted(diff.items())))
        elif moved != want_meta:
            bad(f'{label}: all {len(da)} fields match, but loader_meta moved '
                f'{moved or "nothing"}, expected {want_meta}')
        else:
            ok(f'{label}: all {len(da)} register fields identical '
               f'(rip={da["rip"]:#x} rsi={da["rsi"]:#x} rsp={da["rsp"]:#x} '
               f'cr0={da["cr0"]:#x} eflags={da["eflags"]:#x})'
               + ('' if not moved else
                  ', loader_meta apart from captured_by, which names the file '
                  'that ran'))

    for kind in files:
        for name in CAPTURE_LEGS[1:]:
            a, b = path(kind, 'clean', 0), path(kind, name, 0)
            if not (a.exists() and b.exists()):
                bad(f'{kind}: missing dump for {name}')
                continue
            if kind == 'regs':
                regs_cmp(a.read_bytes(), b.read_bytes(),
                         f'regs vs clean ({name})', [])
                continue
            ra, rb = a.read_bytes(), b.read_bytes()
            if ra == rb:
                ok(f'{kind} vs clean ({name}): {len(ra):,} B BYTE-IDENTICAL, '
                   'no normalization applied or needed')
            else:
                spans = diff_spans(ra, rb)
                bad(f'{kind} vs clean ({name}): {len(spans)} differing spans, '
                    f'first at '
                    f'{", ".join(f"{s:#x}-{e:#x}" for s, e in spans[:6])}')
    # and the strongest form: identical to the LANDED PXC1 medium's handoff.
    hr('B+. The repaired handoff vs BM903\'s landed PXC1 dumps '
       '(pinned copy in evidence/refs)')
    for kind, ref_name, size in (
            ('zp', 'bm903_px_zp_leg0.bin', 4096),
            ('cmdline', 'bm903_px_cmdline_leg0.bin', 512),
            ('regs', 'bm903_px_regs_leg0.json', 472)):
        ref = REFS / ref_name
        if not ref.exists():
            bad(f'{ref_name} is not in {REFS.relative_to(HERE)} -- this row has '
                f'no landed reference to match. It is a verbatim copy of a '
                f'BM903 capture output (rung9/run_bm903_e2e.sh regenerates it '
                f'at its pixel legs); copy it back with the sha in '
                f'RUNG9_REF_SHA, do not overwrite the pin with whatever is there')
            continue
        assert sizes[kind] == size
        got = hashlib.sha256(ref.read_bytes()).hexdigest()
        if got != RUNG9_REF_SHA[ref_name]:
            bad(f'{ref_name} is not the dump this row was designed against: '
                f'sha256 {got[:16]}... != pinned '
                f'{RUNG9_REF_SHA[ref_name][:16]}...')
            continue
        ok(f'{ref_name} intact: sha256 {got[:16]}..., the reference this row '
           'was written against')
        for name in CAPTURE_LEGS:
            p = path(kind, name, 0)
            if not p.exists():
                bad(f'{kind}: no {name} dump to compare against {ref_name}')
                continue
            mine, theirs = p.read_bytes(), ref.read_bytes()
            if kind == 'regs':
                regs_cmp(mine, theirs, f'{name} regs vs {ref_name}',
                         ['captured_by'])
                continue
            if mine == theirs:
                ok(f'{name} {kind} == {ref_name}: {len(mine):,} B, the same '
                   'executed handoff state the 42-leg medium produced')
            else:
                spans = diff_spans(mine, theirs)
                bad(f'{name} {kind} != {ref_name}: {len(spans)} spans, first '
                    f'{["%#x-%#x" % (s, e) for s, e in spans[:6]]}')


def main(argv) -> int:
    fx = json.loads(FIXJSON.read_text())
    transcripts(fx)
    if '--no-capture' in argv:
        hr('B skipped (--no-capture): no boots, transcripts only')
    else:
        dumps(fx)
    hr(f'IDENTITY: GREEN {pass_n}  RED {fail_n}')
    print('BM602_IDENTITY_STATUS=' + ('GREEN' if fail_n == 0 else f'RED ({fail_n})'))
    return 1 if fail_n else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
