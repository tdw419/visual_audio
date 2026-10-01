"""tests/test_obs1_mcp_transport_identity.py — OBS-1: MCP-transport write-identity gate.

Roadmap row: OBS-1 in systems/GLYPH_SELF_HOSTING_ROADMAP.md (line 334).
Ruling: .builder_queue/RULING_lane_supply_20260912.md § Ruled now.

Contracts verified:
  L1: transport positive — publish write_id 1 through GeosEmitter with
      writer="obs1-stage-a", drive tools/geos_observation_server.py over stdio
      (mcp ClientSession + StdioServerParameters, GEOS_IMAGE_DIR = publish dir),
      and assert geos_surface_meta reports write_id == 1, writer == "obs1-stage-a",
      image_md5 matches served kernel_memory.npy, and non-null sidecar_file.
      Also verify geos_read_surface returns raw ASCII canvas text over stdio.
  L2: monotonic over the transport — in the SAME stdio session, publish #2 with
      writer="obs1-stage-b" and assert geos_surface_meta reports write_id == 2,
      new writer, and updated image_md5 (no stale identity served). Also verify
      load_archived_write(1) still retrieves stage-a's bytes.
  L3: negative leg, loud — point server session at a directory holding an image
      and NO sidecar; assert write_id and writer are None (absence reported, not
      invented), and take_witness(750, expect_write_id=1, image_dir=bare_dir)
      raises the named WitnessMismatch with WITNESS_MISMATCH in message.
  L4: not vacuous (discriminating probes) —
      (a) run L1 identity check helper over real transport payload -> passes,
          then over synthetic payload with write_id=None -> raises AssertionError;
      (b) run L3 refusal helper over real bare-dir witness -> raises WitnessMismatch,
          then over synthetic payload with write_id=1 -> does NOT raise.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _mcp_available() -> bool:
    import importlib.util
    if importlib.util.find_spec("mcp") is None:
        return False
    try:
        from mcp import ClientSession, StdioServerParameters  # noqa: F401
        from mcp.client.stdio import stdio_client             # noqa: F401
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _mcp_available(),
    reason="mcp unavailable (run under py3.12)",
)

if _mcp_available():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from tools.geos_witness import (
        load_archived_write, take_witness, WitnessMismatch,
    )
else:
    ClientSession = Any  # type: ignore
    StdioServerParameters = Any  # type: ignore
    stdio_client = None  # type: ignore
    take_witness = None  # type: ignore
    load_archived_write = None  # type: ignore

    class WitnessMismatch(Exception):  # type: ignore
        pass

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.baker import preemptive_kernel_image        # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.geos_emit import (                                    # noqa: E402
    GeosEmitter, encode_mailbox_word, ACK_SENTINEL,
)

PUBLISH = "publish"


def _bake(tmp: Path) -> Path:
    out = tmp / "gh26.glyph.npy"
    preemptive_kernel_image(build_default_atlas(), timer_quantum=20,
                            out_path=out)
    return out


def _publish_dir(tmp: Path) -> Path:
    """Run the kernel once with publishing so a committed image exists.
    The launcher's own sidecars are then removed: `GeosEmitter` derives its
    `write_id` from the sidecars present in the dir, so leaving them would seed
    the counter (the emitter-path legs L1..L4 assert a counter starting at 1)."""
    img = _bake(tmp)
    pub = tmp / PUBLISH
    receipt = GlyphRunner(img, ram_words=16384).drive(
        publish_dir=pub, max_instructions=60000)
    assert receipt["halted"] and not receipt["faulted"], receipt
    for meta in pub.glob("*.meta.json"):
        meta.unlink()
    return pub


def _acked(tmp: Path) -> Path:
    """Create the ack marker (human-gate satisfied on disk)."""
    ack = tmp / ".geos_emit_ack"
    ack.write_text(ACK_SENTINEL + " — authorized by Jericho (gate fixture)")
    return ack


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


async def _run_stdio_session(
    image_dir: Path,
    action_coro,
    timeout: float = 60.0,
):
    """Spawn the committed geos_observation_server over stdio and run action_coro(session)."""
    params = StdioServerParameters(
        command="/usr/bin/python3",
        args=[str(_REPO / "tools" / "geos_observation_server.py")],
        env={"PATH": os.environ["PATH"], "GEOS_IMAGE_DIR": str(image_dir)},
    )

    async def _runner():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_list = await session.list_tools()
                tool_names = [t.name for t in tools_list.tools]
                assert "geos_surface_meta" in tool_names, (
                    f"geos_surface_meta not exposed by server: {tool_names}"
                )
                assert "geos_read_surface" in tool_names, (
                    f"geos_read_surface not exposed by server: {tool_names}"
                )
                return await action_coro(session)

    return await asyncio.wait_for(_runner(), timeout=timeout)


async def _call_json_tool(session: ClientSession, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    result = await session.call_tool(tool_name, args)
    assert result.content and len(result.content) > 0, f"Empty content from {tool_name}"
    return json.loads(result.content[0].text)


async def _call_text_tool(session: ClientSession, tool_name: str, args: Dict[str, Any]) -> str:
    result = await session.call_tool(tool_name, args)
    assert result.content and len(result.content) > 0, f"Empty content from {tool_name}"
    return result.content[0].text


def check_l1_transport_identity(
    meta_payload: Dict[str, Any],
    expected_writer: str,
    expected_md5: str,
    expected_write_id: int = 1,
) -> None:
    """Validate write-identity attributes reported by geos_surface_meta over stdio transport."""
    source = meta_payload.get("source")
    assert source is not None, "Missing 'source' in geos_surface_meta payload"
    actual_write_id = source.get("write_id")
    assert actual_write_id == expected_write_id, (
        f"write_id mismatch: expected {expected_write_id}, got {actual_write_id}"
    )
    actual_writer = source.get("writer")
    assert actual_writer == expected_writer, (
        f"writer mismatch: expected {expected_writer!r}, got {actual_writer!r}"
    )
    actual_md5 = source.get("image_md5")
    assert actual_md5 == expected_md5, (
        f"image_md5 mismatch: expected {expected_md5}, got {actual_md5}"
    )
    assert source.get("sidecar_file") is not None, (
        "Missing 'sidecar_file' in geos_surface_meta source"
    )


def check_l3_witness_identity(
    witness_payload: Dict[str, Any],
    expected_write_id: int = 1,
) -> Dict[str, Any]:
    """Enforce that witness payload carries expected write_id, raising WitnessMismatch if not."""
    served_id = witness_payload.get("write_id")
    if served_id != expected_write_id:
        raise WitnessMismatch(
            f"WITNESS_MISMATCH: served write_id {served_id} != expected {expected_write_id}"
        )
    return witness_payload


# ── Leg 1: transport positive ──────────────────────────────────────────

def test_l1_transport_positive(tmp_path: Path):
    """L1: transport positive — publish #1 via GeosEmitter with writer='obs1-stage-a'.
    Over stdio MCP transport, geos_surface_meta reports write_id=1, writer='obs1-stage-a',
    image_md5 equal to served kernel_memory.npy, and non-null sidecar_file.
    geos_read_surface returns raw ASCII canvas text (not JSON, not an error)."""
    pub = _publish_dir(tmp_path)
    ack = _acked(tmp_path)
    em = GeosEmitter(publish_dir=pub, ack_file=ack)

    # Publish 1: word 750, writer "obs1-stage-a"
    rc1 = em.emit({
        "kind": "post", "box": 0, "op": 1, "payload": 2,
        "word": 750, "writer": "obs1-stage-a",
    })
    assert rc1["committed"] is True

    served_npy = pub / "kernel_memory.npy"
    expected_md5 = _md5(served_npy)

    async def _action(session):
        meta = await _call_json_tool(session, "geos_surface_meta", {"vx": 0, "vy": 0, "w": 80, "h": 25})
        surf_text = await _call_text_tool(session, "geos_read_surface", {"vx": 0, "vy": 0, "w": 80, "h": 25})
        return meta, surf_text

    meta1, surf_text = asyncio.run(_run_stdio_session(pub, _action))

    # Validate identity via helper
    check_l1_transport_identity(
        meta1,
        expected_writer="obs1-stage-a",
        expected_md5=expected_md5,
        expected_write_id=1,
    )

    # Canvas tool check over the same transport session
    assert isinstance(surf_text, str) and len(surf_text) > 0
    assert not surf_text.startswith("{"), f"Canvas should not be JSON: {surf_text[:40]}"
    assert not surf_text.startswith("GEOS_OBSERVATION_UNAVAILABLE"), (
        f"Canvas returned error: {surf_text[:60]}"
    )
    assert "\n" in surf_text or len(surf_text) >= 80, "Canvas should contain multi-line text"


# ── Leg 2: monotonic over the transport ─────────────────────────────────

def test_l2_monotonic_over_transport(tmp_path: Path):
    """L2: monotonic over the transport — publish #2 in the SAME stdio session.
    geos_surface_meta must report write_id=2 and writer='obs1-stage-b', with image_md5
    matching the newly served image. load_archived_write(1) still retrieves stage-a's bytes."""
    pub = _publish_dir(tmp_path)
    ack = _acked(tmp_path)
    em = GeosEmitter(publish_dir=pub, ack_file=ack)

    # Publish 1: word 750, writer "obs1-stage-a"
    rc1 = em.emit({
        "kind": "post", "box": 0, "op": 1, "payload": 2,
        "word": 750, "writer": "obs1-stage-a",
    })
    assert rc1["committed"] is True

    async def _action(session):
        meta1 = await _call_json_tool(session, "geos_surface_meta", {"vx": 0, "vy": 0, "w": 80, "h": 25})

        # In the SAME session, publish #2 with different writer
        rc2 = em.emit({
            "kind": "post", "box": 0, "op": 1, "payload": 3,
            "word": 754, "writer": "obs1-stage-b",
        })
        assert rc2["committed"] is True

        meta2 = await _call_json_tool(session, "geos_surface_meta", {"vx": 0, "vy": 0, "w": 80, "h": 25})
        return meta1, meta2

    meta1, meta2 = asyncio.run(_run_stdio_session(pub, _action))

    # Check meta1
    src1 = meta1["source"]
    assert src1["write_id"] == 1
    assert src1["writer"] == "obs1-stage-a"

    # Check meta2
    src2 = meta2["source"]
    expected_md5_2 = _md5(pub / "kernel_memory.npy")
    assert src2["write_id"] == 2
    assert src2["writer"] == "obs1-stage-b"
    assert src2["image_md5"] == expected_md5_2
    assert src2["write_id"] > src1["write_id"]
    assert src2["image_md5"] != src1["image_md5"]

    # Archive retrieval: write 1 is preserved and distinguishable
    words1, wid1, writer1, img1, md51 = load_archived_write(1, pub)
    assert wid1 == 1
    assert writer1 == "obs1-stage-a"
    assert words1[750] == encode_mailbox_word(1, 2)
    assert img1.exists()
    assert md51 == _md5(img1)

    # Write 2 is also archived and distinguishable
    words2, wid2, writer2, img2, md52 = load_archived_write(2, pub)
    assert wid2 == 2
    assert writer2 == "obs1-stage-b"
    assert words2[754] == encode_mailbox_word(1, 3)
    assert img2.exists()
    assert md52 == _md5(img2)


