#!/usr/bin/env python3
"""BM653 identity: is the medium that repaired itself AND then executed the
repaired bytes still handing over the SAME machine state as the one that only
repaired itself?

Two halves, both inherited from BM602 -- which inherited them from BM903's L4 --
and both tightened, because option C inserted a program between the gate and the
handoff:

  A. TRANSCRIPTS. rung9's own normalizer (imported by path, so T1-T4 stay
     rung9's rules) reduces each gate log, and then every byte that differs
     from the clean exec boot must sit inside one of SIX named fields, at the
     same offset, in a transcript of the same length, and must equal the value
     bm653_mkimg.py wrote to bm653_fixtures.json before any boot:

        ECC=<8> PAR=<8>   GATE2 CRC=<8> EXP=<8>   GATE2=PASS|FAIL
        BANNER NID=<4>

     The first three are BM602's whitelist plus the verdict word, which BM602
     did not need because it compared media that all booted. The fourth is
     BM653's: the NID is a property of the image, and three of these legs carry
     a different image. `EXEC=` lines are deliberately NOT whitelisted -- the
     green, repaired and scribbler legs all print `EXEC=OK`, and anything else
     on that line is a finding, not a normalization.

     Legs that do not run to the same place are compared UP TO the place they
     do reach: a refusal to the end of its CRC line (the clean boot never
     prints `GATE2=FAIL`, so there is no shared prefix that includes it -- the
     verdict word is then re-asserted as the line that FOLLOWS the cut), the
     halt image to the end of its banner, the scribbler to `HANDOFF BUILT` (it
     is not required to boot Tiny Core -- what its kernel does with a poisoned
     header is a result of this row, not a premise of it). A prefix claim is
     still a claim: the cut text must be equal in length and byte-identical
     outside the fields, and whatever follows the cut must not contain a verdict
     the leg was not supposed to reach.

  B. HANDOFF DUMPS. The executed state at the kernel's first instruction, from
     bm653_capture.py -- rung9's locked gdb session under D4 -- for three media,
     two boots each:

        * leg0 vs leg1 of one medium: the capture is deterministic, strictly;
        * exec_image_repaired vs exec_green: identical. This is the row's
          headline in its strongest form -- a medium with 1,024 of its executable
          bytes wrong, repaired in place, ends with the same handoff as the
          undamaged one, and the image that ran was the same file;
        * exec_green and exec_image_repaired vs pinned references to BM903's
          42-leg PXC1 medium and BM602's image-less PXC2-E medium: identical.
          BM903's dumps live at its rung root and its own gate rewrites them on
          every run, so this row compares against a pinned copy under
          `evidence/refs/` whose sha256 is checked before use -- a landed
          reference is only a reference if it cannot move underneath you.
          Adding an executable region and running it changed nothing the kernel
          can see;
        * exec_scribbler vs those same references: the contract kept (banner,
          echo, mailbox, EXEC=OK) and the zero page differs at EXACTLY the
          offsets bm653_mkimg predicted from the payload and the loader's own
          field writes -- which is what "the exec contract is a liveness
          promise, not a sandbox" means as a measurement.

  usage: python3 bm653_identity.py [--no-capture]
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNG6 = HERE.parent / 'rung6'
RUNG9 = HERE.parent / 'rung9'
LOGS = HERE / 'logs'
CAPS = HERE / 'captures'
REFS_DIR = HERE / 'evidence' / 'refs'
PINS = REFS_DIR / 'refs.json'
NORM = RUNG9 / 'bm903_norm_transcript.py'
FIXJSON = HERE / 'bm653_fixtures.json'

FIELD = re.compile(
    rb'ECC=[0-9A-F]{8} PAR=[0-9A-F]{8}'
    rb'|GATE2 CRC=[0-9A-F]{8} EXP=[0-9A-F]{8}'
    rb'|GATE2=(?:PASS|FAIL)'
    rb'|BANNER NID=[0-9A-F]{4}')
# One pattern, two uses: FIELD.finditer bounds where a difference may live, and
# FIELD.sub(b'<F>') says that nothing else differs. A second, near-identical
# regex would just be a way for the two checks to drift apart.
BASE = 'exec_green'
# A verdict that appears AFTER a leg's cut point would mean the cut was chosen
# to hide it, so every tail is searched for these lines.
ABSENT = (b'BM903-S2 EXEC=', b'BM903-S2 HANDOFF BUILT')
CAPTURE_LEGS = ('exec_green', 'exec_image_repaired', 'exec_scribbler')
# landed references, read-only: (label, directory, filename stem, pinned)
# A pinned reference is a copy this row carries under evidence/refs/ because the
# rung's own file is a working product its gate rewrites; the sha256 in
# refs.json is what makes it a reference rather than a coincidence.
REFS = (('BM903/PXC1', REFS_DIR, 'bm903_px', True),
        ('BM602/PXC2-E', RUNG6 / 'evidence' / 'dumps', 'bm602_px_clean', False))

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


def cut_to(blob: bytes, marker) -> bytes | None:
    """Everything up to and including the first line holding `marker`.

    A None marker means the whole blob: rung9's T4 cut is already the end of the
    normalized text, so a leg that reaches the shell prompt is compared against
    the entire transcript, with no cut chosen here at all.
    """
    if marker is None:
        return blob
    i = blob.find(marker)
    if i < 0:
        return None
    j = blob.find(b'\n', i)
    return blob[:j + 1 if j >= 0 else len(blob)]


# The refusal legs' cut point sits one line BEFORE the verdict word, because the
# clean boot never prints GATE2=FAIL: without a shared line there is no prefix
# claim to make, so the verdict is re-asserted as the line that follows the cut.
CUT_FAIL = b'BM903-S2 GATE2 CRC='
CUT_BANNER = b'IMG2EXEC BANNER NID='
CUT_HANDOFF = b'BM903-S2 HANDOFF BUILT'


def stop_marker(leg):
    """(where the prefix claim ends, what this leg's next line must be).

    A non-None second element is an assertion; None means the tail check below
    carries the claim instead. A None CUT POINT means no cut is claimed: the
    whole normalized transcript is compared, which is what a leg that boots
    Tiny Core to the login race deserves.
    """
    if leg['verdict'] != 'PASS':
        return CUT_FAIL, b'BM903-S2 GATE2=FAIL'
    if leg['exec_expect'] == 'HALT':
        return CUT_BANNER, None
    if leg['anchor_required']:
        return None, None
    return CUT_HANDOFF, None


def cut_label(leg):
    marker, _ = stop_marker(leg)
    return ("rung9's own end-of-transcript cut" if marker is None
            else f"{marker.decode()!r}")


def next_line(blob: bytes, marker: bytes):
    """The line after the cut point, or None if the transcript ended there."""
    cut = cut_to(blob, marker)
    if cut is None:
        return None
    if len(cut) == len(blob):
        return None
    j = blob.find(b'\n', len(cut))
    return blob[len(cut):(j + 1) if j >= 0 else len(blob)]


def fields(blob):
    """The whitelist's contents, keyed by field name, for value comparison."""
    out = {}
    for m in FIELD.finditer(blob):
        t = m.group()
        if t.startswith(b'ECC='):
            out['ECC/PAR'] = t
        elif t.startswith(b'GATE2 CRC'):
            out['CRC/EXP'] = t
        elif t.startswith(b'GATE2='):
            out['verdict'] = t
        else:
            out['NID'] = t
    return out


def predicted(leg):
    """What bm653_mkimg.py wrote to the fixtures file BEFORE any boot, in the
    form FIELD matches: the field bodies, without the line's `BM903-S2 ` stem."""
    return {'ECC/PAR': f'ECC={leg["ecc"]} PAR={leg["par"]}'.encode(),
            'CRC/EXP': f'GATE2 CRC={leg["computed_crc"]} EXP={leg["expected_crc"]}'.encode(),
            'verdict': f'GATE2={leg["verdict"]}'.encode(),
            'NID': f'BANNER NID={leg["exec_nid"]}'.encode()}


def transcripts(fx):
    hr('A. TRANSCRIPTS: every leg against exec_green, rung9 T1-T4 applied')
    by = {f['name']: f for f in fx['fixtures']}
    cpath = LOGS / f'{BASE}.serial'
    if not cpath.exists():
        bad(f'{cpath.name} missing -- run the boot legs first; nothing here '
            'boots anything')
        return
    cbase = norm(cpath)
    if cbase is None:
        return
    ok(f'{BASE}: {len(cpath.read_bytes()):,} B raw -> {len(cbase):,} B compared '
       'after rung9\'s T1-T4')
    blobs = {BASE: cbase}
    for name, leg in sorted(by.items()):
        if name == BASE:
            continue
        p = LOGS / f'{name}.serial'
        if not p.exists():
            bad(f'{name}: no transcript at {p.name}')
            continue
        b = norm(p)
        if b is None:
            continue
        blobs[name] = b
        marker, nxt_want = stop_marker(leg)
        label = cut_label(leg)
        ca, cb = cut_to(cbase, marker), cut_to(b, marker)
        if ca is None or cb is None:
            bad(f'{name}: the clean boot or this one never printed {marker!r}, '
                f'so there is no shared prefix to compare '
                f'(clean={ca is not None}, leg={cb is not None})')
            continue
        if len(ca) != len(cb):
            bad(f'{name}: the two transcripts are not the same length up to '
                f'{label} ({len(ca):,} vs {len(cb):,} B) -- a prefix claim '
                'needs one prefix, not two')
            continue
        spans = diff_spans(ca, cb)
        allowed = [m.span() for m in FIELD.finditer(ca)]
        outside = [(s, e) for s, e in spans
                   if not any(lo <= s and e <= hi for lo, hi in allowed)]
        if outside:
            bad(f'{name}: differs from the clean boot OUTSIDE the whitelisted '
                f'fields, up to {label} -- '
                + ', '.join(f'{s}-{e}' for s, e in outside[:6]))
            continue
        if ca != cb and not spans:
            bad(f'{name}: internal error -- unequal with no differing bytes')
            continue
        if FIELD.sub(b'<F>', ca) != FIELD.sub(b'<F>', cb):
            bad(f'{name}: still differs after the whitelisted fields are '
                'tokenised')
            continue
        cf, lf = fields(ca), fields(cb)
        if set(cf) != set(lf):
            bad(f'{name}: prints a different SET of whitelisted fields than the '
                f'clean boot does up to the same point -- {sorted(lf)} vs '
                f'{sorted(cf)}')
            continue
        want = predicted(leg)
        wrong = {k: (lf[k], want.get(k)) for k in lf if want.get(k) != lf[k]}
        if wrong:
            bad(f'{name}: a whitelisted field is not what the host replay '
                'predicted: '
                + '; '.join(f'{k} wire={v[0]!r} predicted={v[1]!r}'
                            for k, v in sorted(wrong.items())))
            continue
        if nxt_want is not None:
            nl = next_line(b, marker)
            if nl is None or not nl.startswith(nxt_want):
                bad(f'{name}: the cut point sits before the verdict, and what '
                    f'follows it is {nl!r}, not {nxt_want!r}')
                continue
        ok(f'{name}: up to {label} the transcript is the clean boot\'s -- '
           f'{len(ca):,} B compared, equal length, '
           f'{len(spans)} differing span(s) inside {len(allowed)} field(s)'
           + (f', next line {nxt_want.decode()} as predicted' if nxt_want else '')
           + f', and each field equals the prediction ('
           + ', '.join(f'{k}={lf[k].decode()}' for k in sorted(lf)) + ')')
    # A prefix claim has to say what follows the prefix too, or a leg that
    # printed a whole kernel log after the cut point would pass it.
    for name, leg in sorted(by.items()):
        if name == BASE:
            continue
        b = blobs.get(name)
        if b is None:
            continue
        marker, _ = stop_marker(leg)
        after = cut_to(b, marker)
        if after is None:
            continue                       # already RED above
        tail = b[len(after):]
        if marker is None:
            hiding = [w for w in ABSENT if b.count(w) > 1]
            if hiding:
                bad(f'{name}: a verdict line appears twice in the whole '
                    f'transcript ({hiding}) -- a boot that printed EXEC= or '
                    'HANDOFF twice is not the boot being claimed')
                continue
            ok(f'{name}: {len(b):,} B compared with NO cut chosen here, only '
               f'rung9\'s T4, and {ABSENT[0].decode()} / '
               f'{ABSENT[1].decode()} each appear exactly once in it')
            continue
        found = [w for w in ABSENT if w in tail]
        if found:
            bad(f'{name}: {found} appears AFTER {cut_label(leg)} -- the cut '
                'point would be hiding a verdict this leg is not supposed to '
                'reach')
            continue
        ok(f'{name}: {len(tail):,} B of tail after {cut_label(leg)}, and '
           'neither ' + ' nor '.join(repr(w.decode()) for w in ABSENT) +
           ' appears in it'
           + (' -- the transcript stops dead there, which IS this leg\'s claim'
              if tail == b'' else ''))


def capture(name, prefix):
    med = HERE / 'fixtures' / f'{name}.raw'
    r = subprocess.run([sys.executable, str(HERE / 'bm653_capture.py'),
                        str(med), prefix, '60'],
                       capture_output=True, text=True, cwd=str(HERE))
    sys.stdout.write(''.join('        ' + l + '\n'
                             for l in r.stdout.strip().splitlines()))
    if r.returncode:
        bad(f'capture of {name} exited {r.returncode}: {r.stderr.strip()[:200]}')
        return False
    return True


def path(kind, name, leg):
    stem = f'bm653_px_{name}'
    if kind == 'regs':
        return CAPS / f'{stem}_{kind}_leg{leg}.json'
    return CAPS / f'{stem}_{kind}_leg{leg}.bin'


def poison_offsets(fx):
    for f in fx['fixtures']:
        if f['name'] == 'exec_scribbler':
            return {int(p['zp_offset'], 16): (p['clean'], p['scribbled'])
                    for p in f['zp_poison']}
    return {}


def dumps(fx):
    hr('B. HANDOFF DUMPS: executed state at the kernel entry, three media')
    poisons = poison_offsets(fx)
    assert poisons, 'no zp_poison in the fixtures: the scribbler has no prediction'
    CAPS.mkdir(exist_ok=True)
    for name in CAPTURE_LEGS:
        if not capture(name, f'bm653_px_{name}'):
            return
    files = ('zp', 'cmdline', 'regs')
    for name in CAPTURE_LEGS:
        for kind in files:
            a, b = path(kind, name, 0), path(kind, name, 1)
            if not (a.exists() and b.exists()):
                bad(f'{name}: {kind} dump missing ({a.name} / {b.name})')
                continue
            if a.read_bytes() == b.read_bytes():
                ok(f'{name}: {kind} leg0 == leg1, strict, {a.stat().st_size:,} B '
                   '-- deterministic capture')
            else:
                bad(f'{name}: {kind} differs between two boots of the SAME '
                    'medium -- the capture itself is non-deterministic')

    def regs_cmp(a_bytes, b_bytes, label, want_meta):
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

    def bin_cmp(a_bytes, b_bytes, label, expect_diffs):
        """`expect_diffs` maps a zero-page offset to its (clean, dirty) pair, or
        is empty for strict equality. Anything outside it is a RED, and so is
        anything inside it that did NOT move -- the prediction is an equality,
        not a bound."""
        if a_bytes == b_bytes and not expect_diffs:
            ok(f'{label}: {len(a_bytes):,} B BYTE-IDENTICAL, no normalization '
               'applied or needed')
            return
        spans = diff_spans(a_bytes, b_bytes)
        want = {k for k in expect_diffs}
        got = {}
        for s, e in spans:
            for off in range(s, e):
                got[off] = (a_bytes[off], b_bytes[off])
        if set(got) != want:
            bad(f'{label}: differs at {sorted(got)} '
                f'{[(hex(k), f"{v[0]:02X}->{v[1]:02X}") for k, v in sorted(got.items())[:6]]}, '
                f'predicted {sorted(hex(k) for k in want)}')
            return
        wrong = [(hex(k), f'{got[k][0]:02X}->{got[k][1]:02X}',
                  f'{v[0]:02X}->{v[1]:02X}')
                 for k, v in expect_diffs.items() if got[k] != v]
        if wrong:
            bad(f'{label}: the offsets are the predicted ones but the VALUES '
                f'are not: {wrong}')
            return
        ok(f'{label}: differs at exactly {len(want)} byte(s), '
           + ', '.join(f'{hex(k)}: {v[0]:02X}->{v[1]:02X}'
                       for k, v in sorted(expect_diffs.items()))
           + f', and all {len(a_bytes) - len(want):,} other bytes are identical')

    for kind in files:
        for name in CAPTURE_LEGS:
            if name == BASE:
                continue
            a, b = path(kind, BASE, 0), path(kind, name, 0)
            if not (a.exists() and b.exists()):
                bad(f'{kind}: missing dump for {name}')
                continue
            diffs = {} if name != 'exec_scribbler' or kind != 'zp' else poisons
            if kind == 'regs':
                if diffs:
                    bad(f'regs: the scribbler was predicted to leave the '
                        'registers alone')
                    continue
                regs_cmp(a.read_bytes(), b.read_bytes(), f'regs vs {BASE} ({name})',
                         [])
                continue
            bin_cmp(a.read_bytes(), b.read_bytes(), f'{kind} vs {BASE} ({name})',
                    diffs)
    hr('B+. And the same three media against the LANDED references (read-only)')
    pins = json.loads(PINS.read_text())['files'] if PINS.exists() else {}
    for label, reffir, stem, pinned in REFS:
        for kind in ('zp', 'cmdline', 'regs'):
            ext = 'json' if kind == 'regs' else 'bin'
            ref = reffir / f'{stem}_{kind}_leg0.{ext}'
            if not ref.exists():
                bad(f'{ref.name} is not where {label}\'s landed dump should be')
                continue
            if pinned:
                want = pins.get(ref.name)
                if want is None:
                    bad(f'{ref.name} is pinned in code but not in {PINS.name}')
                    continue
                got = hashlib.sha256(ref.read_bytes()).hexdigest()
                if got != want['sha256']:
                    bad(f'{ref.name} sha256 {got[:16]}... != pinned '
                        f'{want["sha256"][:16]}... -- the {label} reference '
                        'moved underneath this row')
                    continue
                ok(f'{label} reference intact: {ref.name} sha256 {got[:16]}...')
            for name in CAPTURE_LEGS:
                mine = path(kind, name, 0)
                if not mine.exists():
                    bad(f'{kind}: no {name} dump to compare against {ref.name}')
                    continue
                diffs = {} if name != 'exec_scribbler' or kind != 'zp' else poisons
                if kind == 'regs':
                    if diffs:
                        bad(f'regs vs {label}: predicted register movement')
                        continue
                    regs_cmp(mine.read_bytes(), ref.read_bytes(),
                             f'{name} regs vs {label}', ['captured_by'])
                    continue
                if diffs:
                    # the landed reference is a CLEAN boot: its zero page holds
                    # the un-poisoned bytes, so the comparison is the same one
                    # as against exec_green.
                    bin_cmp(ref.read_bytes(), mine.read_bytes(),
                            f'{name} {kind} vs {label}', diffs)
                    continue
                if mine.read_bytes() == ref.read_bytes():
                    ok(f'{name} {kind} == {label}: {mine.stat().st_size:,} B, '
                       'the same executed handoff state that medium produced')
                else:
                    spans = diff_spans(mine.read_bytes(), ref.read_bytes())
                    bad(f'{name} {kind} != {label}: {len(spans)} spans, first '
                        f'{["%#x-%#x" % (s, e) for s, e in spans[:6]]}')


def main(argv) -> int:
    fx = json.loads(FIXJSON.read_text())
    transcripts(fx)
    if '--no-capture' in argv:
        hr('B skipped (--no-capture): no gdb boots, transcripts only')
    else:
        dumps(fx)
    hr(f'IDENTITY: GREEN {pass_n}  RED {fail_n}')
    print('BM653_IDENTITY_STATUS=' + ('GREEN' if fail_n == 0 else f'RED ({fail_n})'))
    return 1 if fail_n else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
