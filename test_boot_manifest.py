#!/usr/bin/env python3
"""
test_boot_manifest.py — Tests for signed boot manifests (approach B).

Covers the safety envelope around ["boot", arch, image] ops:
  - a signed boot op decoded through the listener launches the right qemu argv;
  - an unsigned/unprovenanced daemon refuses boot ops outright;
  - path-traversal and unknown-arch manifests are rejected;
  - draw ops still reach the framebuffer when mixed with boot ops.

Nothing here actually spawns QEMU — launches are captured via a fake runner or
dry-run so the test is fast and side-effect free.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools'))

import soundfile as sf

from boot_manifest import launch_boot, parse_boot_op, BootManifestError
from spoken_screen import utter, decode_data_band
import pixel_os_listener
from pixel_os_listener import ListenerDaemon

KEYS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys')
PRIV = os.path.join(KEYS, 'pixel_os_private.pem')
PUB = os.path.join(KEYS, 'pixel_os_public.pem')


def _make_image(dirpath, name='xv6.img', data=b'\x7fELF fake kernel'):
    p = Path(dirpath) / name
    p.write_bytes(data)
    return p


def test_manifest_validation():
    print("Test: manifest validation (arch + traversal)")
    with tempfile.TemporaryDirectory() as d:
        _make_image(d)
        # Good manifest, dry run -> correct argv
        argv = launch_boot(["boot", "riscv64", "xv6.img"], d, dry_run=True)
        assert argv[0] == "qemu-system-riscv64", argv
        assert argv[-2] == "-kernel" and argv[-1].endswith("xv6.img"), argv

        # Unknown arch
        try:
            parse_boot_op(["boot", "sparc", "xv6.img"])
            print("  FAIL: unknown arch accepted"); return False
        except BootManifestError:
            pass

        # Path traversal in image name
        for bad in ["../secret", "/etc/passwd", "sub/dir.img", ".."]:
            try:
                launch_boot(["boot", "riscv64", bad], d, dry_run=True)
                print(f"  FAIL: traversal accepted: {bad!r}"); return False
            except BootManifestError:
                pass

        # Missing image file
        try:
            launch_boot(["boot", "riscv64", "nope.img"], d, dry_run=True)
            print("  FAIL: missing image accepted"); return False
        except BootManifestError:
            pass

        # Malformed op shapes
        for bad in [["boot"], ["boot", "riscv64"], ["fill", "#f00"], "boot"]:
            try:
                parse_boot_op(bad)
                print(f"  FAIL: malformed accepted: {bad!r}"); return False
            except BootManifestError:
                pass
    print("  PASS")
    return True


def test_bios_option():
    print("Test: bios option (default / none / rejected)")
    with tempfile.TemporaryDirectory() as d:
        _make_image(d)
        # default: no -bios in argv
        argv = launch_boot(["boot", "riscv64", "xv6.img"], d, dry_run=True)
        assert "-bios" not in argv, argv
        # explicit default: still no -bios
        argv = launch_boot(["boot", "riscv64", "xv6.img", {"bios": "default"}], d, dry_run=True)
        assert "-bios" not in argv, argv
        # none: -bios none present, before -kernel
        argv = launch_boot(["boot", "riscv64", "xv6.img", {"bios": "none"}], d, dry_run=True)
        assert argv[argv.index("-bios") + 1] == "none", argv
        assert argv.index("-bios") < argv.index("-kernel"), argv
        # rejected: arbitrary bios value (no smuggling a path)
        for bad in [{"bios": "/boot/fw.bin"}, {"bios": "hax"}, {"unknown": 1}]:
            try:
                launch_boot(["boot", "riscv64", "xv6.img", bad], d, dry_run=True)
                print(f"  FAIL: bad opts accepted: {bad!r}"); return False
            except BootManifestError:
                pass
    print("  PASS")
    return True


def test_drive_option():
    print("Test: drive option (virtio disk wiring + safety)")
    with tempfile.TemporaryDirectory() as d:
        _make_image(d)                       # xv6.img stand-in
        _make_image(d, name='fs.img')        # disk stand-in
        argv = launch_boot(
            ["boot", "riscv64", "xv6.img", {"bios": "none", "drive": "fs.img"}],
            d, dry_run=True)
        assert "-drive" in argv, argv
        assert any(a.startswith("file=") and a.endswith("fs.img,if=none,format=raw,id=x0")
                   for a in argv), argv
        assert "virtio-blk-device,drive=x0,bus=virtio-mmio-bus.0" in argv, argv
        # disk wiring must precede the kernel flag
        assert argv.index("-drive") < argv.index("-kernel"), argv

        # drive must be a bare filename in the trusted dir
        try:
            launch_boot(["boot", "riscv64", "xv6.img", {"drive": "../fs.img"}], d, dry_run=True)
            print("  FAIL: drive traversal accepted"); return False
        except BootManifestError:
            pass
        # drive is riscv-only (x86 has no virtio-mmio-bus here)
        try:
            launch_boot(["boot", "x86_64", "xv6.img", {"drive": "fs.img"}], d, dry_run=True)
            print("  FAIL: drive accepted for x86_64"); return False
        except BootManifestError:
            pass
    print("  PASS")
    return True


def test_daemon_refuses_unsigned_boot():
    print("Test: daemon refuses boot without provenance/enable")
    with tempfile.TemporaryDirectory() as d:
        _make_image(d)
        # provenance NOT required -> boot must be refused even if enabled
        daemon = ListenerDaemon(provenance_required=False, enable_boot=True,
                                boot_image_dir=d, boot_dry_run=True)
        assert daemon._handle_boot_op(["boot", "riscv64", "xv6.img"]) is False

        # provenance required but boot NOT enabled -> refused
        daemon2 = ListenerDaemon(provenance_required=True, public_key_path=PUB,
                                 enable_boot=False, boot_image_dir=d, boot_dry_run=True)
        assert daemon2._handle_boot_op(["boot", "riscv64", "xv6.img"]) is False
    print("  PASS")
    return True


def test_signed_boot_end_to_end():
    print("Test: signed boot op end-to-end through decode + dispatch")
    with tempfile.TemporaryDirectory() as d:
        _make_image(d)
        wav = os.path.join(d, 'boot.wav')
        utter("boot xv6", [["boot", "riscv64", "xv6.img"]], wav, private_key_path=PRIV)

        # Frame decodes only with the key (provenance verified) ...
        audio, sr = sf.read(wav)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        import json
        ops = json.loads(decode_data_band(audio, sr, PUB).decode('utf-8'))
        assert ops == [["boot", "riscv64", "xv6.img"]], ops

        # ... and a boot-enabled daemon captures the launch (no real QEMU).
        launched = []
        daemon = ListenerDaemon(provenance_required=True, public_key_path=PUB,
                                enable_boot=True, boot_image_dir=d, boot_dry_run=False)
        # Patch the module-level runner via boot_manifest.launch_boot's default:
        import boot_manifest
        orig = boot_manifest.subprocess.Popen
        boot_manifest.subprocess.Popen = lambda argv, *a, **k: launched.append(argv)
        try:
            assert daemon._dispatch_ops(ops) is True
        finally:
            boot_manifest.subprocess.Popen = orig
        assert len(launched) == 1, launched
        assert launched[0][0] == "qemu-system-riscv64", launched
        assert launched[0][-1].endswith("xv6.img"), launched
    print("  PASS")
    return True


def test_mixed_ops_route_correctly():
    print("Test: boot + draw ops route to the right handlers")
    with tempfile.TemporaryDirectory() as d:
        _make_image(d)
        daemon = ListenerDaemon(provenance_required=True, public_key_path=PUB,
                                enable_boot=True, boot_image_dir=d, boot_dry_run=True)
        boots, draws = [], []
        daemon._handle_boot_op = lambda op: (boots.append(op) or True)
        daemon._apply_ops_to_framebuffer = lambda ops: (draws.append(ops) or True)
        ops = [["boot", "riscv64", "xv6.img"], ["fill", "#ff0000"], ["text", 1, 1, "HI"]]
        assert daemon._dispatch_ops(ops) is True
        assert boots == [["boot", "riscv64", "xv6.img"]], boots
        assert draws == [[["fill", "#ff0000"], ["text", 1, 1, "HI"]]], draws
    print("  PASS")
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("SIGNED BOOT MANIFEST TESTS")
    print("=" * 60)
    results = [
        ("manifest validation", test_manifest_validation()),
        ("bios option", test_bios_option()),
        ("drive option", test_drive_option()),
        ("refuse unsigned boot", test_daemon_refuses_unsigned_boot()),
        ("signed boot end-to-end", test_signed_boot_end_to_end()),
        ("mixed op routing", test_mixed_ops_route_correctly()),
    ]
    print("=" * 60)
    ok = all(r for _, r in results)
    for name, r in results:
        print(f"  {'✓' if r else '✗'} {name}")
    print("=" * 60)
    print("ALL BOOT TESTS PASSED ✓" if ok else "SOME BOOT TESTS FAILED ✗")
    sys.exit(0 if ok else 1)
