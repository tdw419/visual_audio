#!/usr/bin/env python3
"""BK-76 gate — EX-L1..L8 (ruling RULING_BK76_EXEMPTION_POSTURE.md §4).

Option A (No-Vector Refusal) for the :968 SUPER MMIO-window exemption,
locked to the DISPATCH VECTOR WORDS (KFAULT_PC 8193, KSYS_PC 8194,
KTICK_PC 8207) on tile-confined engines (spawn(tile=...) sets
_tile_confinement — the posture of every measured attack shape: tick-20
E1, tick-19 KFAULT chain, tick-21 KSYS chain/persistence).

SCOPE DISCLOSURE (receipt REQUIRED reading): the refuse set is the three
vector words, NOT invariant 1's literal "words 8192+" block. A block-wide
refuse would break lawful post-USER SUPER handler stores that live gates
pin: xv6-nano syscall_dispatch writes ISO_SYS_A0 (word 8205,
test_rv64i_to_glyph_xv6_nano SCENARIO 7/9/10/11), GH-16's tick handler
re-latches MODE_LATCH (word 8192), GO-3 advances ISO_INPUT_CURSOR (word
8237). Ruling invariant 2 itself scopes the hazard to the vectors ("no
lawful reason to mutate KSYS_PC or KFAULT_PC dynamically during guest
dispatch"). Reads stay unmode-gated (BK-48/BK-56 posture).

Legs:
  EX-L1  self-text dispatcher SUPER-window ST to 8194 does NOT land
         (ksys unchanged, faulted=True, reason mmio_exemption_refused,
         running stopped, mode SUPER, NO vector jump taken).
  EX-L2  lawful SUPER no-tile plain-RAM store to 8194 still lands
         (control — the lock is containment-scoped, never legacy).
  EX-L3  USER unpaged out-of-tile rot-guard stays E-K1 (fence live).
  EX-L4  paged walk-refusal rot-guard stays paged_paddr_fence (consult live).
  EX-L5  non-vacuity: neutering the refusal in a TEMP-COPY module lets
         E1 fire and land (real tree md5-pinned before/after).
  EX-L6  KSYS chain (tick-21 K1): guest re-arm of ksys refused -> output
         collapses to [7].
  EX-L7  persistence (tick-21 K2): 75 self-re-arm fires -> 1 fire, clean stop.
  EX-L8  KTICK site measured (ruling §0 requires per-site exercise before
         Option A applies there): tile-confined post-USER store to 8207
         refused, machine stops, and the GH-16 tick arm cannot fire again
         (faulted=True suppresses it — no restart loop).
"""
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))

import numpy as np  # noqa: E402
from tools.glyph_process import GlyphProcessTable  # noqa: E402
from tools.glyph_gpt.baker import bake_image  # noqa: E402

TILE = (256, 19, 1, 2)
WORD_KFAULT = 8193
WORD_KSYS = 8194
WORD_KTICK = 8207
PACKED_HANDLER = (0 << 16) | 3       # pixel (12, 0) = instr 3
PACKED_KTICK = (0 << 16) | 3
SENTINEL = 65537

DISPATCHER_TEXT = (
    ":__entry\n"
    "SYSCALL r10 6\n"      # 0: dispatch to ksys in SUPER
    "LDI r3 99\n"          # 1
    "HALT\n"               # 2
    "LDI r6 %d\n"          # 3: handler start (SUPER) — value
    "LDI r7 %d\n"          # 4: address = vector word
    "ST r7 r6\n"           # 5: THE :968 SUPER-window store
    "LDI r5 52\n"          # 6
    "PRT r5\n"             # 7
    "SYSRET\n"             # 8
)


def _run(text, tile, target_word, host_arm_word=None, host_arm_val=None,
         stamps=None, max_instructions=500, host_arm_fmt=True, arm_val=None):
    """host_arm_fmt=False: `text` carries THREE format slots
    (re-arm value, address, address-again) for K1_CHAIN_TEXT whose unarm
    ST also takes the address; PERSIST_TEXT has only two slots, so pass
    a third-slot-free text via arm_val only for chain shapes."""
    if host_arm_fmt:
        img = bake_image(text % (SENTINEL, target_word), cols_instrs=8,
                         min_rows=64, out_path=None)
    elif text.count("%d") == 2:
        img = bake_image(text % (arm_val, target_word),
                         cols_instrs=8, min_rows=64, out_path=None)
    else:
        img = bake_image(text % (arm_val, target_word, target_word),
                         cols_instrs=8, min_rows=64, out_path=None)
    table = GlyphProcessTable(cols_instrs=8, memory_words=16384)
    if stamps:
        h, w, _ = img.shape
        for word, val in stamps.items():
            idx = word % (h * w)
            img[idx // w, idx % w] = ((val >> 16) & 0xFF, (val >> 8) & 0xFF,
                                      val & 0xFF)
    kw = {} if tile is None else {"tile": tile}
    pid = table.spawn(image=img, max_instructions=max_instructions, **kw)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    if host_arm_word is not None:
        cpu.memory[host_arm_word] = host_arm_val
    table._run_task(pid)
    return {
        "exit": task["exit_status"],
        "faulted": bool(cpu.faulted),
        "reason": (cpu.fault_reason or "")[:80],
        "running": bool(cpu.running),
        "mode": "USER" if cpu.mode == 1 else "SUPER",
        "output": [int(v) for v in cpu.output],
        "word": int(cpu.memory[target_word]),
        "landed": int(cpu.memory[target_word]) == SENTINEL,
    }


