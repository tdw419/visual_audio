import re

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "r") as f:
    data = f.read()

# Find the handover_offset calculation
old_code = "let handover_offset = { header.handover_offset } as u64 + 0x200;"
new_code = """
    // handover_offset is relative to the start of the payload (startup_32)
    // The payload starts after the setup code.
    let setup_sects = header.setup_sects;
    let setup_sects = if setup_sects == 0 { 4 } else { setup_sects };
    let setup_size = (setup_sects as u64 + 1) * 512;
    
    // For 64-bit EFI handover, it's at handover_offset + 512
    let handover_offset = { header.handover_offset } as u64 + 512;
    
    let handover_addr = kernel_base.as_ptr() as u64 + setup_size + handover_offset;
"""

# Wait, there's another line defining handover_addr right after
data = data.replace(old_code, new_code)
# Remove the old handover_addr definition if it exists right after
data = re.sub(r'let handover_addr = kernel_base\.as_ptr\(\) as u64 \+ handover_offset;\n', '', data)

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(data)