# ── Leg 3: negative leg, loud ──────────────────────────────────────────

def test_l3_negative_leg_loud(tmp_path: Path):
    """L3: negative leg, loud — point server session at directory holding an image and NO sidecar.
    Assert (a) source['write_id'] is None and source['writer'] is None (absence reported, not invented).
    Assert (b) identity-demanding read take_witness(750, expect_write_id=1, image_dir=bare_dir)
    raises the named WitnessMismatch with WITNESS_MISMATCH in message."""
    bare_dir = tmp_path / "bare_dir"
    bare_dir.mkdir(parents=True, exist_ok=True)
    bare_npy = bare_dir / "kernel_memory.npy"
    np.save(bare_npy, np.zeros(16384, dtype=np.uint32))

    async def _action(session):
        return await _call_json_tool(session, "geos_surface_meta", {"vx": 0, "vy": 0, "w": 80, "h": 25})

    meta = asyncio.run(_run_stdio_session(bare_dir, _action))
    source = meta.get("source", {})

    # (a) Transport reports absence rather than inventing an identity
    assert source.get("write_id") is None
    assert source.get("writer") is None
    assert source.get("sidecar_file") is None
    assert source.get("image_md5") is None

    # (b) Identity-demanding read refuses loudly with named WitnessMismatch
    with pytest.raises(WitnessMismatch) as exc_info:
        take_witness(750, expect_write_id=1, image_dir=bare_dir)

    err_msg = str(exc_info.value)
    assert "WITNESS_MISMATCH" in err_msg, f"Expected WITNESS_MISMATCH in error message: {err_msg}"
    assert "None" in err_msg, f"Expected 'None' (served id) in message: {err_msg}"
    assert "1" in err_msg, f"Expected expected id '1' in message: {err_msg}"


