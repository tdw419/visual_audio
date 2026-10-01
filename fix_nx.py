import os
with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "r") as f:
    code = f.read()

disable_nx = """
        // Disable NX globally before handoff
        unsafe {
            let mut efer: u64;
            core::arch::asm!("rdmsr", out("eax") _, out("edx") _, in("ecx") 0xC0000080u32, options(nomem, nostack));
            // Actually let's do it safely
            core::arch::asm!(
                "rdmsr",
                "btr eax, 11", // Clear bit 11 (NXE)
                "wrmsr",
                in("ecx") 0xC0000080u32,
                out("eax") _,
                out("edx") _,
            );
        }
"""

code = code.replace(
    '        uefi::println!("Handing off to runtime entry {:#x}...", runtime_entry);',
    disable_nx + '\n        uefi::println!("Handing off to runtime entry {:#x}...", runtime_entry);'
)

with open("systems/virtio_pixel_rs_v3_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(code)
