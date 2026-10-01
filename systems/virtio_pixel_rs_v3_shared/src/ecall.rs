#![no_std]
#[cfg(target_arch = "x86_64")]
#[repr(C, packed)]
#[derive(Clone, Copy)]
pub struct IdtEntry {
    offset_low: u16,
    selector: u16,
    ist: u8,
    type_attr: u8,
    offset_mid: u16,
    offset_high: u32,
    reserved: u32,
}

#[cfg(target_arch = "x86_64")]
impl IdtEntry {
    pub const fn new() -> Self {
        IdtEntry {
            offset_low: 0,
            selector: 0,
            ist: 0,
            type_attr: 0,
            offset_mid: 0,
            offset_high: 0,
            reserved: 0,
        }
    }
    pub fn set_handler(&mut self, handler: u64, cs: u16) {
        self.offset_low = handler as u16;
        self.selector = cs;
        self.ist = 0;
        self.type_attr = 0x8E;
        self.offset_mid = (handler >> 16) as u16;
        self.offset_high = (handler >> 32) as u32;
        self.reserved = 0;
    }
}

#[cfg(target_arch = "x86_64")]
#[repr(C, packed)]
struct IdtPtr {
    limit: u16,
    base: u64,
}

#[cfg(target_arch = "x86_64")]
static mut IDT: [IdtEntry; 256] = [IdtEntry::new(); 256];
#[cfg(target_arch = "x86_64")]
static mut IDTR: IdtPtr = IdtPtr { limit: 0, base: 0 };

#[cfg(target_arch = "x86_64")]
#[unsafe(naked)]
pub unsafe extern "C" fn isr_vector_0x06() {
    core::arch::naked_asm!(
        "mov ax, 0x2000",
        "mov dx, 0x604",
        "out dx, ax",
        "2: cli; hlt; jmp 2b"
    );
}

#[cfg(target_arch = "x86_64")]
#[unsafe(naked)]
pub unsafe extern "C" fn isr_vector_0x0E() {
    core::arch::naked_asm!(
        "mov ax, 0x3F8",
        "mov dx, ax",
        "mov al, 0x50", // 'P'
        "out dx, al",
        "mov al, 0x46", // 'F'
        "out dx, al",
        "1: cli; hlt; jmp 1b"
    );
}

#[cfg(target_arch = "x86_64")]
#[unsafe(naked)]
pub unsafe extern "C" fn isr_vector_0x0D() {
    core::arch::naked_asm!(
        "mov ax, 0x3F8",
        "mov dx, ax",
        "mov al, 0x47", // 'G'
        "out dx, al",
        "mov al, 0x50", // 'P'
        "out dx, al",
        "1: cli; hlt; jmp 1b"
    );
}

#[cfg(target_arch = "x86_64")]
#[unsafe(naked)]
pub unsafe extern "C" fn isr_vector_0x08() {
    core::arch::naked_asm!(
        "mov ax, 0x3F8",
        "mov dx, ax",
        "mov al, 0x44", // 'D'
        "out dx, al",
        "mov al, 0x46", // 'F'
        "out dx, al",
        "1: cli; hlt; jmp 1b"
    );
}

#[cfg(target_arch = "x86_64")]
#[unsafe(naked)]
pub unsafe extern "C" fn isr_vector_0x80() {
    core::arch::naked_asm!(
        "mov ax, 0x3F8",
        "mov dx, ax",
        "mov ax, di",
        "out dx, al",
        "iretq"
    );
}

pub fn setup_trap_table() {
    #[cfg(target_arch = "x86_64")]
    {
        let cs: u16;
        unsafe { core::arch::asm!("mov {:x}, cs", out(reg) cs) };
        unsafe {
            #[allow(static_mut_refs)]
            IDT[0x80].set_handler(isr_vector_0x80 as usize as u64, cs);
            #[allow(static_mut_refs)]
            IDT[0x06].set_handler(isr_vector_0x06 as usize as u64, cs);
            #[allow(static_mut_refs)]
            IDT[0x0E].set_handler(isr_vector_0x0E as usize as u64, cs);
            #[allow(static_mut_refs)]
            IDT[0x0D].set_handler(isr_vector_0x0D as usize as u64, cs);
            #[allow(static_mut_refs)]
            IDT[0x08].set_handler(isr_vector_0x08 as usize as u64, cs);
            
            IDTR.limit = (core::mem::size_of_val(&IDT) - 1) as u16;
            IDTR.base = IDT.as_ptr() as u64;

            core::arch::asm!(
                "cli",
                "lidt [{}]",
                in(reg) &IDTR,
            );
        }
    }
}