# ── Leg 4: discriminating probes (not vacuous) ─────────────────────────

def test_l4_not_vacuous_probes(tmp_path: Path):
    """L4: in-gate discriminating probes (mirrors WF-1 L1b pattern):
    (a) L1 identity check passes over real transport payload, but raises AssertionError
        over synthetic payload with write_id=None (and over wrong writer);
    (b) L3 refusal helper raises WitnessMismatch on real bare-dir witness, but does NOT
        raise on synthetic payload whose write_id equals the expectation."""
    # Probe (a): L1 identity check helper discrimination
    pub = _publish_dir(tmp_path)
    ack = _acked(tmp_path)
    em = GeosEmitter(publish_dir=pub, ack_file=ack)
    em.emit({
        "kind": "post", "box": 0, "op": 1, "payload": 2,
        "word": 750, "writer": "obs1-stage-a",
    })
    expected_md5 = _md5(pub / "kernel_memory.npy")

    async def _action(session):
        return await _call_json_tool(session, "geos_surface_meta", {"vx": 0, "vy": 0, "w": 80, "h": 25})

    real_meta = asyncio.run(_run_stdio_session(pub, _action))

    # 1. Passes over real transport payload
    check_l1_transport_identity(
        real_meta,
        expected_writer="obs1-stage-a",
        expected_md5=expected_md5,
        expected_write_id=1,
    )

    # 2. Must raise on synthetic payload with write_id=None
    synthetic_meta = copy.deepcopy(real_meta)
    synthetic_meta["source"]["write_id"] = None
    with pytest.raises(AssertionError) as exc_a:
        check_l1_transport_identity(
            synthetic_meta,
            expected_writer="obs1-stage-a",
            expected_md5=expected_md5,
            expected_write_id=1,
        )
    assert "write_id mismatch" in str(exc_a.value)

    # Also proves discrimination against mismatched writer
    synthetic_meta_writer = copy.deepcopy(real_meta)
    synthetic_meta_writer["source"]["writer"] = "wrong-writer"
    with pytest.raises(AssertionError) as exc_w:
        check_l1_transport_identity(
            synthetic_meta_writer,
            expected_writer="obs1-stage-a",
            expected_md5=expected_md5,
            expected_write_id=1,
        )
    assert "writer mismatch" in str(exc_w.value)

    # Probe (b): L3 refusal helper discrimination
    bare_dir = tmp_path / "bare_dir_l4"
    bare_dir.mkdir(parents=True, exist_ok=True)
    np.save(bare_dir / "kernel_memory.npy", np.zeros(16384, dtype=np.uint32))

    # Real bare-dir witness (expect_write_id=None returns unverified witness)
    real_bare_witness = take_witness(750, expect_write_id=None, image_dir=bare_dir)
    assert real_bare_witness["write_id"] is None

    # 1. Refusal helper must raise WitnessMismatch on real bare-dir witness
    with pytest.raises(WitnessMismatch) as exc_b:
        check_l3_witness_identity(real_bare_witness, expected_write_id=1)
    err_b = str(exc_b.value)
    assert "WITNESS_MISMATCH" in err_b
    assert "None" in err_b
    assert "1" in err_b

    # 2. Refusal helper must NOT raise on synthetic payload whose write_id equals expectation
    synthetic_witness = copy.deepcopy(real_bare_witness)
    synthetic_witness["write_id"] = 1
    res = check_l3_witness_identity(synthetic_witness, expected_write_id=1)
    assert res["write_id"] == 1
