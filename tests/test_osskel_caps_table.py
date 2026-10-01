"""
tests/test_osskel_caps_table.py — Gate for OS-SKEL-R2 Phase 3 Step 4: CapTable.grant / revoke / held.
"""

import pytest

import tools.geos_caps as geos_caps
from tools.geos_caps import (
    CAP_BOOT_VERIFY,
    CAP_FS_WRITE,
    CAP_NET,
    CAP_OBSERVE,
    CAP_ROOT,
    CapTable,
    get_granter_mask,
    set_granter_mask,
)


@pytest.fixture(autouse=True)
def restore_granter_mask():
    """Ensure granter mask isolation across tests and verify it is unbound after each test."""
    old_mask = get_granter_mask()
    set_granter_mask(None)
    try:
        yield
    finally:
        set_granter_mask(old_mask)
        assert get_granter_mask() is None


def test_l1_no_amplification_raises() -> None:
    """L1: granter CAP_FS_WRITE|CAP_OBSERVE; grant(pid, CAP_FS_WRITE) returns
    the mask and held(pid) sees it; grant(pid, CAP_NET) raises PermissionError
    and the message contains net (canonical name) and the pid; the mask is
    unchanged after the refusal (non-mutation).
    """
    set_granter_mask(CAP_FS_WRITE | CAP_OBSERVE)
    table = CapTable(grants={1: 0})
    res = table.grant(1, CAP_FS_WRITE)
    assert res == CAP_FS_WRITE
    assert table.held(1) == CAP_FS_WRITE

    with pytest.raises(PermissionError) as exc_info:
        table.grant(1, CAP_NET)
    msg = str(exc_info.value)
    assert "net" in msg
    assert "1" in msg
    assert table.held(1) == CAP_FS_WRITE


def test_l2_cap_root_not_a_wildcard() -> None:
    """L2: granter holds CAP_ROOT only; grant(pid, CAP_FS_WRITE) still raises
    (root is not a wildcard, I1); granting CAP_ROOT from a CAP_ROOT granter succeeds.
    """
    set_granter_mask(CAP_ROOT)
    table = CapTable(grants={1: 0})
    with pytest.raises(PermissionError):
        table.grant(1, CAP_FS_WRITE)
    assert table.held(1) == 0

    res = table.grant(1, CAP_ROOT)
    assert res == CAP_ROOT
    assert table.held(1) == CAP_ROOT


def test_l3_revoke_root_requires_force() -> None:
    """L3: revoke(pid, CAP_ROOT) raises PermissionError and CAP_ROOT stays held;
    revoke(pid, CAP_ROOT, force=True) removes it and returns the new mask.
    """
    table = CapTable(grants={1: CAP_ROOT | CAP_FS_WRITE})
    with pytest.raises(PermissionError):
        table.revoke(1, CAP_ROOT)
    assert table.held(1) == CAP_ROOT | CAP_FS_WRITE

    res = table.revoke(1, CAP_ROOT, force=True)
    assert res == CAP_FS_WRITE
    assert table.held(1) == CAP_FS_WRITE


def test_l4_unknown_pid_raises_keyerror() -> None:
    """L4: held(999), grant(999, CAP_NET) and revoke(999, CAP_NET) all raise KeyError."""
    set_granter_mask(CAP_NET)
    table = CapTable(grants={1: 0})
    with pytest.raises(KeyError):
        table.held(999)
    with pytest.raises(KeyError):
        table.grant(999, CAP_NET)
    with pytest.raises(KeyError):
        table.revoke(999, CAP_NET)


def test_l5_grant_held_roundtrip() -> None:
    """L5: grant->held() round-trips a multi-bit mask exactly, and a second grant
    is idempotent (same value, no double-count).
    """
    mask = CAP_FS_WRITE | CAP_OBSERVE | CAP_BOOT_VERIFY
    set_granter_mask(mask)
    table = CapTable(grants={42: 0})
    ret1 = table.grant(42, mask)
    assert ret1 == mask
    assert table.held(42) == mask

    ret2 = table.grant(42, mask)
    assert ret2 == mask
    assert table.held(42) == mask


def test_l6_unbound_granter_refuses_loudly() -> None:
    """L6: with no granter bound, grant raises RuntimeError and the mask is
    unchanged (refusal, not a silent no-op).
    """
    assert get_granter_mask() is None
    table = CapTable(grants={1: CAP_FS_WRITE})
    with pytest.raises(RuntimeError):
        table.grant(1, CAP_OBSERVE)
    assert table.held(1) == CAP_FS_WRITE


def test_l7_binding_hygiene() -> None:
    """L7: set_granter_mask("x") -> TypeError; set_granter_mask(-1) -> ValueError (or TypeError);
    set_granter_mask(1 << 20) (unknown bit) -> ValueError; set_granter_mask(None) round-trips
    to get_granter_mask() is None; and neither helper name appears in geos_caps.__all__.
    """
    with pytest.raises(TypeError):
        set_granter_mask("x")  # type: ignore[arg-type]

    with pytest.raises((ValueError, TypeError)):
        set_granter_mask(-1)

    with pytest.raises(ValueError):
        set_granter_mask(1 << 20)

    set_granter_mask(CAP_FS_WRITE)
    assert get_granter_mask() == CAP_FS_WRITE
    set_granter_mask(None)
    assert get_granter_mask() is None

    assert "set_granter_mask" not in geos_caps.__all__
    assert "get_granter_mask" not in geos_caps.__all__
    assert "_granter_mask" not in geos_caps.__all__
