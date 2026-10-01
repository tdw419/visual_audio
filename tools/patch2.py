import re

with open("systems/v4_bootloader_x86/src/linux_boot.rs", "r") as f:
    data = f.read()

if "pub fn set_cmdline" not in data:
    data = data.replace("pub fn set_ext_ramdisk", """pub fn set_cmdline(&mut self, addr: u64) {
        self.hdr_mut().cmd_line_ptr = addr as u32;
        unsafe { *(self.raw.as_mut_ptr().add(0x0c8) as *mut u32) = (addr >> 32) as u32; }
    }
    
    pub fn set_ext_ramdisk""")
    
with open("systems/v4_bootloader_x86/src/linux_boot.rs", "w") as f:
    f.write(data)

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "r") as f:
    data = f.read()

# Replace the command line pointer assignment
data = re.sub(
    r'if cmdline_ptr != 0 \{\s*boot_params\.hdr_mut\(\)\.cmd_line_ptr = cmdline_ptr;\s*\}',
    r'if cmdline_ptr != 0 { boot_params.set_cmdline(cmdline_addr); }',
    data
)

# Enhance the CMDLINE
data = re.sub(
    r'const CMDLINE: &\[u8\] = b"[^"]*";',
    r'const CMDLINE: &[u8] = b"console=ttyS0,115200 earlyprintk=ttyS0,115200 earlycon=uart8250,io,0x3f8,115200n8 loglevel=7 debug\\0";',
    data
)

# Add logging for the CMDLINE string
if "CMDLINE set to:" not in data:
    data = re.sub(
        r'info!\("Jumping to Linux kernel..."\);',
        r'info!("CMDLINE ptr: 0x{:x}, string: {}", cmdline_addr, core::str::from_utf8(CMDLINE).unwrap_or("INVALID"));\n    info!("Jumping to Linux kernel...");',
        data
    )

with open("systems/v4_bootloader_x86/src/bootloader_uefi.rs", "w") as f:
    f.write(data)