PERSIST_TEXT = (
    ":__entry\n"
    "LDI r5 5\n"           # 0
    "SYSCALL r10 6\n"      # 1 -> H (3); SYSRET resumes at 2
    "JMP 1,0\n"            # 2 jump back to instr 1 — persistence vehicle
    "LDI r9 7\n"           # 3  H entry
    "PRT r9\n"             # 4  prints 7 per fire
    "LDI r6 %d\n"          # 5  H packed (self re-arm)
    "LDI r7 %d\n"          # 6  vector word
    "ST r7 r6\n"           # 7  self re-arm (SUPER exemption)
    "SYSRET\n"             # 8
)

K1_CHAIN_TEXT = (
    ":__entry\n"
    "SYSCALL r10 6\n"      # 0  USER: dispatch -> H (instr 3)
    "LDI r3 99\n"          # 1
    "HALT\n"               # 2
    "LDI r9 7\n"           # 3  H entry (SUPER)
    "PRT r9\n"             # 4  prints 7
    "LDI r6 %d\n"          # 5  G2 packed
    "LDI r7 %d\n"          # 6  vector word
    "ST r7 r6\n"           # 7  THE re-arm (SUPER :968 exemption)
    "SYSCALL r10 6\n"      # 8  dispatch #2 -> re-armed ksys
    "PRT r9\n"             # 9
    "LDI r4 41\n"          # 10
    "HALT\n"               # 11
    "LDI r9 7\n"           # 12 G2 entry
    "PRT r9\n"             # 13
    "LDI r9 52\n"          # 14
    "PRT r9\n"             # 15
    "LDI r6 0\n"           # 16
    "LDI r7 %d\n"          # 17 vector word
    "ST r7 r6\n"           # 18 unarm
    "SYSCALL r10 6\n"      # 19 dispatch #3 -> fallback
    "PRT r10\n"            # 20
    "HALT\n"               # 21
)

ARM = "LDI r15 %d\nLDI r14 %d\nST r15 r14\n" % (8211, 1536)
PT_TAG_WORD = 1535
VPN32_PTE_WORD = 1536 + 32
PTE_RAM_PFN32 = 0x7 | (32 << 8)


def test_ex_l1_store_refused():
    r = _run(DISPATCHER_TEXT, TILE, WORD_KSYS, WORD_KSYS, PACKED_HANDLER)
    assert not r["landed"], f"EX-L1: exempt store LANDED (word={r['word']})"
    assert r["word"] == PACKED_HANDLER, r
    assert r["faulted"], "EX-L1: no fault recorded"
    assert "mmio_exemption_refused" in r["reason"], r["reason"]
    assert not r["running"], "EX-L1: machine kept running after refuse"
    assert r["mode"] == "SUPER", r["mode"]
    # no vector jump: the handler never reached PRT (output would carry 52)
    assert 52 not in r["output"], f"EX-L1: vectored/handled anyway {r['output']}"


def test_ex_l2_super_no_tile_lawful():
    r = _run(DISPATCHER_TEXT, None, WORD_KSYS, WORD_KSYS, PACKED_HANDLER)
    assert r["landed"], f"EX-L2: lawful no-tile SUPER store refused: {r}"
    assert r["faulted"] is False and r["exit"] == 0, r


def test_ex_l3_unpaged_rotguard():
    r = _run(":__entry\nLDI r6 %d\nLDI r7 %d\nST r7 r6\nHALT\n",
             TILE, WORD_KSYS, None, None)
    # E-K1 shape: faulted, store refused, FAULT_ADDR = byte address, reaper
    # park (the landed family's pinned evidence shape — item-29 B3).
    assert r["faulted"], r
    assert not r["landed"], r
    assert r["exit"] == 1, r
    assert r["mode"] == "SUPER", r


