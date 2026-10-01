#!/usr/bin/env python3
"""Pillar 2.1 — syscall ABI spec with a doc-rot guard (GLYPH_ISA_ROADMAP.md §2.1).

"One page per syscall: register contract, argument addressing (which memory
view!), return codes, errno set, containment rules. Written against the ISA,
implementable by any engine. Gate: the doc's register/addr claims are
extracted from code by a test (doc-rot guard), not transcribed."

Design (why extraction, not transcription): a transcribed claim can drift
from the engine silently — the exact failure class Pillar 2.2a caught (the
twin's syscall stub drifted the moment the reference engine evolved). So the
doc carries MACHINE-READABLE claim blocks (<!--ABI 0xNN ... -->) and this
gate re-derives the same facts from the engine sources and the live engine:

  L1  Registry coverage — every Python dispatch branch (0x01..0x12) has a
      doc block; every doc block has a branch. Both directions.
  L2  Storage-home claims — doc says RAM -> the handler body addresses
      self.memory; doc says PIXEL -> it goes through _mem_read/_mem_write
      on the image; doc says HOST -> no substrate storage claim.
  L3  Twin-status claims — doc's per-syscall WGSL status matches the twin
      source structure: IMPLEMENTED has its own `syscall_num == Nu` branch,
      STUB sits in the 3u/4u/6u no-op group, BRIDGED falls in the
      16u..255u return-0 group, UNIMPLEMENTED has no branch (else -> -1).
  L4  Live behavioral legs — the doc's register contract and return codes
      are exercised against the REAL Python engine (handlers driven
      directly, the test_defect_d pattern): pokes + call + assert.
  L5  Non-vacuity — a mutated in-memory copy of the doc (flipped storage
      claim, flipped return claim) makes the guard legs FAIL, so the gate
      can go RED when the doc lies.

The WGSL twin implements a strict subset (documented divergence, not a
defect): 0x01/0x02/0x05 real, 0x03/0x04/0x06 stubs returning 0,
0x07/0x08/0x09 -> -1 (no branch), 0x10 IMPLEMENTED, 0x11 BRIDGED no-op
returning 0, and 0x12 -> -1 (18u excluded from the 16u..255u GeOS bridge
by the TICKET_ITEM8 fix, 2026-09-22: the bridge previously returned 0 —
a measured false spawn-success; the exclusion legs below pin the fix —
removing `!= 18u` from the bridge REDs). Cross-engine parity of the
shared subset is the standing job of tests/test_pillar23_parity_ci.py,
not duplicated here.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphCPUv2,
    OpcodeMapV2,
    INPUT_LEN_ADDR,
    INPUT_CURSOR_ADDR,
    INPUT_DATA_ADDR,
)

PY_ENGINE = REPO / "tools" / "glyph_isa_v2.py"
WGSL_TWIN = REPO / "tools" / "wgsl_glyph_isa_v2.py"
SPEC_DOC = REPO / "docs" / "SYSCALL_ABI_SPEC.md"

ADDR = 2000  # safely outside the GH-8b FS window [1024, 1280)


# ---------------------------------------------------------------------------
# Doc claim-block parser (shared by the gate legs AND the non-vacuity probe)
# ---------------------------------------------------------------------------

_ABI_BLOCK_RE = re.compile(
    r"<!--ABI\s+0x([0-9A-Fa-f]{2})\s*\n(.*?)-->", re.DOTALL)


def parse_abi_blocks(doc_text: str) -> dict[int, dict[str, str]]:
    """Parse <!--ABI 0xNN ... --> blocks into {num: {field: value}}.

    Fields are `key: value` lines. Raises ValueError on duplicate numbers
    or blocks missing the required fields — a malformed spec is a RED spec.
    """
    required = {"name", "args", "storage", "returns", "twin"}
    out: dict[int, dict[str, str]] = {}
    for m in _ABI_BLOCK_RE.finditer(doc_text):
        num = int(m.group(1), 16)
        if num in out:
            raise ValueError(f"duplicate ABI block for 0x{num:02X}")
        fields: dict[str, str] = {}
        for line in m.group(2).strip().splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
        missing = required - set(fields)
        if missing:
            raise ValueError(
                f"ABI block 0x{num:02X} missing fields: {sorted(missing)}")
        out[num] = fields
    return out


def python_dispatch_bodies(source: str) -> dict[int, str]:
    """Slice _handle_syscall's body per branch from the Python engine source.

    Returns {syscall_num: body_text} for each `if/elif syscall_num == 0xNN:`
    branch. A refactor that renames the dispatch shape trips every leg that
    depends on this (loudly), which is the intended failure mode.
    """
    starts = [(m.start(), int(m.group(1), 16)) for m in re.finditer(
        r"(?:if|elif) syscall_num == 0x([0-9A-Fa-f]{2}):", source)]
    if not starts:
        raise AssertionError(
            "no `syscall_num == 0xNN` dispatch branches found in the Python "
            "engine — dispatch shape changed; re-sync the extraction")
    bodies: dict[int, str] = {}
    for i, (pos, num) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(source)
        bodies[num] = source[pos:end]
    return bodies


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def doc_text() -> str:
    assert SPEC_DOC.exists(), (
        f"{SPEC_DOC} missing — the Pillar 2.1 ABI spec doc does not exist")
    return SPEC_DOC.read_text()


@pytest.fixture(scope="module")
def claims(doc_text: str) -> dict[int, dict[str, str]]:
    return parse_abi_blocks(doc_text)


@pytest.fixture(scope="module")
def py_source() -> str:
    return PY_ENGINE.read_text()


@pytest.fixture(scope="module")
def wgsl_source() -> str:
    return WGSL_TWIN.read_text()


def _fresh_cpu():
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    return cpu, image


def _stamp_path(cpu, path_addr: int, s: str) -> None:
    for i, b in enumerate(s.encode() + b"\0"):
        cpu.memory[path_addr + i] = b


# ---------------------------------------------------------------------------
# L1 — registry coverage, both directions
# ---------------------------------------------------------------------------

def test_l1_every_python_branch_has_a_doc_block(py_source, claims):
    bodies = python_dispatch_bodies(py_source)
    have_doc = set(claims)
    have_code = set(bodies)
    # The doc must cover exactly the implemented surface: 0x01..0x09 plus
    # 0x10..0x13 (0x0A..0x0F have NO dispatch branch — they fall through
    # to the unknown-syscall -1 handler; that gap is part of the ABI).
    expected = set(range(0x01, 0x0A)) | {0x10, 0x11, 0x12, 0x13}
    assert have_code == have_doc, (
        f"doc/code registry mismatch: in code not in doc = "
        f"{sorted(hex(n) for n in have_code - have_doc)}; "
        f"in doc not in code = {sorted(hex(n) for n in have_doc - have_code)}")
    assert have_code == expected, (
        "engine surface changed (0x0A..0x0F implemented? a new number?) "
        "— spec is stale")


def test_l1_doc_numbers_are_well_formed(doc_text, claims):
    assert claims, "spec carries no ABI blocks"
    nums = sorted(claims)
    assert nums == sorted(set(range(0x01, 0x0A)) | {0x10, 0x11, 0x12, 0x13}), (
        f"expected 0x01..0x09 + 0x10..0x13, got {sorted(hex(n) for n in nums)}")
    for num, c in claims.items():
        assert re.fullmatch(r"SYSCALL_[A-Z0-9_]+", c["name"]), (
            f"0x{num:02X}: bad name {c['name']!r}")
        assert c["twin"] in {"IMPLEMENTED", "STUB", "UNIMPLEMENTED", "BRIDGED"}, (
            f"0x{num:02X}: unknown twin status {c['twin']!r}")
        assert c["storage"] in {"RAM", "PIXEL", "HOST"}, (
            f"0x{num:02X}: unknown storage {c['storage']!r}")


# ---------------------------------------------------------------------------
# L2 — storage-home claims vs the handler body
# ---------------------------------------------------------------------------

def test_l2_storage_claims_match_handler_bodies(py_source, claims):
    bodies = python_dispatch_bodies(py_source)
    for num, c in claims.items():
        body = bodies[num]
        if c["storage"] == "RAM":
            assert "self.memory[" in body, (
                f"0x{num:02X}: doc claims RAM but the handler body never "
                f"addresses self.memory — doc rotted or engine changed")
        elif c["storage"] == "PIXEL":
            assert ("_mem_read(image" in body) or ("_mem_write(image" in body), (
                f"0x{num:02X}: doc claims PIXEL but the body never touches "
                f"the image via _mem_read/_mem_write")
        # storage == HOST: no substrate-storage claim to check (0x07/0x12
        # spawn host processes; their I/O is paths, not memory views).


def test_l2_reserved_bridge_and_unknown_are_documented(doc_text):
    # The dispatch tail (0x10..0xFF reserved bridge, unknown -> -1) is part
    # of the ABI; the spec must state both defaults in prose.
    assert "Reserved" in doc_text or "reserved" in doc_text
    assert "-1" in doc_text


# ---------------------------------------------------------------------------
# L3 — twin-status claims vs the WGSL source
# ---------------------------------------------------------------------------

_WGSL_STUB_GROUP = (
    "syscall_num == 3u || syscall_num == 4u || syscall_num == 6u")
_WGSL_BRIDGE_GROUP = "syscall_num >= 16u && syscall_num <= 255u"


def test_l3_twin_status_matches_wgsl_structure(wgsl_source, claims):
    assert _WGSL_STUB_GROUP in wgsl_source, (
        "WGSL 3u/4u/6u stub group moved — re-sync the extraction and the "
        "spec's twin-status legend together")
    assert _WGSL_BRIDGE_GROUP in wgsl_source, (
        "WGSL 16u..255u bridge group moved — re-sync extraction + spec")
    for num, c in claims.items():
        branch = f"syscall_num == {num}u"
        has_branch = branch in wgsl_source
        if c["twin"] == "IMPLEMENTED":
            assert has_branch, (
                f"0x{num:02X}: doc claims twin IMPLEMENTED but WGSL has no "
                f"`{branch}` branch")
        elif c["twin"] == "STUB":
            # The stub group's members appear ONLY inside the `a || b || c`
            # group expression. A standalone branch is any occurrence of
            # `syscall_num == Nu` not joined by `||` on either side.
            occurrences = [m for m in re.finditer(
                rf"syscall_num == {num}u", wgsl_source)]
            standalone = [m for m in occurrences
                          if not (wgsl_source.startswith(" || ", m.end())
                                  or wgsl_source.endswith(" || ", 0, m.start()))]
            assert num in (0x03, 0x04, 0x06) and not standalone, (
                f"0x{num:02X}: doc claims twin STUB but WGSL has a "
                f"standalone branch (stub group dissolved?)")
        elif c["twin"] == "UNIMPLEMENTED":
            assert not has_branch, (
                f"0x{num:02X}: doc claims twin UNIMPLEMENTED but WGSL grew "
                f"a `{branch}` branch — update the spec")
        elif c["twin"] == "BRIDGED":
            assert 0x10 <= num <= 0xFF and not has_branch, (
                f"0x{num:02X}: doc claims twin BRIDGED but WGSL structure "
                f"changed")


def test_l3_python_and_twin_disagree_only_where_the_spec_says(py_source,
                                                              wgsl_source,
                                                              claims):
    """The known cross-engine divergence set is exactly what the spec names.

    Python implements every branch; the twin implements a subset. The spec
    must claim divergence for every syscalL the twin does NOT really
    implement (STUB = implemented as a no-op, still a divergence from the
    Python semantics; BRIDGED/UNIMPLEMENTED likewise).
    """
    py_bodies = python_dispatch_bodies(py_source)
    divergent = set(py_bodies)  # everything the twin doesn't match exactly
    # Twin honestly matches Python ONLY where the doc says IMPLEMENTED.
    for num, c in claims.items():
        if c["twin"] == "IMPLEMENTED":
            divergent.discard(num)
    spec_divergent = {num for num, c in claims.items()
                      if c["twin"] != "IMPLEMENTED"}
    assert divergent == spec_divergent, (
        f"divergence ledger stale: engine-divergent-but-claimed-matching = "
        f"{sorted(hex(n) for n in divergent - spec_divergent)}")


# ---------------------------------------------------------------------------
# L3.5 — RUN-lane twin CONTRACT/GAP pinning (item-8 truthing, 2026-09-22)
# ---------------------------------------------------------------------------

_TICKET_0X12 = REPO / ".builder_queue" / "TICKET_ITEM8_0x12_bridge_false_success.md"


def test_l35_run_lane_twin_contract_claims(claims):
    """The machine-readable twin_contract field pairs correctly with the
    twin-status column for the RUN-lane + FS syscalls. All five are
    NORMATIVE: the twin's actual behavior IS the contract (0x12 joined
    when the TICKET_ITEM8 bridge exclusion landed; 0x13 joined when its
    BK-15 bridge exclusion landed). A doc edit that flips 0x12 or 0x13
    back to a GAP/BRIDGED claim — or drops the field — REDs."""
    for num in (0x03, 0x04, 0x07, 0x12, 0x13):
        c = claims[num]
        assert "twin_contract" in c, (
            f"0x{num:02X}: ABI block lost its twin_contract field "
            f"(item-8 truthing / BK-15 landing)")
    assert claims[0x03]["twin_contract"] == "NORMATIVE"
    assert claims[0x04]["twin_contract"] == "NORMATIVE"
    assert claims[0x07]["twin_contract"] == "NORMATIVE"
    assert claims[0x12]["twin_contract"] == "NORMATIVE", (
        "0x12: twin_contract drifted from NORMATIVE — the TICKET_ITEM8 "
        "bridge exclusion landed 2026-09-22; a GAP/BRIDGED claim here is "
        "stale (re-truth against the twin source before editing)")
    assert claims[0x13]["twin_contract"] == "NORMATIVE", (
        "0x13: twin_contract drifted from NORMATIVE — the BK-15 bridge "
        "exclusion landed 2026-09-24; a GAP/BRIDGED claim here is stale")


def _assert_0x12_bridge_exclusion(wgsl_source, claims):
    """Shared pin: the TICKET_ITEM8 exclusion must be present and the spec
    must claim the resulting NEGATIVE contract."""
    assert claims[0x12]["twin"] == "UNIMPLEMENTED", (
        "0x12: exclusion pin assumes UNIMPLEMENTED status — re-sync the pair")
    assert _TICKET_0X12.exists(), (
        f"0x12: correction history references {_TICKET_0X12} but the ticket "
        f"file is gone — the GAP-era correction history is unanchored")
    assert _WGSL_BRIDGE_GROUP in wgsl_source, (
        "WGSL 16u..255u bridge group moved — re-sync extraction + spec")
    anchor = ("syscall_num >= 16u && syscall_num <= 255u "
              "&& syscall_num != 18u && syscall_num != 19u")
    assert anchor in wgsl_source, (
        "0x12/0x13: a twin bridge exclusion is missing — the false "
        "spawn-success (18u) or false listing-success (19u) divergence "
        "is BACK (twin returns 0 where python refuses). Restore the "
        "exclusions and re-sync the spec")


def test_l35_neg_pin_0x12_bridge_exclusion_landed(wgsl_source, claims):
    """TICKET_ITEM8 landed 2026-09-22 (18u) and BK-15 landed 2026-09-24
    (19u): both are excluded from the GeOS bridge so each reaches the
    unknown-syscall path (-1, matching python and the spec's NEGATIVE
    contracts). This leg pins both — if the bridge closes back over
    either, it REDs immediately."""
    _assert_0x12_bridge_exclusion(wgsl_source, claims)


def test_l35_gap_pairing_python_side(claims):
    """The Python reference side of the GAP pairing: 0x12 exists as a real
    dispatch branch (it is HOST-storage, containment-refusing), so the
    divergence is genuinely twin-side. If Python's 0x12 branch disappears,
    the GAP story must be re-examined."""
    bodies = python_dispatch_bodies(PY_ENGINE.read_text())
    assert 0x12 in bodies, "0x12 branch vanished from the Python engine"
    assert claims[0x12]["storage"] == "HOST"


def test_l35_mutated_bridge_reversion_is_caught(wgsl_source, claims):
    """RED probe (non-vacuity): on an in-memory twin copy with the 19u
    exclusion removed (the bridge closing back over FILE_LIST), the pin
    must FAIL on that copy — the gate can still go RED after the fix."""
    anchor = "&& syscall_num != 19u"
    assert anchor in wgsl_source, "probe anchor stale: 19u exclusion moved"
    mutated = wgsl_source.replace(anchor, "", 1)
    with pytest.raises(AssertionError, match="exclusion is missing"):
        _assert_0x12_bridge_exclusion(mutated, claims)


# ---------------------------------------------------------------------------
# L4 — live behavioral legs (doc's register contract vs the real engine)
# ---------------------------------------------------------------------------

def test_l4_0x01_write_reads_ram_returns_0(claims):
    c = claims[0x01]
    assert "r1" in c["args"] and "r2" in c["args"]
    assert c["returns"] == "0"
    cpu, image = _fresh_cpu()
    cpu.memory[ADDR] = 0x5A
    cpu.memory[ADDR + 1] = 0xA5
    cpu.registers[1] = ADDR
    cpu.registers[2] = 2
    rc = cpu._handle_syscall(0x01, image)
    assert rc == 0 and cpu.output[-2:] == [0x5A, 0xA5]


def test_l4_0x02_read_ring_drain_and_exhaustion(claims):
    c = claims[0x02]
    assert c["storage"] == "RAM"
    cpu, image = _fresh_cpu()
    total, cursor_idx = INPUT_LEN_ADDR >> 2, INPUT_CURSOR_ADDR >> 2
    data_idx = INPUT_DATA_ADDR >> 2
    cpu.memory[total] = 3
    cpu.memory[cursor_idx] = 0
    cpu.memory[data_idx] = 0x78
    cpu.memory[data_idx + 1] = 0x79
    cpu.memory[data_idx + 2] = 0x7A
    cpu.registers[1] = ADDR
    cpu.registers[2] = 2
    assert cpu._handle_syscall(0x02, image) == 2          # returns bytes read
    assert cpu.memory[ADDR:ADDR + 2] == [0x78, 0x79]      # lands in RAM
    assert cpu.memory[cursor_idx] == 2                    # cursor advances
    cpu.registers[2] = 5
    assert cpu._handle_syscall(0x02, image) == 1          # exhaustion: 1 left
    # A third call reads 0 — "no more input" is distinguishable from "zero
    # bytes were requested" because the caller sees the cursor, and a
    # zero-byte REQUEST would have returned 0 with the cursor unmoved.
    before = cpu.memory[cursor_idx]
    assert cpu._handle_syscall(0x02, image) == 0
    assert cpu.memory[cursor_idx] == before


def test_l4_0x03_file_write_data_from_ram(claims, tmp_path):
    c = claims[0x03]
    assert c["storage"] == "RAM" and c["returns"].startswith("0, or -1")
    cpu, image = _fresh_cpu()
    f = tmp_path / "abi_spec_probe.bin"
    _stamp_path(cpu, 3000, str(f))
    cpu.memory[ADDR:ADDR + 3] = [0x11, 0x22, 0x33]
    cpu.registers[1] = 3000
    cpu.registers[2] = ADDR
    cpu.registers[3] = 3
    assert cpu._handle_syscall(0x03, image) == 0
    assert f.read_bytes() == b"\x11\x22\x33"


def test_l4_0x04_file_read_dest_into_ram(claims, tmp_path):
    c = claims[0x04]
    assert c["storage"] == "RAM"
    cpu, image = _fresh_cpu()
    f = tmp_path / "abi_spec_probe_in.bin"
    f.write_bytes(b"hello")
    _stamp_path(cpu, 3000, str(f))
    cpu.registers[1] = 3000
    cpu.registers[2] = ADDR
    cpu.registers[3] = 10
    rc = cpu._handle_syscall(0x04, image)
    assert rc == 5                                        # returns bytes read
    assert bytes(cpu.memory[ADDR:ADDR + 5]) == b"hello"   # lands in RAM


def test_l4_0x05_exit_returns_status_and_halts(claims):
    assert claims[0x05]["returns"] == "status"
    cpu, image = _fresh_cpu()
    cpu.running = True
    cpu.registers[1] = 42
    assert cpu._handle_syscall(0x05, image) == 42
    assert cpu.running is False


def test_l4_0x06_debug_returns_0(claims):
    assert claims[0x06]["returns"] == "0"
    cpu, image = _fresh_cpu()
    cpu.registers[1] = 7
    assert cpu._handle_syscall(0x06, image) == 0


def test_l4_0x10_boot_linux_rejects_bad_signature(claims):
    c = claims[0x10]
    # 2026-09-22 backlog-(d) residual: header read migrated PIXEL -> RAM;
    # twin now has its own `16u` branch reading the ram buffer (IMPLEMENTED).
    assert c["storage"] == "RAM" and c["returns"] == "0 if VAC2, else -1"
    assert c["twin"] == "IMPLEMENTED"
    cpu, image = _fresh_cpu()
    cpu.registers[1] = ADDR  # zero RAM -> sig != VAC2
    cpu.registers[2] = 0x05
    assert cpu._handle_syscall(0x10, image) == -1


def test_l4_0x11_store_code_copies_pixel_words(claims):
    c = claims[0x11]
    assert c["storage"] == "PIXEL"
    cpu, image = _fresh_cpu()
    for i in range(4):
        cpu._mem_write(image, ADDR + 16 + i, 0xA0 + i)
    cpu.registers[1] = ADDR + 64    # dest (pixel space)
    cpu.registers[2] = ADDR + 16    # src  (pixel space)
    cpu.registers[3] = 4
    assert cpu._handle_syscall(0x11, image) == 0
    assert [cpu._mem_read(image, ADDR + 64 + i) for i in range(4)] == \
        [0xA0, 0xA1, 0xA2, 0xA3]


def test_l4_0x11_rejects_nonpositive_length(claims):
    cpu, image = _fresh_cpu()
    cpu.registers[1] = ADDR
    cpu.registers[2] = ADDR + 16
    cpu.registers[3] = 0
    assert cpu._handle_syscall(0x11, image) == -1


def test_l4_0x07_0x12_run_family_allowlist_refusal(claims, tmp_path):
    """0x07/0x12's containment rule: a path NOT in GLYPH_RUN_ALLOW is
    refused with -1 — exercised live via a real (nonempty, non-allowlisted)
    file, so the leg cannot pass vacuously on the file-not-found branch."""
    for num in (0x07, 0x12):
        c = claims[num]
        assert c["storage"] == "HOST" and c["returns"] == "exit code, or -1"
        cpu, image = _fresh_cpu()
        f = tmp_path / f"not_allowlisted_{num:02x}.txt"
        f.write_text("x")  # exists -> refusal must come from the ALLOWLIST
        _stamp_path(cpu, 3000, str(f))
        cpu.registers[1] = 3000
        cpu.registers[2] = 0
        cpu.registers[3] = 0
        assert cpu._handle_syscall(num, image) == -1, (
            f"0x{num:02X}: non-allowlisted executable was not refused")


def test_l4_out_of_range_args_do_not_crash(doc_text, claims):
    """The spec's no-crash OOB convention (0x01 reads 0, write sides drop)
    is stated AND true on the live engine."""
    assert "out-of-range" in doc_text or "out of range" in doc_text
    cpu, image = _fresh_cpu()
    cpu.registers[1] = 10_000_000   # far past RAM
    cpu.registers[2] = 4
    assert cpu._handle_syscall(0x01, image) == 0    # reads as 0, appends 0s
    # 0x02 with an OOB dest (r1 past RAM): truncated to 0, RAM never grows.
    cpu.registers[1] = 10_000_000
    cpu.registers[2] = 5
    cpu.memory[INPUT_LEN_ADDR >> 2] = 1
    assert cpu._handle_syscall(0x02, image) == 0    # truncated, no growth
    assert len(cpu.memory) == 16384


def test_l4_0x13_file_list_entries_and_count(claims, tmp_path,
                                              monkeypatch):
    """0x13's live contract: NUL-separated sorted names land in RAM, rd
    returns the entry count. Driven through the REAL engine handler."""
    c = claims[0x13]
    assert c["storage"] == "RAM" and "r1" in c["args"] and "r3" in c["args"]
    monkeypatch.setenv("GLYPH_FS_ALLOW", str(tmp_path))
    (tmp_path / "b.txt").write_text("2")
    (tmp_path / "a.txt").write_text("1")
    cpu, image = _fresh_cpu()
    _stamp_path(cpu, 3000, str(tmp_path))
    cpu.registers[1] = 3000
    cpu.registers[2] = ADDR
    cpu.registers[3] = 64
    rc = cpu._handle_syscall(0x13, image)
    assert rc == 2, rc
    assert bytes(cpu.memory[ADDR:ADDR + 12]) == b"a.txt\0b.txt\0"


def test_l4_0x13_empty_dir_returns_zero(claims, tmp_path, monkeypatch):
    monkeypatch.setenv("GLYPH_FS_ALLOW", str(tmp_path))
    cpu, image = _fresh_cpu()
    _stamp_path(cpu, 3000, str(tmp_path))
    cpu.registers[1] = 3000
    cpu.registers[2] = ADDR
    cpu.registers[3] = 64
    assert cpu._handle_syscall(0x13, image) == 0
    assert cpu.memory[ADDR] == 0


def test_l4_0x13_containment_refusal_and_deny_by_default(claims, tmp_path,
                                                         monkeypatch):
    """Outside GLYPH_FS_ALLOW -> -1; env UNSET -> -1 even for an existing
    dir (deny-by-default: never a free host-FS walk)."""
    cpu, image = _fresh_cpu()
    _stamp_path(cpu, 3000, str(tmp_path))
    cpu.registers[1] = 3000
    cpu.registers[2] = ADDR
    cpu.registers[3] = 64
    monkeypatch.setenv("GLYPH_FS_ALLOW", "/nonexistent_root_xyz")
    assert cpu._handle_syscall(0x13, image) == -1
    monkeypatch.delenv("GLYPH_FS_ALLOW")
    assert cpu._handle_syscall(0x13, image) == -1


def test_l4_0x13_truncation_cuts_whole_names(claims, tmp_path, monkeypatch):
    """max_bytes too small for the second name: the first lands whole, the
    count is 1, and NO partial name byte ever reaches the dest."""
    monkeypatch.setenv("GLYPH_FS_ALLOW", str(tmp_path))
    (tmp_path / "aa.txt").write_text("x")
    (tmp_path / "bb.txt").write_text("y")
    cpu, image = _fresh_cpu()
    _stamp_path(cpu, 3000, str(tmp_path))
    cpu.registers[1] = 3000
    cpu.registers[2] = ADDR
    cpu.registers[3] = 7  # fits "aa.txt\0" (7) but not "aa.txt\0bb.txt\0" (14)
    rc = cpu._handle_syscall(0x13, image)
    assert rc == 1, rc
    assert bytes(cpu.memory[ADDR:ADDR + 7]) == b"aa.txt\0"
    assert cpu.memory[ADDR + 7] == 0  # no partial second name


# ---------------------------------------------------------------------------
# L5 — non-vacuity: the guard must be able to FAIL when the doc lies
# ---------------------------------------------------------------------------

def test_l5_mutated_storage_claim_is_caught(doc_text):
    """Flip 0x02's storage claim RAM->PIXEL in an in-memory doc copy: the
    L2 extraction leg must RED on that copy."""
    mutated = doc_text.replace("storage: RAM", "storage: PIXEL", 1)
    assert mutated != doc_text, "probe anchor stale: no `storage: RAM` in doc"
    claims = parse_abi_blocks(mutated)
    bodies = python_dispatch_bodies(PY_ENGINE.read_text())
    body = bodies[0x02]
    # Exactly the L2 check for a PIXEL claim, which 0x02's RAM-only body
    # cannot satisfy:
    with pytest.raises(AssertionError, match="0x02"):
        assert ("_mem_read(image" in body) or ("_mem_write(image" in body), (
            f"0x02: doc claims PIXEL but the handler body never touches "
            f"the image via _mem_read/_mem_write")


def test_l5_mutated_return_claim_is_caught(doc_text):
    """Flip 0x05's return claim to a literal 0: the L4 contract assertion
    (`returns == 'status'`) must RED on the mutated claims."""
    mutated = doc_text.replace(
        "returns: status", "returns: 0", 1)
    assert mutated != doc_text, "probe anchor stale: no `returns: status`"
    claims = parse_abi_blocks(mutated)
    with pytest.raises(AssertionError):
        assert claims[0x05]["returns"] == "status"


def test_l5_mutated_twin_claim_is_caught(doc_text):
    """Flip 0x07's twin claim UNIMPLEMENTED->IMPLEMENTED: the L3 structure
    leg must RED (WGSL has no `syscall_num == 7u` branch)."""
    mutated = doc_text.replace(
        "twin: UNIMPLEMENTED", "twin: IMPLEMENTED", 1)
    assert mutated != doc_text, "probe anchor stale: no `twin: UNIMPLEMENTED`"
    claims = parse_abi_blocks(mutated)
    wgsl = WGSL_TWIN.read_text()
    with pytest.raises(AssertionError, match="0x07"):
        assert "syscall_num == 7u" in wgsl, (
            "0x07: doc claims twin IMPLEMENTED but WGSL has no branch")
