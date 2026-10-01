import sys
sys.path.insert(0, 'tools')

from boot_manifest import launch_boot, parse_boot_op

# Patch build_qemu_argv to use virtio-vga
import tools.boot_manifest as bm

original_build = bm.build_qemu_argv

def patched_build_qemu_argv(manifest, image_path, drive_path=None, initrd_path=None):
    binary, template = bm.ARCH_QEMU[manifest.arch]

    if manifest.gui:
        mem_val = manifest.mem if manifest.mem else "2048"
        base_cmd = [
            binary,
            "-M", "pc", "-m", mem_val,
            "-enable-kvm",
            "-display", "vnc=:1,share=force-shared",
            "-device", "virtio-vga",
            "-usb", "-device", "usb-tablet",
        ]

        if manifest.cdrom:
            return base_cmd + ["-cdrom", str(image_path)]
        else:
            return base_cmd + [
                "-drive", f"file={image_path},format=qcow2,if=virtio,snapshot=on"
            ]

    return original_build(manifest, image_path, drive_path, initrd_path)

bm.build_qemu_argv = patched_build_qemu_argv

argv = launch_boot(["boot", "x86_64", "arch_desktop.qcow2", {"gui": True, "mem": "2048M"}],
                    image_dir="boot_images", dry_run=False)
print(f"Launched: {' '.join(argv)}")