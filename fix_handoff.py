handoff = """//! CPU handoff — set state and jump to kernel entry point

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
pub unsafe extern "sysv64" fn x86_64_handoff(_entry_point: u64, _stack_ptr: u64) -> ! {
    core::arch::naked_asm!(
        "mov rsp, rsi",
        "jmp rdi",
    );
}

#[cfg(target_arch = "riscv64")]
#[unsafe(naked)]
pub unsafe extern "C" fn riscv64_handoff(_entry_point: u64, _stack_ptr: u64) -> ! {
    core::arch::naked_asm!(
        "mv sp, a1",
        
        // Clear SPP in sstatus to drop to U-mode
        "csrr t0, sstatus",
        "li t1, 0x100", // SPP is bit 8
        "not t1, t1",
        "and t0, t0, t1",
        "csrw sstatus, t0",
        
        // Set sepc to entry point
        "csrw sepc, a0",
        
        // Return to U-mode
        "sret"
    );
}
"""
with open("systems/virtio_pixel_rs_v3_shared/src/handoff.rs", "w") as f:
    f.write(handoff)
