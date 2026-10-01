#!/usr/bin/env python3
"""
Lockstep divergence harness (chunked) — execute_decoded() vs decode_and_execute()

Two-phase algorithm:
  Phase 1 (coarse): step both cores in large chunks (one GPU dispatch per core
    per chunk), compare architectural state (PC, regs, mode, trap, key CSRs) at
    each chunk boundary. Cheap: ~max_steps/chunk comparisons total.
  Phase 2 (fine): on the first mismatching chunk [S, S+n), reload the checkpoint
    fresh, replay S steps, then single-step with full per-step comparison until
    the exact diverging instruction is found. At most n single steps.

Fast-path activation: SpatialRV64ICore._init_pipeline() does NOT honour any
SHADER_TRANSFORM hook (verified 2026-09-01) — the hook in older harnesses was
silently ignored, so "fast" cores were actually slow-path cores. We patch the
flag the same way _init_pipeline bakes HILBERT_N: by rewriting the shader source
before create_shader_module(). This is done by subclassing and overriding
_init_pipeline to apply FLAG transform to the loaded text.

Deterministic, falsifiable, no LLM in the loop.
"""
import os
import sys
import gc
import tempfile
import numpy as np
from pathlib import Path

TOOLS_DIR = str(Path(__file__).parent.parent.parent / "tools")
sys.path.insert(0, TOOLS_DIR)

from rv64i_checkpoint import load_checkpoint, save_checkpoint

FLAG_OFF = 'let DECODED_FASTPATH_DISABLED: bool = true;'
FLAG_ON = 'let DECODED_FASTPATH_DISABLED: bool = false;'
# Flag default flipped to fast-path-ON 2026-09-02. Both directions are forced
# explicitly via tools/fastpath_core.py CoreSlow/CoreFast — the harness no
# longer depends on which way the shader default points.
from fastpath_core import CoreSlow, load_checkpoint_slow
from spatial_rv64i_cpu import SpatialRV64ICore

CSR_SPOT_CHECKS = [
    ("mstatus", 0x300), ("mepc", 0x341), ("mcause", 0x342), ("mtval", 0x343),
    ("mip", 0x344), ("mie", 0x304), ("mideleg", 0x303),
    ("sstatus", 0x100), ("sepc", 0x141), ("scause", 0x142), ("satp", 0x180),
    ("sip", 0x144), ("sie", 0x104),
]


def _destroy_core(core):
    """Explicitly destroy wgpu buffers to prevent ~340MB/iter host/driver leaks."""
    if core is None:
        return
    for attr_path in [
        ['memory', 'buffer'], ['registers', 'buffer'], ['state_buffer'],
        ['csr_buffer'], ['uart_buffer'], ['tlb_buffer'], ['hilbert_lut_buffer'],
        ['decoded_ops_buffer'],
    ]:
        try:
            target = core
            for a in attr_path:
                target = getattr(target, a, None)
                if target is None:
                    break
            if target is not None and hasattr(target, 'destroy'):
                target.destroy()
        except Exception:
            pass


def _mkpc(st):
    return ((int(st['pc_high']) & 0xffffffff) << 32) | (int(st['pc_low']) & 0xffffffff)


def _snapshot(core):
    st = core.get_state()
    snap = {
        'pc': _mkpc(st),
        'mode': int(st.get('mode', 0)),
        'trap': int(st.get('trap_pending', 0)),
    }
    regs = np.frombuffer(core.queue.read_buffer(core.registers.buffer), dtype=np.uint64)
    snap['regs'] = regs[:32].copy()
    snap['csrs'] = {name: int(core.read_csr(addr)) for name, addr in CSR_SPOT_CHECKS}
    return snap


def _diff_snapshots(a, b):
    diffs = []
    if a['pc'] != b['pc']:
        diffs.append(f"pc: 0x{a['pc']:016x} vs 0x{b['pc']:016x}")
    if a['trap'] != b['trap']:
        diffs.append(f"trap_pending: {a['trap']} vs {b['trap']}")
    if a['mode'] != b['mode']:
        diffs.append(f"mode: {a['mode']} vs {b['mode']}")
    for i in range(32):
        if a['regs'][i] != b['regs'][i]:
            diffs.append(f"x{i}: 0x{int(a['regs'][i]):016x} vs 0x{int(b['regs'][i]):016x}")
    for name in a['csrs']:
        if a['csrs'][name] != b['csrs'][name]:
            diffs.append(f"csr_{name}: 0x{a['csrs'][name]:016x} vs 0x{b['csrs'][name]:016x}")
    return diffs


