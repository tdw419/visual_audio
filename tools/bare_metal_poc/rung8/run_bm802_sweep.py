#!/usr/bin/env python3
"""TASK_BM802: the fault-sensitivity map.

Question the roadmap actually asks: if one byte of the medium decays, does the
machine still boot? Not "does the gate catch it" -- L6 already proved the gate
catches a flipped payload byte. A map that only re-measures the gate is vacuous
(the finding recorded in the ROADMAP's BM802 cell), so every payload sample runs
through bm802_fixture: the loader's EXPECTED_CRC is re-baked to the truth about
the corrupted stream, the gate stays a real check, and what is left standing is
the kernel's own tolerance. That split is what Rung 6 (ECC) needs: how much of
the medium must stay readable for the box to boot, and how much may rot silently.

Three fault axes, one primitive (a single medium byte XOR'd):
  * band    -- a byte of the loader itself (stage1 MBR, stage2 code, the guest's
               CRC32 table, the container's zero padding). Cannot move a CRC
               computed over the payload, so no re-bake is involved.
  * payload -- a byte of the kernel / initrd / filler stream, re-baked.
  * width   -- 3-bit (0xA5) against 1-bit (0x01), so the map does not quietly
               assume multi-bit pit damage.

Plus two honesty legs: gate-ON refusal (the CLEAN loader must refuse a flipped
payload byte, measured from the guest's serial, not asserted on the host) and a
recheck of SENSITIVE samples at 3x the budget, so "dead" is never just "slow".
The boot budget itself is derived from measured control boots, not picked.
And one leg that checks the MAP rather than the medium: `setup-header-census`
boots every byte of the zero-page handshake window that the 4-byte stride
skipped, because a fixed stride over a structured region is an assumption --
see the METHOD CHECK block it adds to the summary.

  usage: python3 run_bm802_sweep.py [--dry] [--resume] [--summary-only]
                                    [--limit=N --recheck=N]  (pre-flight)
  rows:  rung8/bm802_sweep_rows.txt       (one JSON line per boot, append-only)
  map:   rung8/bm802_sensitivity_map.txt  (from --summary, and at the end)
"""
import json
import statistics
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNG9 = HERE.parent / 'rung9'
sys.path.insert(0, str(HERE))
from bm802_boot_class import CEILING, LaneBusy, run_boot      # noqa: E402
from bm802_fixture import COMMITTED, FAULT, RIG, Rig          # noqa: E402

# Output paths live in one dict so a pre-flight run (--limit/--recheck, a few
# boots to prove the plumbing) cannot write partial rows into the real map's
# files -- the resume logic keys off those files.
PATHS = {'rows': HERE / 'bm802_sweep_rows.txt',
         'map': HERE / 'bm802_sensitivity_map.txt'}
SINGLE_BIT = 0x01

# Region ids that exist to check the MAP's own method, not to add coverage. The
# handshake window was sampled at stride 4 and read 10% fatal; whether that is
# the window's shape or the stride's luck is only answerable by walking the
# bytes the stride skipped. Excluded from the size-weighted headline (it
# re-covers 119 bytes already counted) and reported in its own block.
METHOD_REGIONS = {'setup-header-census'}
METHOD_PARENT = {'setup-header-census': 'setup-header'}

# Band boundaries are pinned against the assembled loader by verify_geometry(),
# not assumed: the stage2 image is 16 sectors, its used area ends where the
# CRC32 table ends, and the table is the last 1 KiB of it.
STAGE2_SECTORS, STAGE2_USED, CRC_TABLE_BYTES = 16, 3344, 1024

