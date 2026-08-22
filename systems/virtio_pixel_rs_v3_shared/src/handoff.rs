//! CPU handoff — set state and jump to kernel entry point

/// CPU state before handoff (platform-specific)
#[repr(C)]
pub struct CpuState {
    // x86_64
    pub rip: u64,
    pub rsp: u64,
    pub rflags: u64,
    pub cs: u64,
    pub ds: u64,
    pub es: u64,
    pub fs: u64,
    pub gs: u64,

    // RISC-V (shared layout for now)
    pub pc: u64,
    pub sp: u64,
}

impl Default for CpuState {
    fn default() -> Self {
        Self {
            rip: 0, rsp: 0, rflags: 0, cs: 0, ds: 0, es: 0, fs: 0, gs: 0, pc: 0, sp: 0,
        }
    }
}

pub unsafe fn handoff_to_kernel(entry_point: u64, state: &CpuState) -> ! {
    #[cfg(target_arch = "x86_64")]
    {
        x86_64_handoff(entry_point, state.rsp)
    }
    #[cfg(target_arch = "riscv64")]
    {
        riscv64_handoff(entry_point, state.sp)
    }
    #[cfg(not(any(target_arch = "x86_64", target_arch = "riscv64")))]
    {
        loop {}
    }
}



#[cfg(target_arch = "x86_64")]
#[unsafe(naked)]
pub unsafe extern "efiapi" fn x86_64_handoff(_entry_point: u64, _stack_ptr: u64) -> ! {
    core::arch::naked_asm!(
        "test rdx, rdx",
        "jz 1f",
        "mov rsp, rdx",
        "1:",
        "jmp rcx",
    );
}




#[cfg(target_arch = "riscv64")]
pub unsafe fn riscv64_handoff(entry_point: u64, stack_ptr: u64) -> ! {
    let mut sstatus: u64;
    core::arch::asm!("csrr {}, sstatus", out(reg) sstatus);
    
    // Clear SPP (bit 8)
    sstatus &= !(1 << 8);
    
    core::arch::asm!(
        "csrw sstatus, {0}",
        "csrw sepc, {1}",
        "mv sp, {2}",
        "sret",
        in(reg) sstatus,
        in(reg) entry_point,
        in(reg) stack_ptr,
    );
    loop {}
}