def load_checkpoint_fast(path):
    """load_checkpoint, but constructing a CoreFast (fast path enabled)."""
    from fastpath_core import load_checkpoint_fast as _lcf
    return _lcf(path)


def _make_cores(checkpoint_path):
    # Both cores warm-load from the SAME original file. Do NOT round-trip
    # through a temp checkpoint: load_checkpoint performs a warm-up step(1),
    # so saving the slow core after load and reloading it would execute the
    # warm-up twice on the fast core, leaving it one instruction ahead —
    # every subsequent comparison would compare different moments in time.
    core_slow = load_checkpoint_slow(checkpoint_path)
    core_fast = load_checkpoint_fast(checkpoint_path)
    d = _diff_snapshots(_snapshot(core_slow), _snapshot(core_fast))
    assert not d, f"cores differ immediately after load: {d[:3]}"
    return core_slow, core_fast


def run_lockstep_chunked(checkpoint_path, max_steps=100_000_000, chunk=100_000,
                         heartbeat_every=10):
    core_slow, core_fast = _make_cores(checkpoint_path)
    steps_done = 0
    chunk_idx = 0
    try:
        while steps_done < max_steps:
            n = min(chunk, max_steps - steps_done)
            core_slow.step(n)
            core_fast.step(n)
            steps_done += n
            chunk_idx += 1

            if chunk_idx % heartbeat_every == 0:
                pc = _mkpc(core_slow.get_state())
                print(f"[heartbeat] steps={steps_done:,} pc=0x{pc:016x}", flush=True)

            diffs = _diff_snapshots(_snapshot(core_slow), _snapshot(core_fast))
            if not diffs and os.environ.get('LOCKSTEP_MEMHASH'):
                # Memory-level compare: catches divergences invisible to the
                # architectural state (e.g. RNG-pool writes of different data).
                import numpy as _np
                ms = _np.frombuffer(core_slow.queue.read_buffer(core_slow.memory.buffer),
                                    dtype=_np.uint32)[core_slow.hilbert_lut_np]
                mf = _np.frombuffer(core_fast.queue.read_buffer(core_fast.memory.buffer),
                                    dtype=_np.uint32)[core_fast.hilbert_lut_np]
                dm = _np.nonzero(ms != mf)[0]
                if len(dm):
                    print(f"\n[phase 1] MEMORY mismatch after chunk ending at step "
                          f"{steps_done:,} — {len(dm)} words differ", flush=True)
                    for d in dm[:12]:
                        print(f"  PA 0x{0x80000000 + int(d)*4:08x}: "
                              f"slow=0x{int(ms[d]):08x} fast=0x{int(mf[d]):08x}")
                    return steps_done - n, n
            if diffs:
                print(f"\n[phase 1] state mismatch after chunk ending at step "
                      f"{steps_done:,} (chunk start {steps_done - n:,})", flush=True)
                for d in diffs[:10]:
                    print(f"  {d}")
                return steps_done - n, n
    finally:
        del core_slow, core_fast
        gc.collect()
    return None, None