MEANING = {
    'stage1-mbr': 'BIOS boot sector',
    'stage2-code': 'loader text/data: walk, gate, handoff',
    'stage2-crc-table': "the gate's own lookup table",
    'stage2-pad': 'unused container, never executed',
    'setup-bootsect': 'real-mode code, never executed (handoff enters pmode)',
    'setup-header': 'ZERO-PAGE HANDSHAKE 0x1f1-0x268: HdrS, cmdline ptr, initrd addr+len',
    'setup-header-census': 'METHOD (not coverage): the handshake bytes the stride-4 row skipped',
    'setup-code': 'rest of the setup sector, copied but not run',
    'pm-kernel': 'compressed kernel, decompiles at 0x100000',
    'pm-pad': 'group padding after the kernel',
    'initrd': 'Tiny Core core.gz',
    'initrd-pad': 'group padding after the archive',
    'filler-sink': 'PATTERN groups landing in the 0x34000 sink',
}


def band_regions():
    """(name, lo, hi, stride) in MEDIUM byte coordinates, half-open."""
    s2, band = 512, 512 + STAGE2_SECTORS * 512
    table_lo = s2 + STAGE2_USED - CRC_TABLE_BYTES
    return [('stage1-mbr', 0, s2, 32),
            ('stage2-code', s2, table_lo, 64),
            ('stage2-crc-table', table_lo, s2 + STAGE2_USED, 64),
            ('stage2-pad', s2 + STAGE2_USED, band, 484)]


def payload_regions(r):
    """(name, lo, hi, stride) in PAYLOAD byte coordinates, half-open."""
    gb, ng = r.consts['PX_GROUP_BYTES'], r.n_groups
    setup = r.consts['SUB0_NGROUPS'] * gb
    pm_lo, pm_hi = setup, setup + r.consts['SUB1_NGROUPS'] * gb
    init_lo, init_hi = pm_hi, pm_hi + r.consts['SUB2_NGROUPS'] * gb
    # The first sub-image is NOT one thing. bm903_stage2_px.asm:183 copies
    # payload 0x1f1..0x268 into the zero page and then compares [0x202] against
    # 'HdrS' -- that 119-byte window is Rung 9's handshake (cmdline pointer,
    # initrd address and length, setup_sects), while the surrounding real-mode
    # bootsect code is never executed, because the handoff jumps to the 32-bit
    # entry. Sampling all 16 KiB on one stride measured the wrong thing: an
    # early 0%-fatal reading for `kernel-setup` came from a 512 B stride that
    # stepped almost entirely through dead code, so the window is now its own
    # region at a 4-byte stride.
    ZP_LO, ZP_HI = 0x1f1, 0x268
    # each sub-image is padded up to a whole group, so the tail of both the
    # kernel and the archive is zeros nobody asked for -- and past them sits the
    # PATTERN filler that the loader deliberately dumps into the sink.
    return [('setup-bootsect', 0, ZP_LO, 64),
            ('setup-header', ZP_LO, ZP_HI, 4),
            ('setup-header-census', ZP_LO, ZP_HI, 1),
            ('setup-code', ZP_HI, setup, 512),
            ('pm-kernel', pm_lo, pm_lo + r.pm_len, 196608),
            ('pm-pad', pm_lo + r.pm_len, pm_hi, 2048),
            ('initrd', init_lo, init_lo + r.initrd_len, 393216),
            ('initrd-pad', init_lo + r.initrd_len, init_hi, 2048),
            ('filler-sink', init_hi, ng * gb, 8192)]


def crc_tab():
    out = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (0xEDB88320 ^ (c >> 1)) if c & 1 else (c >> 1)
        out.append(c)
    return out


