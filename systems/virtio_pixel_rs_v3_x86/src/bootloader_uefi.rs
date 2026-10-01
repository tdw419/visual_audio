#![no_std]
#![no_main]
extern crate alloc;

mod media;

use uefi::Identify;

use uefi::prelude::*;
use uefi::boot::{self, SearchType};
use uefi::proto::media::block::BlockIO;
use media::{UefiBlockDevice, MediaReader, MediaSource};
use virtio_pixel_rs_v3_shared::elf64::{Elf64Loader, check_machine};
use virtio_pixel_rs_v3_shared::handoff::{self, CpuState};

use virtio_pixel_rs_v3_shared::ecall::setup_trap_table;
use virtio_pixel_rs_v3_shared::decoder::PixelDecoder;

/// Maximum bytes to scan for ELF header/segments. Sized from disk capacity, capped here.
/// Small kernels (hello.img, test kernels) will use less; larger kernels need more.
const MAX_IMAGE_SCAN_BYTES: usize = 4 * 1024 * 1024; // 4MB cap for safety

#[entry]
fn main() -> Status {
    uefi::helpers::init().unwrap();
    let _ = uefi::boot::set_watchdog_timer(0, 0, None);
    uefi::println!("virtio_pixel_rs_v3_x86: bare-metal bootloader alive (x86_64)");

    let Ok(handles) = boot::locate_handle_buffer(SearchType::ByProtocol(&BlockIO::GUID)) else {
        uefi::println!("No BlockIO devices found.");
        boot::stall(core::time::Duration::from_secs(5));
        return Status::SUCCESS;
    };

    for handle in handles.iter() {
        let Ok(mut block_io) = boot::open_protocol_exclusive::<BlockIO>(*handle) else {
            uefi::println!("Failed to open BlockIO exclusively for a handle.");
            continue;
        };
        let media = block_io.media();
        let block_size = media.block_size();
        let total_blocks = media.last_block() + 1;

        uefi::println!(
            "Found BlockIO device: block_size={}, total_blocks={}",
            block_size,
            total_blocks
        );

        let block_device = UefiBlockDevice::new(&mut block_io);
        let mut reader = MediaReader::new(block_device, MediaSource::SD);

        let block_size_u64 = block_size as u64;
        let disk_bytes = total_blocks * block_size_u64;
        let scan_bytes = core::cmp::min(disk_bytes as usize, MAX_IMAGE_SCAN_BYTES);
        let scan_blocks = (scan_bytes as u64 + block_size_u64 - 1) / block_size_u64;

        uefi::println!(
            "Scanning {} bytes ({} blocks) from disk...",
            scan_bytes,
            scan_blocks
        );

        let mut image = alloc::vec![0u8; scan_bytes];
        if let Err(e) = reader.read_blocks(0, scan_blocks, &mut image) {
            uefi::println!("Failed to read image: {}", e);
            continue;
        }
        uefi::println!("Read {} bytes from disk.", image.len());

        let payload = if image.len() >= 8 && &image[0..8] == b"\x89PNG\r\n\x1a\n" {
            uefi::println!("Found PNG signature — executing Hilbert pixel-decode path...");
            let mut decoder = PixelDecoder::new();
            match decoder.decode_geos_pixel_container(&image) {
                Ok(decoded) => {
                    uefi::println!("Successfully decoded PNG into {} bytes of executable payload.", decoded.len());
                    decoded
                }
                Err(e) => {
                    uefi::println!("Failed to decode PNG: {}", e);
                    continue;
                }
            }
        } else {
            image
        };

        let loader = Elf64Loader::new(&payload);
        let header = match loader.parse_header() {
            Ok(h) => h,
            Err(e) => {
                uefi::println!("Not a bootable ELF: {}", e);
                continue;
            }
        };
        uefi::println!(
            "ELF64 entry: {:#x}, e_machine: {:#x}",
            header.e_entry,
            header.e_machine
        );

        if let Err(e) = check_machine(&header) {
            uefi::println!("Refusing handoff: {}", e);
            continue;
        }

        let segments = match loader.get_loadable_segments(&header) {
            Ok(s) => s,
            Err(e) => {
                uefi::println!("Failed to parse program headers: {}", e);
                continue;
            }
        };
        uefi::println!(
            "Found {} PT_LOAD segment(s), entry = {:#x}",
            segments.len(),
            header.e_entry
        );
        let mut runtime_entry = header.e_entry;

        for seg in &segments {
            let file_start = seg.p_offset as usize;
            let file_end = file_start + seg.p_filesz as usize;
            if file_end > payload.len() {
                uefi::println!("Segment file range exceeds scanned image bytes — aborting.");
                uefi::println!(
                    "Segment: p_offset={:#x} p_filesz={:#x}, scanned={:#x}",
                    seg.p_offset,
                    seg.p_filesz,
                    payload.len()
                );
                boot::stall(core::time::Duration::from_secs(5));
                return Status::LOAD_ERROR;
            }

            // SAFETY: p_paddr comes from a machine-checked ELF we just parsed. UEFI identity-maps
            // physical memory at this boot stage, so writing raw bytes here is how every bootloader
            // stages a kernel image before handoff.
            
            let num_pages = ((seg.p_memsz + 4095) / 4096) as usize;
            let allocated_addr = unsafe {
                uefi::boot::allocate_pages(
                    uefi::boot::AllocateType::AnyPages,
                    uefi::boot::MemoryType::LOADER_CODE,
                    num_pages,
                ).expect("Failed to allocate memory for ELF segment")
            };
            uefi::println!("Allocated {} pages at {:#x} (requested {:#x})", num_pages, allocated_addr.as_ptr() as u64, seg.p_paddr);
            runtime_entry = (allocated_addr.as_ptr() as u64) + (header.e_entry - seg.p_paddr);
            
            unsafe {

                let dst = allocated_addr.as_ptr();
                core::ptr::copy_nonoverlapping(
                    payload[file_start..file_end].as_ptr(),
                    dst,
                    seg.p_filesz as usize,
                );
                if seg.p_memsz > seg.p_filesz {
                    let bss_start = dst.add(seg.p_filesz as usize);
                    core::ptr::write_bytes(bss_start, 0, (seg.p_memsz - seg.p_filesz) as usize);
                }
            }
            uefi::println!(
                "Loaded segment: paddr={:#x} filesz={:#x} memsz={:#x}",
                seg.p_paddr,
                seg.p_filesz,
                seg.p_memsz
            );
        }

        // Install the ecall trap table only now, right before handoff — not
        // before the BlockIO reads above. Installing it earlier leaves 255
        // of 256 IDT vectors absent while UEFI boot services (which can
        // trigger their own interrupts, e.g. a timer tick) are still
        // running, cascading straight to a triple-fault reboot loop the
        // instant one fires. Verified 2026-08-21: this exact ordering
        // mistake reproduced a silent reboot loop on every boot.
        setup_trap_table();
        uefi::println!("Trap table installed (vector 0x80 -> stub handler).");


        

        uefi::println!("Handing off to runtime entry {:#x}...", runtime_entry);


                let mut state = CpuState::default();
        //state.rsp = 0x0030_0000; // stack region distinct from the 0x200000 load address

        unsafe {
            handoff::handoff_to_kernel(runtime_entry, &state);
        }
    }

    boot::stall(core::time::Duration::from_secs(5));
    Status::SUCCESS
}