def load_checkpoint_nowarm(path, cls):
    """Copy of rv64i_checkpoint.load_checkpoint WITHOUT the warm-up step(1),
    so the harness can single-step from instruction 0 (the warm-up step itself
    is where the fast path first diverges, so it must be observable).

    Skips the warm-up because every step we take afterwards is step(1) — the
    wgpu buffer-mapping hang the warm-up guards against only bites large
    multi-dispatch batches as the first post-write operation.
    """
    import zipfile, json
    with zipfile.ZipFile(path, 'r') as z:
        meta = json.loads(z.read('meta.json'))
        if meta.get('magic') != 'RV64CKPT':
            raise ValueError(f"{path} is not a valid RV64I checkpoint")
        memory_bytes = z.read('memory.bin')
        registers_bytes = z.read('registers.bin')
        csrs_bytes = z.read('csrs.bin')
        state_bytes = z.read('state.bin')
        uart_bytes = z.read('uart.bin')

    core = cls(memory_size_bytes=meta['memory_size_bytes'])

    N = int(np.sqrt(meta['memory_size_bytes'] // 4))
    linear_words = np.frombuffer(memory_bytes, dtype=np.uint32)
    spatial_words = np.zeros_like(linear_words)
    spatial_words[core.hilbert_lut_np] = linear_words
    core.queue.write_buffer(core.memory.buffer, 0, spatial_words.tobytes())

    core.queue.write_buffer(core.registers.buffer, 0, registers_bytes)
    core.queue.write_buffer(core.csr_buffer, 0, csrs_bytes)
    core.queue.write_buffer(core.state_buffer, 0, state_bytes)
    core.queue.write_buffer(core.uart_buffer, 0, uart_bytes)
    core._uart_consumed = meta['uart_consumed']

    core.queue.write_buffer(core.tlb_buffer, 0,
                            np.zeros(core.tlb_entries * 4, dtype=np.uint32).tobytes())
    return core


def run_lockstep_bisect(checkpoint_path, window_start, window_len):
    """Refine a phase-1 flagged window [window_start, window_start+window_len) to
    the exact instruction offset at which fast/slow first diverge — WITHOUT
    single-stepping.

    The threaded fast path only engages inside a multi-instruction dispatch, so
    stepping the window one instruction at a time (run_lockstep_fine) disables
    the very mechanism under test and reports a false "no divergence". This
    instead binary-searches the offset: each probe reloads both cores, replays
    window_start, then executes `mid` instructions as ONE step() call (a single
    dispatch, since mid <= window_len and window_len is a phase-1 chunk, well
    under MAX_STEPS_PER_DISPATCH) and compares architectural state.

    ~log2(window_len) iterations. Invariant: probe==lo has never diverged,
    probe==hi has diverged.
    """
    lo, hi = 0, window_len
    last_diffs = None

    while hi - lo > 1:
        mid = (lo + hi) // 2
        core_slow, core_fast = _make_cores(checkpoint_path)
        try:
            core_slow.step(window_start)
            core_fast.step(window_start)
            pre = _diff_snapshots(_snapshot(core_slow), _snapshot(core_fast))
            if pre:
                return {'diverged': True, 'pre_diverged': True,
                        'step': window_start, 'diffs': pre,
                        'pc': _mkpc(core_slow.get_state()), 'opcode': None}
            core_slow.step(mid)
            core_fast.step(mid)
            diffs = _diff_snapshots(_snapshot(core_slow), _snapshot(core_fast))
        finally:
            _destroy_core(core_slow)
            _destroy_core(core_fast)
            del core_slow, core_fast
            gc.collect()

        print(f"  [bisect] probe={mid:>6} -> {'DIVERGED' if diffs else 'clean'}",
              flush=True)
        if diffs:
            hi = mid
            last_diffs = diffs
        else:
            lo = mid

    if last_diffs is None:
        return {'diverged': False, 'step': window_start + window_len}

    # Re-run the winning probe once more to grab the pre-divergence pc/opcode:
    # replay window_start + (hi-1) clean, read pc, that's the instruction whose
    # execution produces the divergence. Save both cores' full state so the
    # diverging instruction can be inspected live (VA-aware) afterwards.
    core_slow, core_fast = _make_cores(checkpoint_path)
    try:
        core_slow.step(window_start + hi - 1)
        core_fast.step(window_start + hi - 1)
        st = core_slow.get_state()
        pc = _mkpc(st)
        try:
            opcode = core_slow.read_mem_word(pc)
        except Exception:
            opcode = None
        from rv64i_checkpoint import save_checkpoint
        save_checkpoint(core_slow, '/tmp/diverge_slow.rv64ckpt')
        save_checkpoint(core_fast, '/tmp/diverge_fast.rv64ckpt')
        # Dump the fast core's decoded_ops for the block around the diverging pc
        # plus the GPU-side decoded_ops_epoch, to catch stale/corrupt slots.
        try:
            import numpy as _np
            _pc = pc & 0xffffffff   # kernel VA -> PA via the 2MB leaf (PA = VA_low26 | 0x80200000)
            _off = (_pc - 0x80000000) & 0x3fffff | 0x200000
            _slot = _off >> 1
            _ops = _np.frombuffer(core_fast.queue.read_buffer(core_fast.decoded_ops_buffer),
                                  dtype=_np.uint32).reshape(-1, 9)
            _st = core_fast.get_state()
            _epoch = _st.get('decoded_ops_epoch', None)
            print(f"  [dump] decoded_ops_epoch(gpu)={_epoch}")
            for _s in range(_slot - 4, _slot + 5):
                _d = _ops[_s]
                print(f"  [dump] slot {_s}: op={_d[0]} rd={_d[1]} imm=0x{_d[4]:x} raw=0x{_d[6]:08x} len={_d[7]} epoch={_d[8]}")
        except Exception as _e:
            print(f"  [dump] failed: {_e}")
    finally:
        _destroy_core(core_slow)
        _destroy_core(core_fast)
        del core_slow, core_fast
        gc.collect()

    return {'diverged': True, 'step': window_start + hi, 'pc': pc,
            'opcode': opcode, 'diff_type': 'state', 'diffs': last_diffs,
            'diverging_instr_pc': pc}


def run_lockstep_fine(checkpoint_path, clean_steps, max_fine=1_000_000):
    core_slow, core_fast = _make_cores(checkpoint_path)
    core_slow.step(clean_steps)
    core_fast.step(clean_steps)

    diffs = _diff_snapshots(_snapshot(core_slow), _snapshot(core_fast))
    if diffs:
        return {'diverged': True, 'step': clean_steps, 'pre_diverged': True,
                'diffs': diffs, 'pc': _mkpc(core_slow.get_state()), 'opcode': None}

    for step in range(max_fine):
        state_s = core_slow.get_state()
        state_f = core_fast.get_state()
        pc_s, pc_f = _mkpc(state_s), _mkpc(state_f)

        if pc_s != pc_f:
            try:
                opcode = core_slow.read_mem_word(pc_s)
            except Exception:
                opcode = None
            from rv64i_checkpoint import save_checkpoint
            save_checkpoint(core_slow, '/tmp/diverge_slow.rv64ckpt')
            save_checkpoint(core_fast, '/tmp/diverge_fast.rv64ckpt')
            return {'diverged': True, 'step': clean_steps + step, 'pc': pc_s,
                    'pc_fast': pc_f, 'opcode': opcode, 'diff_type': 'pc',
                    'diffs': [f'pc: 0x{pc_s:016x} vs 0x{pc_f:016x}']}

        core_slow.step(1)
        core_fast.step(1)

        diffs = _diff_snapshots(_snapshot(core_slow), _snapshot(core_fast))
        if diffs:
            try:
                opcode = core_slow.read_mem_word(pc_s)
            except Exception:
                opcode = None
            from rv64i_checkpoint import save_checkpoint
            save_checkpoint(core_slow, '/tmp/diverge_slow.rv64ckpt')
            save_checkpoint(core_fast, '/tmp/diverge_fast.rv64ckpt')
            return {'diverged': True, 'step': clean_steps + step, 'pc': pc_s,
                    'opcode': opcode, 'diff_type': 'state', 'diffs': diffs}

    return {'diverged': False, 'step': clean_steps + max_fine}


def probe_one(checkpoint_path, replay, chunk_note=""):
    """Replay `replay` steps on both cores, then execute exactly ONE more
    instruction each and dump pc/x13 before+after — pins which op writes what."""
    core_slow, core_fast = _make_cores(checkpoint_path)
    try:
        def _regs(core):
            import numpy as _np
            return _np.frombuffer(core.queue.read_buffer(core.registers.buffer),
                                  dtype=_np.uint64)[:32].copy()
        core_slow.step(replay)
        core_fast.step(replay)
        s0, f0 = core_slow.get_state(), core_fast.get_state()
        r_s0, r_f0 = _regs(core_slow), _regs(core_fast)
        print(f"[probe] after {replay}: slow pc=0x{_mkpc(s0):016x} x13=0x{int(r_s0[13]):016x}")
        print(f"[probe] after {replay}: fast pc=0x{_mkpc(f0):016x} x13=0x{int(r_f0[13]):016x}")
        core_slow.step(1)
        core_fast.step(1)
        s1, f1 = core_slow.get_state(), core_fast.get_state()
        r_s1, r_f1 = _regs(core_slow), _regs(core_fast)
        print(f"[probe] +1: slow pc=0x{_mkpc(s1):016x} x13=0x{int(r_s1[13]):016x}")
        print(f"[probe] +1: fast pc=0x{_mkpc(f1):016x} x13=0x{int(r_f1[13]):016x}")
        print(f"[probe] full x-reg diff after +1:")
        for _i in range(32):
            if int(r_s1[_i]) != int(r_f1[_i]):
                print(f"    x{_i}: slow=0x{int(r_s1[_i]):016x} fast=0x{int(r_f1[_i]):016x}")
        from rv64i_checkpoint import save_checkpoint
        save_checkpoint(core_slow, '/tmp/probe_slow.rv64ckpt')
        save_checkpoint(core_fast, '/tmp/probe_fast.rv64ckpt')
    finally:
        del core_slow, core_fast
        gc.collect()


def main():
    repo_root = Path(__file__).parent.parent.parent
    checkpoint_path = Path(os.environ.get(
        'LOCKSTEP_FROM', str(repo_root / '.ckpt' / 'v618_preexec.rv64ckpt')))
    if not checkpoint_path.exists():
        print(f"Checkpoint not found: {checkpoint_path}")
        return 1
    if os.environ.get('LOCKSTEP_PROBE_ONE'):
        probe_one(str(checkpoint_path), int(os.environ['LOCKSTEP_PROBE_ONE']))
        return 0
    if os.environ.get('LOCKSTEP_STATEBISECT'):
        replay, window = map(int, os.environ['LOCKSTEP_STATEBISECT'].split(','))
        cs, cf = _make_cores(str(checkpoint_path))
        cs.step(replay)
        cf.step(replay)
        lo, hi = 0, window
        while hi - lo > 1:
            mid = (lo + hi) // 2
            cs2, cf2 = _make_cores(str(checkpoint_path))
            cs2.step(replay + mid)
            cf2.step(replay + mid)
            diffs = _diff_snapshots(_snapshot(cs2), _snapshot(cf2))
            print(f"  [sbisect] probe={replay+mid:>9} -> {'DIVERGED: ' + diffs[0] if diffs else 'clean'}", flush=True)
            if diffs:
                hi = mid
            else:
                lo = mid
            del cs2, cf2
            gc.collect()
        print(f"[sbisect] first state divergence after instruction {replay+hi}")
        return 0
    if os.environ.get('LOCKSTEP_MEMBISECT'):
        import numpy as _np
        from rv64i_checkpoint import save_checkpoint, load_checkpoint
        replay, window = map(int, os.environ['LOCKSTEP_MEMBISECT'].split(','))
        core_slow, core_fast = _make_cores(str(checkpoint_path))
        core_slow.step(replay)
        core_fast.step(replay)
        from rv64i_checkpoint import save_checkpoint
        save_checkpoint(core_slow, '/tmp/membisect_base_slow.rv64ckpt')
        save_checkpoint(core_fast, '/tmp/membisect_base_fast.rv64ckpt')
        del core_slow, core_fast
        gc.collect()
        def _mem(core):
            return _np.frombuffer(core.queue.read_buffer(core.memory.buffer),
                                  dtype=_np.uint32)[core.hilbert_lut_np]
        lo, hi = 0, window
        while hi - lo > 1:
            mid = (lo + hi) // 2
            cs, cf = _make_cores('/tmp/membisect_base_slow.rv64ckpt')
            cs.step(mid)
            cf.step(mid)
            dm = _np.nonzero(_mem(cs) != _mem(cf))[0]
            print(f"  [membisect] probe={mid:>7} -> {'DIVERGED('+str(len(dm))+' words)' if len(dm) else 'clean'}", flush=True)
            if len(dm):
                hi = mid
                last = dm
            else:
                lo = mid
            del cs, cf
            gc.collect()
        cs, cf = _make_cores('/tmp/membisect_base_slow.rv64ckpt')
        cs.step(lo)
        cf.step(lo)
        s_s, s_f = _snapshot(cs), _snapshot(cf)
        print(f"[membisect] first memory divergence after instruction {replay+lo+1} "
              f"(replay {replay} + {lo+1})")
        print(f"[membisect] pre-state regs identical: {not _diff_snapshots(s_s, s_f)}")
        cs.step(1)
        cf.step(1)
        dm = _np.nonzero(_mem(cs) != _mem(cf))[0]
        for d in dm[:16]:
            print(f"  PA 0x{0x80000000 + int(d)*4:08x}: slow=0x{int(_mem(cs)[d]):08x} fast=0x{int(_mem(cf)[d]):08x}")
        pc = _mkpc(cs.get_state())
        print(f"[membisect] post-step pcs: slow=0x{pc:016x} fast=0x{_mkpc(cf.get_state()):016x}")
        return 0

    chunk = int(os.environ.get('LOCKSTEP_CHUNK', '100000'))
    max_steps = int(os.environ.get('LOCKSTEP_MAX_STEPS', '100000000'))
    print(f"Chunked lockstep from {checkpoint_path} "
          f"(chunk={chunk:,}, max_steps={max_steps:,})")
    print("Fast path: ENABLED on 'fast' core via shader-source rewrite "
          "(SHADER_TRANSFORM hook is dead code — do not use)", flush=True)
    print("Loading checkpoints...", flush=True)

    chunk_start, chunk_len = run_lockstep_chunked(
        str(checkpoint_path), max_steps=max_steps, chunk=chunk)

    if chunk_start is None:
        print(f"\nNo divergence within {max_steps:,} steps. Fast path is clean "
              f"on this checkpoint/window.")
        return 0

    # Phase 2: batched binary search over the offset within the flagged window.
    # LOCKSTEP_FINE=single forces the old single-step path (only valid when the
    # divergence is a pure value bug that reproduces without the threaded loop).
    fine_mode = os.environ.get('LOCKSTEP_FINE', 'bisect')
    if fine_mode == 'single':
        print(f"\n[phase 2] refining (single-step): replay {chunk_start:,} clean "
              f"steps, then single-step up to {chunk_len:,}", flush=True)
        result = run_lockstep_fine(str(checkpoint_path), chunk_start,
                                   max_fine=chunk_len + 1)
    else:
        print(f"\n[phase 2] refining (batched bisect): replay {chunk_start:,} "
              f"clean steps, then binary-search the {chunk_len:,}-instr window",
              flush=True)
        result = run_lockstep_bisect(str(checkpoint_path), chunk_start, chunk_len)

    if not result['diverged']:
        print(f"\nRefinement found no divergence in the flagged chunk. If run "
              f"with LOCKSTEP_FINE=single, the divergence needs the threaded "
              f"loop — re-run with the default bisect mode.")
        return 2

    if result.get('pre_diverged'):
        print(f"\nDivergence exists BEFORE the chunk start (replay state already "
              f"differs). Re-run with a smaller chunk. Diffs:")
        for d in result['diffs'][:10]:
            print(f"  {d}")
        return 2

    print(f"\nDIVERGENCE DETECTED at step {result['step']:,}")
    print(f"  PC: 0x{result['pc']:016x}")
    if result.get('pc_fast') is not None:
        print(f"  PC (fast): 0x{result['pc_fast']:016x}")
    if result.get('diverging_instr_pc') is not None:
        print(f"  Diverging instruction pc (slow, offset {result['step'] - chunk_start - 1}"
              f" into window): 0x{result['diverging_instr_pc']:016x}")
    opcode = result.get('opcode')
    print(f"  Opcode: 0x{opcode:08x}" if opcode is not None else "  Opcode: N/A")
    print(f"  Diff type: {result.get('diff_type', 'n/a')}")
    print("  Diffs:")
    for d in result['diffs'][:16]:
        print(f"    {d}")
    if len(result['diffs']) > 16:
        print(f"    ... and {len(result['diffs']) - 16} more")

    return 0


if __name__ == '__main__':
    sys.exit(main())
