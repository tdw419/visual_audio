//! Linux x86_64 boot protocol support (EFI handover)
//!
//! Based on Linux kernel's arch/x86/include/uapi/asm/bootparam.h
//! Boot protocol version 2.12+

use core::mem;

pub const HDR_MAGIC: u32 = 0x53726448; // "HdrS"
pub const BOOT_FLAG: u16 = 0xAA55;
pub const BOOT_PARAM_HDR_OFFSET: usize = 0x1f1; // SetupHeader offset in boot_params

/// Load flags
pub const LOADED_HIGH: u8 = 1 << 0;
pub const KASLR_FLAG: u8 = 1 << 1;
pub const QUIET_FLAG: u8 = 1 << 5;
pub const KEEP_SEGMENTS: u8 = 1 << 6;
pub const CAN_USE_HEAP: u8 = 1 << 7;

/// Extended load flags (xloadflags)
pub const XLF_KERNEL_64: u16 = 1 << 0;
pub const XLF_EFI_HANDOVER_64: u16 = 1 << 3;

#[repr(C, packed)]
#[derive(Copy, Clone, Debug)]
pub struct SetupHeader {
    pub setup_sects: u8,
    pub root_flags: u16,
    pub syssize: u32,
    pub ram_size: u16,
    pub vid_mode: u16,
    pub root_dev: u16,
    pub boot_flag: u16,
    pub jump: u16,
    pub header: u32,
    pub version: u16,
    pub realmode_swtch: u32,
    pub start_sys_seg: u16,
    pub kernel_version: u16,
    pub type_of_loader: u8,
    pub loadflags: u8,
    pub setup_move_size: u16,
    pub code32_start: u32,
    pub ramdisk_image: u32,
    pub ramdisk_size: u32,
    pub bootsect_kludge: u32,
    pub heap_end_ptr: u16,
    pub ext_loader_ver: u8,
    pub ext_loader_type: u8,
    pub cmd_line_ptr: u32,
    pub initrd_addr_max: u32,
    pub kernel_alignment: u32,
    pub relocatable_kernel: u8,
    pub min_alignment: u8,
    pub xloadflags: u16,
    pub cmdline_size: u32,
    pub hardware_subarch: u32,
    pub hardware_subarch_data: u64,
    pub payload_offset: u32,
    pub payload_length: u32,
    pub setup_data: u64,
    pub pref_address: u64,
    pub init_size: u32,
    pub handover_offset: u32,
    pub kernel_info_offset: u32,
}

/// Full Linux boot_params structure (size 4096 bytes)
#[repr(C, packed)]
pub struct BootParams {
    pub raw: [u8; 4096],
}

impl BootParams {
    /// Create BootParams from bzImage setup code and header
    pub fn from_bzimage(bzimage: &[u8]) -> Result<Self, &'static str> {
        if bzimage.len() < 0x1f1 + mem::size_of::<SetupHeader>() {
            return Err("bzImage too small for boot_params");
        }

        let mut boot_params: BootParams = unsafe { mem::zeroed() };

        // Copy up to the end of SetupHeader (which is at 0x1f1)
        let copy_len = 0x1f1 + mem::size_of::<SetupHeader>();
        boot_params.raw[..copy_len].copy_from_slice(&bzimage[..copy_len]);

        Ok(boot_params)
    }

    pub fn new() -> Self {
        unsafe { mem::zeroed() }
    }

    // Get mutable reference to hdr
    pub fn hdr_mut(&mut self) -> &mut SetupHeader {
        unsafe {
            &mut *(self.raw.as_mut_ptr().add(0x1f1) as *mut SetupHeader)
        }
    }

    // Set ext_ramdisk fields
    pub fn set_cmdline(&mut self, addr: u64) {
        self.hdr_mut().cmd_line_ptr = addr as u32;
        unsafe { *(self.raw.as_mut_ptr().add(0x0c8) as *mut u32) = (addr >> 32) as u32; }
    }
    
    pub fn set_ext_ramdisk(&mut self, addr: u64, size: u64) {
        // ext_ramdisk_image is at 0x0c0
        let ext_ramdisk_image = (addr >> 32) as u32;
        let ext_ramdisk_size = (size >> 32) as u32;
        unsafe {
            *(self.raw.as_mut_ptr().add(0x0c0) as *mut u32) = ext_ramdisk_image;
            *(self.raw.as_mut_ptr().add(0x0c4) as *mut u32) = ext_ramdisk_size;
        }
    }
}

pub struct BzImage<'a> {
    data: &'a [u8],
    header: SetupHeader,
}

impl<'a> BzImage<'a> {
    pub fn parse(data: &'a [u8]) -> Result<Self, &'static str> {
        if data.len() < 0x1f1 + mem::size_of::<SetupHeader>() {
            return Err("bzImage too small");
        }

        let boot_flag = u16::from_le_bytes([data[0x1FE], data[0x1FF]]);
        if boot_flag != BOOT_FLAG {
            return Err("Invalid boot flag (not a bzImage)");
        }

        let header: SetupHeader = unsafe { *(data.as_ptr().add(0x1F1) as *const SetupHeader) };

        if header.header != HDR_MAGIC {
            return Err("Invalid header magic");
        }

        if header.xloadflags & XLF_KERNEL_64 == 0 {
            return Err("Not a 64-bit kernel");
        }
        if header.xloadflags & XLF_EFI_HANDOVER_64 == 0 {
            return Err("Kernel does not support EFI handover");
        }

        Ok(Self { data, header })
    }

    pub fn header(&self) -> &SetupHeader {
        &self.header
    }

    pub fn payload(&self) -> &[u8] {
        let offset = self.header.payload_offset as usize;
        let len = self.header.payload_length as usize;
        if offset + len > self.data.len() {
            &self.data[offset..]
        } else {
            &self.data[offset..offset + len]
        }
    }

    pub fn pref_address(&self) -> u64 {
        if self.header.pref_address == 0 {
            0x100000
        } else {
            self.header.pref_address
        }
    }

    pub fn handover_offset(&self) -> u32 {
        self.header.handover_offset
    }

    pub fn kernel_alignment(&self) -> u32 {
        if self.header.kernel_alignment == 0 {
            0x200000
        } else {
            self.header.kernel_alignment
        }
    }
}
