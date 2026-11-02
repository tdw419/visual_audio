with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "r") as f:
    data = f.read()

data = data.replace(
    'type EfiHandoverEntry = unsafe extern "C" fn(',
    'type EfiHandoverEntry = unsafe extern "sysv64" fn('
)
# Also change back image_handle from null_mut to image_handle
data = data.replace(
    "handover_entry(core::ptr::null_mut(), system_table, boot_params as *mut _);",
    "handover_entry(image_handle, system_table, boot_params as *mut _);"
)

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(data)
