import re

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "r") as f:
    data = f.read()

# Replace boot_params.hdr.cmd_line_ptr = cmdline_ptr;
data = re.sub(r'boot_params\.hdr\.cmd_line_ptr\s*=\s*cmdline_ptr;', 'boot_params.hdr_mut().cmd_line_ptr = cmdline_ptr;', data)

# Replace boot_params.ext_ramdisk_image = ...
# Replace boot_params.ext_ramdisk_size = ...
# Replace boot_params.hdr.ramdisk_image = ...
# Replace boot_params.hdr.ramdisk_size = ...

data = re.sub(r'boot_params\.ext_ramdisk_image\s*=\s*initramfs_addr\s*as\s*u32;', 'boot_params.set_ext_ramdisk(initramfs_addr as u64, initramfs_size as u64);\n    boot_params.hdr_mut().ramdisk_image = initramfs_addr as u32;\n    boot_params.hdr_mut().ramdisk_size = initramfs_size as u32;', data)
data = re.sub(r'boot_params\.ext_ramdisk_size\s*=\s*initramfs_size;', '', data)
data = re.sub(r'boot_params\.hdr\.ramdisk_image\s*=\s*initramfs_addr\s*as\s*u32;', '', data)
data = re.sub(r'boot_params\.hdr\.ramdisk_size\s*=\s*initramfs_size;', '', data)

# Fix type_of_loader
data = re.sub(r'boot_params\.hdr\.type_of_loader\s*=\s*0xFF;', 'boot_params.hdr_mut().type_of_loader = 0xFF;', data)

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(data)
