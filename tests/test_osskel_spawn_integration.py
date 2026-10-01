"""
tests/test_osskel_spawn_integration.py — Gate for OS-SKEL-R2 Phase 3 Step 7:
cross-module spawn() integration.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import pytest

import tools.geos_aspace as geos_aspace
import tools.geos_caps as geos_caps
import tools.geos_devtab as geos_devtab
import tools.geos_proctab as geos_proctab
import tools.geos_spawn as geos_spawn

from tools.geos_aspace import AsidAllocator, set_asid_allocator
from tools.geos_caps import (
    CAP_BOOT_VERIFY,
    CAP_DEV_MMIO,
    CAP_FS_ADMIN,
    CAP_FS_WRITE,
    CAP_KILL,
    CAP_NET,
    CAP_OBSERVE,
    CAP_ROOT,
    CAP_SPAWN,
    CapTable,
    set_granter_mask,
)
from tools.geos_devtab import (
    DeviceConflict,
    DeviceDescriptor,
    Devtab,
    Driver,
    device_id,
)
from tools.geos_proctab import (
    STATE_READY,
    STATE_RUNNING,
    ProcessDescriptor,
    Proctab,
)
from tools.geos_spawn import BoxAllocator, spawn


@dataclass
class SpawnEnv:
    proctab: Proctab
    captab: CapTable
    devtab: Devtab
    box_alloc: BoxAllocator
    asid_alloc: AsidAllocator
    device: DeviceDescriptor
    driver: Driver


@pytest.fixture
def env():
    """Fixture providing fresh instances and hooks for each test leg."""
    proctab = Proctab()
    captab = CapTable()
    devtab = Devtab()
    box_alloc = BoxAllocator()
    asid_alloc = AsidAllocator()

    set_asid_allocator(asid_alloc)
    set_granter_mask(CAP_SPAWN | CAP_DEV_MMIO | CAP_OBSERVE)

    device = DeviceDescriptor(
        dev_id=device_id(0x1001, 0x0003),
        name="uart0",
        window_lo=0x40,
        window_hi=0x48,
        irq_word=0x48,
    )
    devtab.register_device(device)
    driver = Driver("uart-pl011", vendor=0x1001, dev_class=0x0003)

    test_env = SpawnEnv(
        proctab=proctab,
        captab=captab,
        devtab=devtab,
        box_alloc=box_alloc,
        asid_alloc=asid_alloc,
        device=device,
        driver=driver,
    )

    try:
        yield test_env
    finally:
        set_asid_allocator(None)
        set_granter_mask(None)


def test_l1_happy_path(env: SpawnEnv) -> None:
    """L1 happy path: spawn with a driver."""
    caps = CAP_SPAWN | CAP_DEV_MMIO
    desc = spawn(
        env.proctab,
        env.captab,
        env.devtab,
        env.box_alloc,
        caps=caps,
        driver=env.driver,
        device=env.device,
    )
    assert desc.state == STATE_READY
    assert desc.pid == 0
    assert desc.asid == 0
    assert desc.box == 0
    assert env.captab.held(0) == caps
    assert type(desc) is ProcessDescriptor
    assert desc.meta["aspace"].asid == 0
    assert 0 in env.asid_alloc.live()
    assert desc.meta["binding"].device == env.device.name
    assert env.devtab.grant_words(desc.meta["binding"]) == (
        env.device.window_lo,
        env.device.window_hi,
    )


def test_l2_cap_dev_mmio_missing(env: SpawnEnv) -> None:
    """L2 CAP_DEV_MMIO missing: same call, caps=CAP_OBSERVE, driver+device given."""
    with pytest.raises(PermissionError) as excinfo:
        spawn(
            env.proctab,
            env.captab,
            env.devtab,
            env.box_alloc,
            caps=CAP_OBSERVE,
            driver=env.driver,
            device=env.device,
        )
    assert "CAP_DEV_MMIO" in str(excinfo.value)
    assert env.proctab.procs == {}
    assert env.proctab.pids.live() == []
    assert env.asid_alloc.live() == []
    assert env.box_alloc.live() == []
    assert env.devtab.bindings == []
    assert env.captab.grants == {}


def test_l3_unbound_hooks(env: SpawnEnv) -> None:
    """L3 unbound hooks: missing allocator / missing granter."""
    set_asid_allocator(None)
    with pytest.raises(RuntimeError) as excinfo:
        spawn(
            env.proctab,
            env.captab,
            env.devtab,
            env.box_alloc,
            caps=CAP_SPAWN,
        )
    assert "no asid allocator bound" in str(excinfo.value)
    assert env.proctab.procs == {}
    assert env.proctab.pids.live() == []
    assert env.asid_alloc.live() == []
    assert env.box_alloc.live() == []
    assert env.devtab.bindings == []
    assert env.captab.grants == {}

    set_asid_allocator(env.asid_alloc)
    set_granter_mask(None)
    with pytest.raises(RuntimeError) as excinfo2:
        spawn(
            env.proctab,
            env.captab,
            env.devtab,
            env.box_alloc,
            caps=CAP_SPAWN,
        )
    assert "no granter mask bound" in str(excinfo2.value)
    assert env.proctab.procs == {}
    assert env.proctab.pids.live() == []
    assert env.asid_alloc.live() == []
    assert env.box_alloc.live() == []
    assert env.devtab.bindings == []
    assert env.captab.grants == {}


def test_l4_who_may_spawn_no_amplification(env: SpawnEnv) -> None:
    """L4 who may spawn / no amplification."""
    all_except_spawn = (
        CAP_FS_WRITE
        | CAP_FS_ADMIN
        | CAP_KILL
        | CAP_NET
        | CAP_DEV_MMIO
        | CAP_OBSERVE
        | CAP_BOOT_VERIFY
        | CAP_ROOT
    )
    set_granter_mask(all_except_spawn)
    with pytest.raises(PermissionError) as excinfo:
        spawn(
            env.proctab,
            env.captab,
            env.devtab,
            env.box_alloc,
            caps=CAP_OBSERVE,
        )
    assert "CAP_SPAWN" in str(excinfo.value)
    assert env.proctab.procs == {}
    assert env.proctab.pids.live() == []
    assert env.asid_alloc.live() == []
    assert env.box_alloc.live() == []
    assert env.devtab.bindings == []
    assert env.captab.grants == {}

    set_granter_mask(CAP_SPAWN | CAP_OBSERVE)
    with pytest.raises(PermissionError) as excinfo2:
        spawn(
            env.proctab,
            env.captab,
            env.devtab,
            env.box_alloc,
            caps=CAP_DEV_MMIO,
        )
    assert "dev_mmio" in str(excinfo2.value)
    assert env.proctab.procs == {}
    assert env.proctab.pids.live() == []
    assert env.asid_alloc.live() == []
    assert env.box_alloc.live() == []
    assert env.devtab.bindings == []
    assert env.captab.grants == {}


def test_l5_lifecycle_end_to_end(env: SpawnEnv) -> None:
    """L5 full lifecycle, end to end: spawn -> RUNNING -> exit -> reap -> reuse pid & asid."""
    desc = spawn(
        env.proctab,
        env.captab,
        env.devtab,
        env.box_alloc,
        caps=CAP_SPAWN,
    )
    pid = desc.pid
    assert pid == 0
    assert desc.asid == 0

    env.proctab.transition(pid, STATE_RUNNING)
    env.proctab.mark_exited(pid, 42)
    assert env.proctab.reap(pid) == 42

    # Retired space cannot be released again: reap already dropped refcount to 0
    live_before = list(env.asid_alloc.live())
    assert desc.meta["aspace"].refcount == 0
    with pytest.raises(RuntimeError):
        desc.meta["aspace"].release()
    assert env.asid_alloc.live() == live_before

    # Second spawn gets pid == 0 and asid == 0 again (lowest-free reuse)
    desc2 = spawn(
        env.proctab,
        env.captab,
        env.devtab,
        env.box_alloc,
        caps=CAP_SPAWN,
    )
    assert desc2.pid == 0
    assert desc2.asid == 0

    # Also verify refcount-0 refusal after retiring desc2
    env.proctab.transition(desc2.pid, STATE_RUNNING)
    env.proctab.mark_exited(desc2.pid, 99)
    assert env.proctab.reap(desc2.pid) == 99

    assert desc2.meta["aspace"].refcount == 0
    with pytest.raises(RuntimeError):
        desc2.meta["aspace"].release()
    assert env.asid_alloc.live() == []


def test_l6_box_allocation(env: SpawnEnv) -> None:
    """L6 box allocation: lowest-free order, exhaustion refusal, double-free refusal, reuse."""
    d0 = spawn(env.proctab, env.captab, env.devtab, env.box_alloc, caps=CAP_SPAWN)
    d1 = spawn(env.proctab, env.captab, env.devtab, env.box_alloc, caps=CAP_SPAWN)
    d2 = spawn(env.proctab, env.captab, env.devtab, env.box_alloc, caps=CAP_SPAWN)
    assert (d0.box, d1.box, d2.box) == (0, 1, 2)
    assert env.box_alloc.live() == [0, 1, 2]

    procs_before = dict(env.proctab.procs)
    pids_before = list(env.proctab.pids.live())
    asids_before = list(env.asid_alloc.live())
    bindings_before = list(env.devtab.bindings)

    with pytest.raises(RuntimeError) as excinfo:
        spawn(env.proctab, env.captab, env.devtab, env.box_alloc, caps=CAP_SPAWN)
    assert "box space exhausted" in str(excinfo.value)
    assert env.proctab.procs == procs_before
    assert env.proctab.pids.live() == pids_before
    assert env.asid_alloc.live() == asids_before
    assert env.devtab.bindings == bindings_before
    assert env.box_alloc.live() == [0, 1, 2]

    with pytest.raises(KeyError):
        env.box_alloc.free(3)

    env.box_alloc.free(1)
    assert env.box_alloc.live() == [0, 2]
    d3 = spawn(env.proctab, env.captab, env.devtab, env.box_alloc, caps=CAP_SPAWN)
    assert d3.box == 1
    assert env.box_alloc.live() == [0, 1, 2]


def test_l7_device_legs(env: SpawnEnv) -> None:
    """L7 device legs: driver/device validation, pre-flight conflicts, no leak."""
    with pytest.raises(ValueError):
        spawn(
            env.proctab,
            env.captab,
            env.devtab,
            env.box_alloc,
            caps=CAP_SPAWN | CAP_DEV_MMIO,
            driver=env.driver,
            device=None,
        )
    assert env.proctab.procs == {}
    assert env.asid_alloc.live() == []
    assert env.box_alloc.live() == []
    assert env.devtab.bindings == []

    with pytest.raises(ValueError):
        spawn(
            env.proctab,
            env.captab,
            env.devtab,
            env.box_alloc,
            caps=CAP_SPAWN | CAP_DEV_MMIO,
            driver=None,
            device=env.device,
        )
    assert env.proctab.procs == {}
    assert env.asid_alloc.live() == []
    assert env.box_alloc.live() == []
    assert env.devtab.bindings == []

    unregistered = DeviceDescriptor(
        dev_id=device_id(0x1002, 0x0004),
        name="nic0",
        window_lo=0x50,
        window_hi=0x60,
    )
    unreg_driver = Driver("nic-e1000", vendor=0x1002, dev_class=0x0004)
    with pytest.raises(ValueError) as excinfo:
        spawn(
            env.proctab,
            env.captab,
            env.devtab,
            env.box_alloc,
            caps=CAP_SPAWN | CAP_DEV_MMIO,
            driver=unreg_driver,
            device=unregistered,
        )
    assert "nic0" in str(excinfo.value)
    assert env.proctab.procs == {}
    assert env.asid_alloc.live() == []
    assert env.box_alloc.live() == []
    assert env.devtab.bindings == []

    d1 = spawn(
        env.proctab,
        env.captab,
        env.devtab,
        env.box_alloc,
        caps=CAP_SPAWN | CAP_DEV_MMIO,
        driver=env.driver,
        device=env.device,
    )
    assert d1.meta["binding"].device == env.device.name
    assert env.devtab.bindings[0].device == env.device.name
    pids_before = list(env.proctab.pids.live())
    asids_before = list(env.asid_alloc.live())
    boxes_before = list(env.box_alloc.live())

    with pytest.raises(DeviceConflict):
        spawn(
            env.proctab,
            env.captab,
            env.devtab,
            env.box_alloc,
            caps=CAP_SPAWN | CAP_DEV_MMIO,
            driver=env.driver,
            device=env.device,
        )
    assert env.proctab.pids.live() == pids_before
    assert env.asid_alloc.live() == asids_before
    assert env.box_alloc.live() == boxes_before

    d2 = spawn(
        env.proctab,
        env.captab,
        env.devtab,
        env.box_alloc,
        caps=CAP_SPAWN | CAP_DEV_MMIO,
    )
    assert "binding" not in d2.meta


def test_l8_integration_hygiene(env: SpawnEnv) -> None:
    """L8 integration hygiene: descriptor type/state, public surface, no back-imports."""
    desc = spawn(
        env.proctab,
        env.captab,
        env.devtab,
        env.box_alloc,
        caps=CAP_SPAWN,
    )
    assert type(desc) is geos_proctab.ProcessDescriptor
    assert desc.state == geos_proctab.STATE_READY

    assert geos_spawn.__all__ == ["BoxAllocator", "spawn"]

    for mod in (geos_aspace, geos_caps, geos_proctab, geos_devtab):
        assert "geos_spawn" not in mod.__all__
        tree = ast.parse(Path(mod.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert "geos_spawn" not in a.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert "geos_spawn" not in node.module
