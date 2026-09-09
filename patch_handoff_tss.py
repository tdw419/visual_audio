import os
with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "r") as f:
    code = f.read()

tss_code = """
#[cfg(target_arch = "x86_64")]
#[repr(C, packed)]
struct Tss {
    reserved1: u32,
    rsp0: u64,
    rsp1: u64,
    rsp2: u64,
    reserved2: u64,
    ist1: u64,
    ist2: u64,
    ist3: u64,
    ist4: u64,
    ist5: u64,
    ist6: u64,
    ist7: u64,
    reserved3: u64,
    reserved4: u16,
    iomap_base: u16,
}

#[cfg(target_arch = "x86_64")]
static mut TSS: Tss = Tss {
    reserved1: 0, rsp0: 0x400000, rsp1: 0, rsp2: 0, reserved2: 0,
    ist1: 0, ist2: 0, ist3: 0, ist4: 0, ist5: 0, ist6: 0, ist7: 0,
    reserved3: 0, reserved4: 0, iomap_base: 0xFFFF,
};

#[cfg(target_arch = "x86_64")]
static mut GDT: [u64; 7] = [
    0,
    0x00af9a000000ffff, // 0x08: Ring 0 64-bit code
    0x00cf92000000ffff, // 0x10: Ring 0 data
    0x00affa000000ffff, // 0x18: Ring 3 64-bit code
    0x00cff2000000ffff, // 0x20: Ring 3 data
    0, // 0x28: TSS low (filled at runtime)
    0, // 0x30: TSS high
];
"""

new_handoff = """
#[cfg(target_arch = "x86_64")]
pub unsafe fn x86_64_handoff(entry_point: u64, stack_ptr: u64) -> ! {
    let tss_addr = &TSS as *const _ as u64;
    // TSS descriptor is 16 bytes in long mode
    let limit = (core::mem::size_of::<Tss>() - 1) as u64;
    let base_low = tss_addr & 0xFFFFFF;
    let base_high = (tss_addr >> 24) & 0xFF;
    let base_upper = tss_addr >> 32;
    
    // Type 9 (available 64-bit TSS), Present, DPL0
    GDT[5] = (limit & 0xFFFF) | ((base_low & 0xFFFFFF) << 16) | (0x89 << 40) | (((limit >> 16) & 0xF) << 48) | (base_high << 56);
    GDT[6] = base_upper;

    let ptr = GdtPointer {
        limit: (core::mem::size_of_val(&GDT) - 1) as u16,
        base: GDT.as_ptr() as u64,
    };
    core::arch::asm!("lgdt [{}]", in(reg) &ptr);
    
    // Load TSS
    core::arch::asm!("ltr ax", in("ax") 0x28);

    core::arch::asm!(
        "mov ax, 0x23",
        "mov ds, ax",
        "mov es, ax",
        "mov fs, ax",
        "mov gs, ax",
        "push 0x23",        // SS
        "push {0}",         // RSP
        "push 0x202",       // RFLAGS
        "push 0x1b",        // CS
        "push {1}",         // RIP
        "iretq",
        in(reg) stack_ptr,
        in(reg) entry_point,
        options(noreturn)
    );
}
"""

import re
code = re.sub(r'#\[cfg\(target_arch = "x86_64"\)\]\nstatic mut GDT:.*?\];', tss_code, code, flags=re.DOTALL)
code = re.sub(r'#\[cfg\(target_arch = "x86_64"\)\]\npub unsafe fn x86_64_handoff.*?options\(noreturn\)\n    \);\n}', new_handoff, code, flags=re.DOTALL)

with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "w") as f:
    f.write(code)
