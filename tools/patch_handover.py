import re

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "r") as f:
    data = f.read()

# Replace handover_entry call to not take double reference
data = data.replace(
    "handover_entry(image_handle, system_table, &mut boot_params);",
    "handover_entry(image_handle, system_table, boot_params as *mut _);"
)

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(data)
