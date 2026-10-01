//! RISC-V Bare-Metal Bootloader for Phase 3 Ecall Tracing
//!
//! This is a minimal RISC-V bootloader that:
//! 1. Embeds hello.img directly via include_bytes!()
//! 2. Parses and loads the ELF64 kernel
//! 3. Sets up the stvec trap table for ecall interception
//! 4. Hands off to the kernel and logs any syscalls it makes
//!
//! Boot sequence: OpenSBI (M-mode) → bootloader (S-mode) → kernel (S-mode)
//!
//! Usage:
//!   cargo build --release --target riscv64gc-unknown-none-elf
//!   qemu-system-riscv64 -machine virt -bios default \
//!     -kernel target/.../bootloader_riscv -nographic

#![no_std]
#![no_main]
extern crate alloc;



use alloc::alloc::GlobalAlloc;
use core::panic::PanicInfo;

use virtio_pixel_rs_v3_riscv::ecall::setup_trap_table;
use virtio_pixel_rs_v3_riscv::elf64::{check_machine, Elf64Loader};
use virtio_pixel_rs_v3_riscv::handoff::{self, CpuState};

/// Embedded hello.img kernel (RISC-V ELF)
/// Compiled from boot_images/Makefile's hello target
static HELLO_PNG: &[u8] = include_bytes!("../../../boot_images/hello.rts.png");

/// Minimal bump allocator for bare-metal
/// Place heap after bootloader code at 0x80100000
use core::sync::atomic::{AtomicUsize, Ordering};
struct BumpAllocator {
    start: usize,
    end: usize,
    next: AtomicUsize,
}

fn align_up(addr: usize, align: usize) -> usize {
    (addr + align - 1) & !(align - 1)
}

unsafe impl GlobalAlloc for BumpAllocator {
    unsafe fn alloc(&self, layout: core::alloc::Layout) -> *mut u8 {
        let mut current_next = self.next.load(Ordering::Relaxed);
        loop {
            let alloc_start = align_up(current_next, layout.align());
            let alloc_end = alloc_start + layout.size();

            if alloc_end > self.end {
                return core::ptr::null_mut();
            }

            match self.next.compare_exchange_weak(
                current_next,
                alloc_end,
                Ordering::Relaxed,
                Ordering::Relaxed,
            ) {
                Ok(_) => return alloc_start as *mut u8,
                Err(actual) => current_next = actual,
            }
        }
    }

    unsafe fn dealloc(&self, _ptr: *mut u8, _layout: core::alloc::Layout) {
        // No-op
    }
}
#[global_allocator]
static HEAP: BumpAllocator = BumpAllocator {
    start: 0x80210000,
    end: 0x80A00000, // 8MB heap
    next: AtomicUsize::new(0x80210000),
};

/// Minimal panic handler for bare-metal
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    virtio_pixel_rs_v3_riscv::println!("PANIC: {}", _info);
    loop {}
}

/// Minimal entry point — OpenSBI jumps here directly

core::arch::global_asm!(
    ".section .text.entry",
    ".global _start",
    "_start:",
    "la sp, _boot_stack_top",
    "j rust_main"
);

#[no_mangle]
pub extern "C" fn rust_main() -> ! {

    // Minimal early init — no heap allocator yet, just the embedded image
    unsafe { virtio_pixel_rs_v3_riscv::uart::UART.init(); }
    setup_trap_table();
    virtio_pixel_rs_v3_riscv::println!("Trap table initialized");
virtio_pixel_rs_v3_riscv::println!("RISC-V Bootloader: UART initialized");
    
    
    let image_png = &HELLO_PNG[..];
    virtio_pixel_rs_v3_riscv::println!("PNG Signature: {:02x} {:02x} {:02x} {:02x}", image_png[0], image_png[1], image_png[2], image_png[3]);

    virtio_pixel_rs_v3_riscv::println!("Decoding PXC1 Hilbert PNG ({} bytes)...", image_png.len());
    let mut decoder = virtio_pixel_rs_v3_shared::decoder::PixelDecoder::new();
    let image_vec = match decoder.decode_geos_pixel_container(image_png) {
        Ok(v) => v,
        Err(e) => {
            virtio_pixel_rs_v3_riscv::println!("Decode error: {}", e);
            loop {}
        }
    };
    let image = &image_vec[..];
    virtio_pixel_rs_v3_riscv::println!("Decode success! Output size: {} bytes", image.len());

virtio_pixel_rs_v3_riscv::println!("Parsing ELF... First bytes: {:02x} {:02x} {:02x} {:02x}", image[0], image[1], image[2], image[3]); virtio_pixel_rs_v3_riscv::println!("First bytes: {:02x} {:02x} {:02x} {:02x}", image[0], image[1], image[2], image[3]);

    // Parse ELF64 header
    let loader = Elf64Loader::new(image);
    let header = match loader.parse_header() {
        Ok(h) => h,
        Err(e) => { virtio_pixel_rs_v3_riscv::println!("Error: {}", e); loop {} },
    };

    // Verify this is a RISC-V kernel
    virtio_pixel_rs_v3_riscv::println!("Checking machine...");
if let Err(e) = check_machine(&header) { virtio_pixel_rs_v3_riscv::println!("check_machine: {}", e);
        loop {}
    }

    // Load all PT_LOAD segments
    virtio_pixel_rs_v3_riscv::println!("Getting segments...");
let segments = match loader.get_loadable_segments(&header) {
        Ok(s) => s,
        Err(e) => { virtio_pixel_rs_v3_riscv::println!("Error: {}", e); loop {} },
    };

    virtio_pixel_rs_v3_riscv::println!("Loading {} segments...", segments.len());
for seg in &segments {
        virtio_pixel_rs_v3_riscv::println!("Seg offset: {}, size: {}, memsz: {}, p_paddr: {:#x}", seg.p_offset, seg.p_filesz, seg.p_memsz, seg.p_paddr);
        let file_start = seg.p_offset as usize;
        let file_end = file_start + seg.p_filesz as usize;

        unsafe {
            let dst = seg.p_paddr as *mut u8;
            core::ptr::copy_nonoverlapping(
                image[file_start..file_end].as_ptr(),
                dst,
                seg.p_filesz as usize,
            );
            if seg.p_memsz > seg.p_filesz {
                let bss_start = dst.add(seg.p_filesz as usize);
                core::ptr::write_bytes(bss_start, 0, (seg.p_memsz - seg.p_filesz) as usize);
            }
        }
    }

    // Set up RISC-V trap table for ecall interception
    // Set up stack pointer (OpenSBI convention: 0x80200000, stack grows down)
    let mut state = CpuState::default();
    state.sp = 0x80200000;

    // Hand off to kernel entry point
    unsafe {
        virtio_pixel_rs_v3_riscv::println!("RISC-V Bootloader: Handing off to entry {:#x}", header.e_entry);
        
        let mut sstatus: u64;
        core::arch::asm!("csrr {}, sstatus", out(reg) sstatus);
        virtio_pixel_rs_v3_riscv::println!("sstatus before handoff: {:#x}", sstatus);
        handoff::handoff_to_kernel(header.e_entry, &state);

    }
}