def test_ex_l4_paged_rotguard():
    r = _run(":__entry\n" + ARM + "LDI r6 %d\nLDI r7 %d\nST r7 r6\nHALT\n",
             TILE, WORD_KSYS, None, None,
             stamps={PT_TAG_WORD: 0x505447, VPN32_PTE_WORD: PTE_RAM_PFN32})
    assert r["faulted"] and "paged_paddr_fence" in r["reason"], r


def test_ex_l5_non_vacuity():
    """Non-vacuity (BK-48/51/64 family shape): the refusal neutered to a
    no-op in a TEMP-COPY module lets E1 fire and land; the REAL tree is
    md5-pinned before/after."""
    import hashlib
    import importlib.util
    real = HERE / "tools" / "glyph_isa_v2.py"
    md5_before = hashlib.md5(real.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "glyph_isa_v2_neutered.py"
        src = real.read_text()
        marker = "def _bk76_exemption_refuse(self, word_addr: int, val: int, x: int, y: int):"
        assert marker in src, "neuter target missing — gate rot"
        neutered = src.replace(marker, marker + "\n        return  # NEUTERED (EX-L5)")
        assert neutered != src
        tmp.write_text(neutered)
        spec = importlib.util.spec_from_file_location("bk76_neutered", tmp)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        # The neutered module's OpcodeMapV2 opens its own wordbase at the
        # REAL path (repo-relative), so run it with the repo as cwd root —
        # pass the REAL wordbase path explicitly.
        cpu = mod.GlyphCPUv2(mod.OpcodeMapV2(
            wordbase_path=HERE / "db" / "wordbase.db"), cols_instrs=8)
        cpu.memory = [0] * 16384
        from tools.glyph_containment import arm_tile
        arm_tile(cpu, TILE)
        cpu.memory[WORD_KSYS] = PACKED_HANDLER
        cpu.running = True
        # bake the E1 program via the REAL baker (same opcode colors —
        # the neuter only touches the refusal body, never the map)
        img = bake_image(DISPATCHER_TEXT % (SENTINEL, WORD_KSYS),
                         cols_instrs=8, min_rows=64, out_path=None)
        import io as _io
        with __import__("contextlib").redirect_stdout(_io.StringIO()):
            n = 0
            while cpu.running and n < 500:
                cpu.step(img)
                n += 1
        landed = cpu.memory[WORD_KSYS] == SENTINEL
        assert landed, f"EX-L5: E1 did not fire under neuter (faulted={cpu.faulted})"
        md5_after = hashlib.md5(real.read_bytes()).hexdigest()
    assert md5_before == md5_after, "real engine mutated by EX-L5"


def test_ex_l6_chain_refused():
    """Tick-21 K1 chain shape: handler re-arms ksys to G2; post-fix the
    re-arm refuses -> second dispatch never happens -> output collapses."""
    g2 = (1 << 16) | 4   # G2 = instr 12 = (row 1, col 4)
    r = _run(K1_CHAIN_TEXT, TILE, WORD_KSYS, WORD_KSYS, PACKED_HANDLER,
             host_arm_fmt=False, arm_val=g2, max_instructions=500)
    assert r["output"] == [7], f"EX-L6: chain not broken: {r['output']}"
    assert r["faulted"] and "mmio_exemption_refused" in r["reason"], r
    assert r["word"] == PACKED_HANDLER, r


def test_ex_l7_persistence_broken():
    """Tick-21 K2 shape: handler self-re-arm + SYSRET loop, main SYSCALL;JMP.
    Post-fix: 1 fire, refusal stops the machine (no restart loop)."""
    r = _run(PERSIST_TEXT, TILE, WORD_KSYS, WORD_KSYS, PACKED_HANDLER,
             host_arm_fmt=False, arm_val=PACKED_HANDLER, max_instructions=600)
    fires = sum(1 for v in r["output"] if v == 7)
    assert fires == 1, f"EX-L7: persistence live ({fires} fires): {r['output']}"
    assert r["faulted"] and not r["running"], r


def test_ex_l8_ktick_site_measured():
    """Ruling §0: the KTICK site is exercised before Option A applies
    there. Dispatch via KSYS (the only re-vector vehicle in this posture);
    the handler's store targets 8207 (KTICK_PC). Post-fix: refused, no
    vector, machine stops — and the faulted latch also suppresses the
    GH-16 tick arm (step() consults `not self.faulted`), so no restart."""
    r = _run(DISPATCHER_TEXT, TILE, WORD_KTICK, WORD_KSYS, PACKED_KTICK)
    assert not r["landed"], f"EX-L8: KTICK store LANDED (word={r['word']})"
    assert r["word"] == 0, r
    assert r["faulted"] and "mmio_exemption_refused" in r["reason"], r["reason"]
    assert not r["running"], "EX-L8: restart loop — machine kept running"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
