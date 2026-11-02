import re

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "r") as f:
    data = f.read()

# Find where boot_params is created
old_code = """    let mut boot_params = match BootParams::from_bzimage(kernel_data) {
        Ok(params) => params,
        Err(e) => {
            info!("Failed to create boot_params from bzImage: {}", e);
            boot::stall(core::time::Duration::from_secs(5));
            return Status::LOAD_ERROR;
        }
    };"""

new_code = """    let mut boot_params_stack = match BootParams::from_bzimage(kernel_data) {
        Ok(params) => params,
        Err(e) => {
            info!("Failed to create boot_params from bzImage: {}", e);
            boot::stall(core::time::Duration::from_secs(5));
            return Status::LOAD_ERROR;
        }
    };
    
    // Allocate boot_params dynamically so it survives ExitBootServices
    let boot_params_addr = unsafe {
        uefi::boot::allocate_pages(
            uefi::boot::AllocateType::AnyPages,
            uefi::boot::MemoryType::LOADER_DATA,
            1, // 4KB = 1 page
        ).expect("Failed to allocate boot_params")
    };
    
    let boot_params = unsafe { &mut *(boot_params_addr.as_ptr() as *mut BootParams) };
    unsafe {
        core::ptr::copy_nonoverlapping(&boot_params_stack, boot_params, 1);
    }
"""

data = data.replace(old_code, new_code)

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(data)
