//! ELF64 loader for booting RISC-V and x86_64 kernels

#[repr(C)]
pub struct Elf64Header {
    pub e_ident: [u8; 16],
    pub e_type: u16,
    pub e_machine: u16,
    pub e_version: u32,
    pub e_entry: u64,
    pub e_phoff: u64,
    pub e_shoff: u64,
    pub e_flags: u32,
    pub e_ehsize: u16,
    pub e_phentsize: u16,
    pub e_phnum: u16,
    pub e_shentsize: u16,
    pub e_shnum: u16,
    pub e_shstrndx: u16,
}

#[repr(C)]
pub struct Elf64ProgramHeader {
    pub p_type: u32,
    pub p_flags: u32,
    pub p_offset: u64,
    pub p_vaddr: u64,
    pub p_paddr: u64,
    pub p_filesz: u64,
    pub p_memsz: u64,
    pub p_align: u64,
}

pub const PT_LOAD: u32 = 1;

pub const EM_X86_64: u16 = 62;
pub const EM_RISCV: u16 = 243;

#[cfg(target_arch = "x86_64")]
pub const HOST_MACHINE: u16 = EM_X86_64;

#[cfg(target_arch = "riscv64")]
pub const HOST_MACHINE: u16 = EM_RISCV;

/// Refuse to hand off to a kernel built for a different ISA than this bootloader runs on.
pub fn check_machine(header: &Elf64Header) -> Result<(), &'static str> {
    if header.e_machine != HOST_MACHINE {
        return Err("ELF e_machine does not match host architecture — refusing cross-ISA handoff");
    }
    Ok(())
}

pub struct Elf64Loader<'a> {
    data: &'a [u8],
}

impl<'a> Elf64Loader<'a> {
    pub fn new(data: &'a [u8]) -> Self {
        Self { data }
    }

    /// Parse ELF header from raw bytes
    pub fn parse_header(&self) -> Result<Elf64Header, &'static str> {
        if self.data.len() < 64 {
            return Err("ELF too short");
        }

        // Verify ELF magic
        if &self.data[0..4] != b"\x7fELF" {
            return Err("Invalid ELF magic");
        }

        Ok(Elf64Header {
            e_ident: self.data[0..16].try_into().unwrap(),
            e_type: u16::from_le_bytes(self.data[16..18].try_into().unwrap()),
            e_machine: u16::from_le_bytes(self.data[18..20].try_into().unwrap()),
            e_version: u32::from_le_bytes(self.data[20..24].try_into().unwrap()),
            e_entry: u64::from_le_bytes(self.data[24..32].try_into().unwrap()),
            e_phoff: u64::from_le_bytes(self.data[32..40].try_into().unwrap()),
            e_shoff: u64::from_le_bytes(self.data[40..48].try_into().unwrap()),
            e_flags: u32::from_le_bytes(self.data[48..52].try_into().unwrap()),
            e_ehsize: u16::from_le_bytes(self.data[52..54].try_into().unwrap()),
            e_phentsize: u16::from_le_bytes(self.data[54..56].try_into().unwrap()),
            e_phnum: u16::from_le_bytes(self.data[56..58].try_into().unwrap()),
            e_shentsize: u16::from_le_bytes(self.data[58..60].try_into().unwrap()),
            e_shnum: u16::from_le_bytes(self.data[60..62].try_into().unwrap()),
            e_shstrndx: u16::from_le_bytes(self.data[62..64].try_into().unwrap()),
        })
    }

    /// Get entry point address
    pub fn entry_point(&self, header: &Elf64Header) -> u64 {
        header.e_entry
    }

    /// Get all loadable segments
    pub fn get_loadable_segments(&self, header: &Elf64Header) -> Result<alloc::vec::Vec<Elf64ProgramHeader>, &'static str> {
        let mut segments = alloc::vec::Vec::new();
        let phoff = header.e_phoff as usize;
        let phentsize = header.e_phentsize as usize;
        let phnum = header.e_phnum as usize;

        if self.data.len() < phoff + phentsize * phnum {
            return Err("ELF program headers truncated");
        }

        for i in 0..phnum {
            let offset = phoff + i * phentsize;
            let segment_data = &self.data[offset..offset + phentsize];

            let p_type = u32::from_le_bytes(segment_data[0..4].try_into().unwrap());

            if p_type == PT_LOAD {
                segments.push(Elf64ProgramHeader {
                    p_type,
                    p_flags: u32::from_le_bytes(segment_data[4..8].try_into().unwrap()),
                    p_offset: u64::from_le_bytes(segment_data[8..16].try_into().unwrap()),
                    p_vaddr: u64::from_le_bytes(segment_data[16..24].try_into().unwrap()),
                    p_paddr: u64::from_le_bytes(segment_data[24..32].try_into().unwrap()),
                    p_filesz: u64::from_le_bytes(segment_data[32..40].try_into().unwrap()),
                    p_memsz: u64::from_le_bytes(segment_data[40..48].try_into().unwrap()),
                    p_align: u64::from_le_bytes(segment_data[48..56].try_into().unwrap()),
                });
            }
        }

        Ok(segments)
    }
}