def verify_geometry(r):
    """Check every number the sampling plan rests on. Returns plane bytes."""
    med = r.control()
    assert med == COMMITTED.read_bytes(), 'control fixture != committed medium'
    plane = (len(med) - r.base * 512) // 4
    assert len(med) == (r.base + 4 * (plane // 512)) * 512, 'medium size drift'
    s2 = med[512:512 + STAGE2_SECTORS * 512]
    assert len(s2) == STAGE2_SECTORS * 512
    assert max(i for i, b in enumerate(s2) if b) == STAGE2_USED - 1, \
        f'stage2 used area is not {STAGE2_USED} B -- band boundaries are stale'
    tab = struct.pack(f'<{CRC_TABLE_BYTES // 4}I', *crc_tab())
    assert s2[STAGE2_USED - CRC_TABLE_BYTES:STAGE2_USED] == tab, \
        'the CRC32 table is not where the boundary says it is'
    assert all(b == 0 for b in s2[STAGE2_USED:]), 'container pad is not zero'
    for _n, lo, hi, _s in band_regions():
        assert 0 <= lo < hi <= len(med)
    for _n, lo, hi, _s in payload_regions(r):
        assert 0 <= lo < hi <= len(r.payload), f'{_n} runs off the payload'
    return plane


def plan(r):
    """Ordered samples: (id, phase, kind, region, offset, fault, rebake)."""
    out = [(f'band-{n}-{i:03d}', 'map', 'band', n, off, FAULT, None)
           for n, lo, hi, st in band_regions()
           for i, off in enumerate(range(lo, hi, st))]
    out += [(f'pay-{n}-{i:03d}', 'map', 'payload', n, off, FAULT, True)
            for n, lo, hi, st in payload_regions(r)
            for i, off in enumerate(range(lo, hi, st))]
    # A method region covers bytes a coarser region already perturbed; booting
    # the same byte twice under two ids would buy nothing and would inflate the
    # boot count. The census keeps only the gap its parent's stride skipped.
    for n, parent in METHOD_PARENT.items():
        have = {s[4] for s in out if s[3] == parent}
        out = [s for s in out if s[3] != n or s[4] not in have]
    # Width legs: the SAME offset, one bit wide instead of three. They must reuse
    # offsets the map already perturbed, or "1 bit vs 3 bits" compares two
    # different places and proves nothing. Middle sample of each region, so the
    # pair does not land on a first-byte edge case.
    seen = {}
    for _sid, _p, kind, region, off, _f, rebake in out:
        if region in ('pm-kernel', 'initrd', 'stage2-code'):
            seen.setdefault(region, []).append((kind, off, rebake))
    out += [(f'width-{reg}', 'width', kind, reg, off, SINGLE_BIT, rebake)
            for reg, lst in sorted(seen.items())
            for (kind, off, rebake) in [lst[len(lst) // 2]]]
    return out


def boot_wait(med, log, budget, tries=900, wait=20.0):
    """run_boot, but patient about the lane: a boot measured beside someone
    else's guest is uninterpretable in both directions (BM903 measured three
    TCG guests pushing an 11 s boot past 240 s), so queue instead of racing.
    `tries` is hours, not minutes, because this sweep is meant to run overnight
    on a box with other lanes alive: a map row is only evidence if it was won
    alone. Aborts rather than writing a half-map it might misread as complete.
    """
    for attempt in range(tries):
        try:
            return run_boot(med, log, budget)
        except LaneBusy as e:
            if attempt % 10 == 0:
                print(f'  lane busy, queuing ({attempt}): {e}', flush=True)
            time.sleep(wait)
    raise SystemExit('lane never cleared; sweep aborted with the map half-'
                     'written, which is worse than not writing it')


SAMPLE_MED = RIG / 'bm903_bm802_sample.raw'
SAMPLE_LOG = RIG / 'bm903_bm802_sample.log'
TRANS = RIG / 'transcripts'          # /tmp, not the repo: ~1 KB a boot, and the
#                                     medium itself is 13.6 MB -- 180 of them
#                                     would eat the 4 GB this box has left.


class Sweep:
    def __init__(self, r):
        self.r = r
        self.out = PATHS['rows'].open('a')
        self.done = {}
        TRANS.mkdir(parents=True, exist_ok=True)

    def boot(self, sid, phase, kind, region, off, fault, rebake, budget):
        """Build this one sample, boot it, return the row UNWRITTEN: the caller
        gets to add the verdict before emit() fixes the line in place, so a row
        on disk is never missing the column the summary reads. The medium path
        is REUSED -- boots here are strictly serial, and 180 x 13.6 MB does not
        fit on this disk."""
        if kind == 'band':
            fx = self.r.build_band(off, SAMPLE_MED, fault=fault)
            payload_off, medium_off = None, off
        else:
            fx = self.r.build(off, SAMPLE_MED, fault=fault, rebake=rebake)
            payload_off, medium_off = off, self.r.medium_byte(off)
        res = boot_wait(SAMPLE_MED, SAMPLE_LOG, budget)
        (TRANS / f'{sid}.txt').write_text(
            f'# {sid} {kind} {region} fault={fault:#04x} rebake={rebake} '
            f'offset={off}\n' + SAMPLE_LOG.read_text('latin-1'))
        return {'id': sid, 'phase': phase, 'kind': kind, 'region': region,
                'payload_off': payload_off, 'medium_off': medium_off,
                'fault': fault, 'rebake': rebake, 'budget': budget,
                'guest_crc': f"{fx['crc']:08X}", **res}

    def emit(self, row):
        self.out.write(json.dumps(row, sort_keys=True) + '\n')
        self.out.flush()
        self.done[row['id']] = row


def load_rows():
    done = {}
    if PATHS['rows'].exists():
        for ln in PATHS['rows'].read_text().splitlines():
            if ln.startswith('{'):
                d = json.loads(ln)
                done[d['id']] = d
    return done


def derive_budget(sw, r, resume):
    """The ceiling is control's own runtime: measure it, then triple it."""
    if resume:
        b = [d['budget'] for d in sw.done.values() if d['phase'] == 'control']
        if b:
            print(f'  resuming with the recorded budget {max(b):.0f}s')
            return max(b)
    trials = []
    for i in range(3):
        res = boot_wait(RIG / 'bm903_bm802_control.raw',
                        RIG / f'bm903_bm802_control{i}.log', 60.0)
        trials.append(res)
        print(f'  control {i}: stage={res["stage"]} t={res["t"]:.1f}s '
              f'flags={",".join(res["flags"])}', flush=True)
        if res['stage'] < CEILING:
            print('CONTROL DID NOT REACH THE CEILING: the rig, the host or the '
                  'lane is unhealthy, so nothing downstream is interpretable. '
                  'Aborting before spending the map budget.')
            raise SystemExit(1)
    med_t = statistics.median(t['t'] for t in trials)
    budget = float(max(25.0, min(60.0, 3 * med_t + 5.0)))
    print(f'  derived boot budget = {budget:.0f}s (3x the control median '
          f'{med_t:.1f}s, ceiling {CEILING})')
    for i, t in enumerate(trials):
        sw.emit({**t, 'id': f'control-{i}', 'phase': 'control',
                 'kind': 'control', 'region': 'control', 'payload_off': None,
                 'medium_off': None, 'fault': 0, 'rebake': None,
                 'budget': budget, 'guest_crc': f'{r.clean_crc:08X}',
                 'verdict': 'CONTROL-OK'})
    return budget


def arg(argv, name, default=None):
    """An --name=N option; both uses here are counts, so ints only."""
    for a in argv:
        if a.startswith(f'--{name}='):
            return int(a.split('=', 1)[1])
    return default


def main(argv):
    resume, dry, summary_only = ('--resume' in argv, '--dry' in argv,
                                 '--summary-only' in argv)
    limit, n_recheck = arg(argv, 'limit'), arg(argv, 'recheck', 8)
    r = Rig()
    r.plane_bytes = verify_geometry(r)
    r.medium_byte = lambda off: (r.base * 512 + (off % 4) * r.plane_bytes
                                 + off // 4)
    samples = plan(r)
    if limit:
        # A pre-flight: a few map legs plus every special leg, into its own
        # files, so the plumbing (build -> boot -> row -> map) is proven before
        # two hours of boots are committed.
        PATHS['rows'] = HERE / 'bm802_preflight_rows.txt'
        PATHS['map'] = HERE / 'bm802_preflight_map.txt'
        samples = [s for s in samples if s[1] == 'width'] + \
                  [s for s in samples if s[1] == 'map'][:limit]
        print(f'*** PREFLIGHT: --limit={limit}, {n_recheck} recheck legs, '
              f'writing {PATHS["rows"].name} (the real map files are untouched)')
    n_map = len(samples)
    n_boots = n_map + 3 + 2 + n_recheck     # map + controls + gate-ON + recheck
    print(f'geometry pinned: medium {len(r.control()):,} B, plane '
          f'{r.plane_bytes:,} B, payload {len(r.payload):,} B')
    for label, regs in (('band', band_regions()), ('payload', payload_regions(r))):
        print(f'  {label}: ' + '  '.join(
            f'{n}={len(range(lo, hi, st))}/{hi - lo:,} B' for n, lo, hi, st in regs))
    print(f'  {n_map} map samples, ~{n_boots} boots total, '
          f'~{n_boots * 31 / 60:.0f} min at a 30 s budget')
    if dry:
        for s in samples[:4] + samples[-4:]:
            print(f'   {s[0]:26} {s[2]:8} {s[5]:#04x} @ {s[4]}')
        print('  ... plan only, no boots run')
        return 0
    if summary_only:
        summarize(load_rows(), r)
        return 0

    if PATHS['rows'].exists() and not resume:
        PATHS['rows'].unlink()
    sw = Sweep(r)
    if resume:
        sw.done = load_rows()
        print(f'  resume: {len(sw.done)} rows already on disk')
    budget = derive_budget(sw, r, resume)

    # -- boot-side non-vacuity: the CLEAN loader against a flipped payload byte
    for i, off in enumerate((16384 + r.pm_len // 2, 4308992 + r.initrd_len // 2)):
        sid = f'gateon-{i}'
        if sid in sw.done:
            continue
        row = sw.boot(sid, 'gate-on', 'payload', 'gate-on-refusal', off, FAULT,
                      False, budget)
        row['verdict'] = ('refused' if row['stage'] <= 1 and
                          'gate-MISMATCH' in row['flags'] else 'NOT-REFUSED')
        sw.emit(row)
        print(f'  gate-ON payload {off}: stage={row["stage"]} '
              f'flags={row["flags"]} -> {row["verdict"]}', flush=True)

    # -- the map
    t0 = time.time()
    for k, (sid, phase, kind, region, off, fault, rebake) in enumerate(samples):
        if sid in sw.done:
            continue
        row = sw.boot(sid, phase, kind, region, off, fault, rebake, budget)
        row['verdict'] = 'INERT' if row['stage'] >= CEILING else (
            'SLOW' if row['stage'] == CEILING - 1 and row['t'] > 0.9 * budget
            else 'SENSITIVE')
        sw.emit(row)
        if k % 10 == 0:
            el = time.time() - t0
            left = (n_map - k - 1) * el / max(1, k + 1)
            print(f'  [{k + 1}/{n_map}] {sid:26} stage={row["stage"]} '
                  f'{row["verdict"]:9} ({el / 60:.1f} min in, '
                  f'~{left / 60:.0f} min left)', flush=True)

    # -- timeout control: does SENSITIVE mean dead, or merely slow?
    sens = [d for d in sw.done.values() if d['phase'] == 'map'
            and d['verdict'] in ('SENSITIVE', 'SLOW')]
    # A method leg exists to be trusted, so EVERY fatal reading inside one gets
    # the 3x recheck; only the coverage regions are rechecked by sample.
    must = [d for d in sens if d['region'] in METHOD_REGIONS]
    ids = {d['id'] for d in must}
    pool = [d for d in sens if d['id'] not in ids]
    step = max(1, len(pool) // max(1, n_recheck))
    for d in must + pool[::step][:n_recheck]:
        sid = d['id'] + '#slow'
        if sid in sw.done:
            continue
        off = d['medium_off'] if d['kind'] == 'band' else d['payload_off']
        row = sw.boot(sid, 'recheck', d['kind'], d['region'], off, d['fault'],
                      d['rebake'], 3 * budget)
        row['verdict'] = 'ALIVE-SLOW' if row['stage'] >= CEILING else 'DEAD'
        sw.emit(row)
        print(f'  recheck {d["id"]:24} at 3x budget: stage={row["stage"]} '
              f'-> {row["verdict"]}', flush=True)
    sw.out.close()
    summarize(load_rows(), r)
    return 0


def summarize(rows, r):
    sizes = {n: hi - lo for n, lo, hi, _ in band_regions()}
    strides = {n: st for n, _lo, _hi, st in
               (*band_regions(), *payload_regions(r))}
    sizes.update({n: hi - lo for n, lo, hi, _ in payload_regions(r)})
    order = list(sizes)
    buckets = {n: [] for n in order}
    special = {}
    for d in rows.values():
        if d['phase'] == 'map' and d['region'] in buckets:
            buckets[d['region']].append(d)
        else:
            special.setdefault(d['phase'], []).append(d)
    ctrls, gateon = special.get('control', []), special.get('gate-on', [])
    recheck, width = special.get('recheck', []), special.get('width', [])

    L = ["BM802 FAULT-SENSITIVITY MAP -- one medium byte XOR'd: how far does the boot get?",
         '',
         "Fixture (rung8/bm802_fixture.py) re-bakes the loader's EXPECTED_CRC to the CRC the",
         'corrupted payload actually computes, so the guest gate stays a REAL check and what',
         'is measured here is kernel tolerance, not gate function (BM903 L6 measured that).',
         "Primitive: one byte XOR 0xA5 (three bits); a one-bit leg is reported separately.",
         'RECOVERED is absent by construction -- nothing on this medium can repair a fault',
         'until Rung 6 is funded and built.']
    if ctrls:
        L += ['', f'Control: {sum(1 for c in ctrls if c["stage"] >= CEILING)}/'
              f'{len(ctrls)} boots reached stage {CEILING} '
              f'(median {statistics.median(c["t"] for c in ctrls):.1f}s); '
              f'fault legs ran on a {ctrls[0]["budget"]:.0f}s budget derived as '
              f'3x that median, so the ceiling is measured, not chosen.']
    L += ['', 'stage  meaning                                verdict',
          f'  {CEILING}    boot scripts finished                      INERT (the fault did not matter)',
          '  4    reached "Loading extensions"               SENSITIVE unless it timed out',
          '  0-3  refused / silent / never reached init      SENSITIVE',
          f'  {CEILING + 1}    + serial prompt                          bonus only (BM903 measured the autologin race)',
          '']
    L.append(f'{"region":16} {"kind":8} {"bytes":>10} {"samp":>5} {"SENS":>5} '
             f'{"INERT":>5} {"fatal%":>7} {"worst":>6}  what it is')
    L.append('-' * 100)
    med_total = len(r.control())
    crit = 0.0
    for n in order:
        d = buckets[n]
        if not d:
            continue
        sens = sum(1 for x in d if x['verdict'] != 'INERT')
        rate = sens / len(d)
        if n not in METHOD_REGIONS:
            crit += rate * sizes[n]
        L.append(f'{n:16} {d[0]["kind"]:8} {sizes[n]:>10,} {len(d):>5} '
                 f'{sens:>5} {len(d) - sens:>5} {rate:>6.0%} '
                 f'{min(x["stage"] for x in d):>6}  {MEANING[n]}')
    L.append('-' * 100)
    L.append(f'Weighted by region size: {crit / 1e6:.2f} MB of the '
             f'{med_total / 1e6:.2f} MB medium ({crit / med_total:.1%}) sits on a '
             f'byte where a single-byte fault stops the boot. That assumes each '
             f'region is uniform between its samples -- the map is a SHAPE, '
             f'not a census: {sum(len(buckets[n]) for n in order)} of '
             f'{med_total:,} medium bytes were perturbed.')
    for n in order:
        d, parent = buckets[n], METHOD_PARENT.get(n)
        if n not in METHOD_REGIONS or not d or not buckets.get(parent):
            continue
        pd = buckets[parent]
        win = {x['payload_off'] for x in d} | {x['payload_off'] for x in pd}
        fatal = sorted(x['payload_off'] for x in d + pd
                       if x['verdict'] != 'INERT')
        est, truth = (sum(1 for x in pd if x['verdict'] != 'INERT') / len(pd),
                      len(fatal) / len(win))
        missed = [o for o in fatal if o not in
                  {x['payload_off'] for x in pd}]
        L += ['', f'METHOD CHECK on {parent} -- reported apart and NOT counted in the',
              f'weighting above, because it re-covers the same {len(win)} bytes.',
              f'Stride {strides[parent]} B sampled {len(pd)} bytes and read {est:.0%} fatal; the',
              f'census booted the other {len(d)}. The whole window is {len(fatal)}/{len(win)}',
              f'= {truth:.0%} fatal, and the stride saw {len(fatal) - len(missed)} of those',
              f'{len(fatal)}: a fixed stride aliases one byte per field, so a field can be',
              'fatal in bytes the stride never touched.']
        if missed:
            L += [f'  The stride MISSED {len(missed)} fatal byte(s): '
                  + ', '.join(hex(o) for o in missed) + '.',
                  '  => A stride can hide fatal bytes, so every fatal% in the table above is a',
                  '     SAMPLE, not a rate -- and for the question Rung 6 asks ("how much of the',
                  '     medium must stay readable?") they are to be read as a FLOOR.']
        else:
            L += ['  The stride MISSED NOTHING: its rate is the window\'s rate.',
                  '  => In the one window where the claim is checkable, coarse strides hid',
                  '     nothing, so the sampled rates stand for the regions they sample.']
    if gateon:
        L += ['', 'Boot-side non-vacuity (committed loader, flipped payload -- the guest '
                  'must refuse):']
        L += [f'  payload {d["payload_off"]:>9} -> stage {d["stage"]}, '
              f'flags={",".join(d["flags"])}, {d.get("verdict", "?")}' for d in gateon]
    if width:
        L += ['', 'Fault width (1 bit, same primitive, at named offsets):']
        for d in width:
            twin = [x for x in rows.values() if x['phase'] == 'map'
                    and x['kind'] == d['kind']
                    and x.get('payload_off') == d.get('payload_off')
                    and x.get('medium_off') == d.get('medium_off')]
            L.append(f'  {d["id"]:18} {d["kind"]:8} stage={d["stage"]} '
                     f'{d.get("verdict", "?"):9} (3-bit at the same offset: '
                     f'{twin[0]["stage"] if twin else "no twin"})')
    if recheck:
        alive = [d for d in recheck if d['verdict'] == 'ALIVE-SLOW']
        L += ['', f'Timeout control: {len(recheck)} SENSITIVE/SLOW legs re-run at 3x the '
              f'budget -> {len(alive)} came alive.']
        L += [f'  {d["id"]:28} stage={d["stage"]} {d["verdict"]}' for d in recheck]
        if not alive:
            L.append('  Every re-run stayed down, so SENSITIVE in this map means a stopped boot,')
            L.append('  not a slow one.')
    L += ['', 'Read this against the Rung 6 case: a large SENSITIVE area is the argument FOR',
          'paying +75% medium capacity for Hamming(7,4), because decay then equals a box that',
          'will not boot; a large INERT area is the argument that some of the medium can be',
          'left unprotected -- and it is also the warning, because an INERT byte is a fault',
          'the CRC gate happily signs off on. Silence is not the same as correctness.']
    text = '\n'.join(L) + '\n'
    PATHS['map'].write_text(text)
    print(text)
    return text


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
