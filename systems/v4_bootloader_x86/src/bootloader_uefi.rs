#![no_std]
#![no_main]

extern crate alloc;

use uefi::prelude::*;
use uefi::Identify;
use uefi::boot::{self, SearchType};
use uefi::proto::media::block::BlockIO;
use uefi::table::system_table_raw;
use log::info;

mod media;
mod linux_boot;

use media::{UefiBlockDevice, V4DiskReader};
use geos_pixel::decoder::PixelDecoder;
use linux_boot::{BzImage, BootParams};

const MAX_IMAGE_SCAN_BYTES: usize = 16 * 1024 * 1024;

use uefi_raw;

type EfiHandoverEntry = unsafe extern "sysv64" fn(Handle, *const uefi_raw::table::system::SystemTable, *mut BootParams) -> !;

#[entry]
fn main() -> Status {
    uefi::helpers::init().unwrap();
    let _ = uefi::boot::set_watchdog_timer(0, 0, None);
    info!("virtio_pixel_rs_v4_x86: Linux boot protocol support (x86_64)");

    let image_handle = uefi::boot::image_handle();

    let Ok(handles) = boot::locate_handle_buffer(SearchType::ByProtocol(&BlockIO::GUID)) else {
        info!("No BlockIO devices found.");
        boot::stall(core::time::Duration::from_secs(5));
        return Status::SUCCESS;
    };

    for handle in handles.iter() {
        let Ok(mut block_io) = boot::open_protocol_exclusive::<BlockIO>(*handle) else {
            continue;
        };

        let block_size = block_io.media().block_size() as u64;
        let total_blocks = block_io.media().last_block() + 1;

        info!(
            "Scanning BlockIO device: block_size={}, total_blocks={}",
            block_size,
            total_blocks
        );

        let block_device = UefiBlockDevice::new(&mut block_io);
        let mut reader = V4DiskReader::new(block_device);

        let result = match reader.locate_tiles_json() {
            Ok(res) => {
                info!("Found V4BOOT00 header, tiles.json at offset {}", res.0);
                Some(res)
            }
            Err(_) => {
                info!("Not a V4 boot disk, skipping...");
                None
            }
        };

        if result.is_none() {
            continue;
        }

        info!("=== V4 Boot Path (Linux bzImage) ===");
        info!("Loading kernel PNG (tile 0)...");

        let (kernel_offset, kernel_size) = match reader.find_nth_png_tile(0) {
            Ok((offset, size)) => {
                info!("Kernel PNG found at offset {} ({} bytes)", offset, size);
                (offset, size)
            }
            Err(e) => {
                info!("Failed to locate kernel PNG: {}", e);
                continue;
            }
        };

        let kernel_png = match reader.read_bytes(kernel_offset, kernel_size) {
            Ok(png) => png,
            Err(e) => {
                info!("Failed to read kernel PNG: {}", e);
                continue;
            }
        };

        let mut decoder = PixelDecoder::new();
        let kernel_bzimage = match decoder.decode_pdb_table(&kernel_png, 0) {
            Ok(decoded) => {
                info!("Kernel decoded: {} bytes", decoded.len());
                decoded
            }
            Err(e) => {
                info!("Failed to decode kernel PNG: {}", e);
                continue;
            }
        };

        info!("Parsing bzImage...");
        let bzimage = match BzImage::parse(&kernel_bzimage) {
            Ok(bz) => bz,
            Err(e) => {
                info!("Failed to parse bzImage: {}", e);
                continue;
            }
        };

        let header = bzimage.header();
        info!(
            "bzImage header: version=0x{:04x}, pref_address=0x{:x}, payload_offset=0x{:x}, handover_offset=0x{:x}",
            { header.version }, { header.pref_address },
            { header.payload_offset },
            { header.handover_offset }
        );

        info!("Loading initramfs PNG (tile 1)...");
        let initramfs_payload = match reader.find_nth_png_tile(1) {
            Ok((offset, size)) => {
                info!("Initramfs PNG found at offset {} ({} bytes)", offset, size);
                match reader.read_bytes(offset, size) {
                    Ok(png) => match decoder.decode_pdb_table(&png, 0) {
                        Ok(decoded) => {
                            info!("Initramfs decoded: {} bytes", decoded.len());
                            decoded
                        }
                        Err(e) => {
                            info!("Failed to decode initramfs PNG: {}", e);
                            info!("Booting with kernel only...");
                            return boot_linux_kernel(image_handle, &bzimage, &kernel_bzimage, None);
                        }
                    },
                    Err(e) => {
                        info!("Failed to read initramfs PNG: {}", e);
                        info!("Booting with kernel only...");
                        return boot_linux_kernel(image_handle, &bzimage, &kernel_bzimage, None);
                    }
                }
            }
            Err(e) => {
                info!("Warning: Failed to locate initramfs PNG: {}", e);
                info!("Booting with kernel only...");
                return boot_linux_kernel(image_handle, &bzimage, &kernel_bzimage, None);
            }
        };

        return boot_linux_kernel(image_handle, &bzimage, &kernel_bzimage, Some(&initramfs_payload));
    }

    boot::stall(core::time::Duration::from_secs(10));
    Status::SUCCESS
}

fn boot_linux_kernel(
    image_handle: Handle,
    bzimage: &BzImage,
    kernel_data: &[u8],  // Full bzImage, not just payload
    initramfs_data: Option<&[u8]>,
) -> Status {
    let header = bzimage.header();
    let pref_address = bzimage.pref_address();
    let kernel_alignment = bzimage.kernel_alignment() as u64;

    info!("=== Linux Boot Protocol ===");
    info!("Pref address: 0x{:x}", pref_address);
    info!("Kernel size: {} bytes (full bzImage)", kernel_data.len());
    info!("Kernel alignment: 0x{:x}", kernel_alignment);

    let kernel_pages = (kernel_data.len() as u64 + 4095) / 4096;

    info!("Allocating {} pages at 0x{:x}...", kernel_pages, pref_address);

    let kernel_base = unsafe {
        // Try preferred address first
        match uefi::boot::allocate_pages(
            uefi::boot::AllocateType::Address(pref_address),
            uefi::boot::MemoryType::LOADER_DATA,
            kernel_pages as usize,
        ) {
            Ok(addr) => {
                info!("Kernel allocated at 0x{:x}", addr.as_ptr() as u64);
                addr
            }
            Err(_) => {
                info!("Preferred address unavailable, allocating anywhere...");
                // Fallback: allocate anywhere
                uefi::boot::allocate_pages(
                    uefi::boot::AllocateType::MaxAddress(0xFFFFFFFF),
                    uefi::boot::MemoryType::LOADER_DATA,
                    kernel_pages as usize,
                )
                .expect("Failed to allocate kernel memory anywhere")
            }
        }
    };

    info!("Kernel allocated at 0x{:x}", kernel_base.as_ptr() as u64);

    info!("Loading kernel (full bzImage)...");
    unsafe {
        core::ptr::copy_nonoverlapping(kernel_data.as_ptr(), kernel_base.as_ptr(), kernel_data.len());
    }

    let (initramfs_addr, initramfs_size) = if let Some(initrd) = initramfs_data {
        let initrd_pages = (initrd.len() as u64 + 4095) / 4096;

        info!("Allocating {} pages for initramfs...", initrd_pages);
        let initrd_base = unsafe {
            uefi::boot::allocate_pages(
                uefi::boot::AllocateType::MaxAddress(0xFFFFFFFF),
                uefi::boot::MemoryType::LOADER_DATA,
                initrd_pages as usize,
            )
        };

        let initrd_base = match initrd_base {
            Ok(addr) => {
                info!("Initramfs allocated at 0x{:x}", addr.as_ptr() as u64);
                addr
            }
            Err(e) => {
                info!("Failed to allocate initramfs memory: {:?}", e);
                boot::stall(core::time::Duration::from_secs(5));
                return Status::LOAD_ERROR;
            }
        };

        info!("Loading initramfs...");
        unsafe {
            core::ptr::copy_nonoverlapping(initrd.as_ptr(), initrd_base.as_ptr(), initrd.len());
        }

        (initrd_base.as_ptr() as u64, initrd.len() as u32)
    } else {
        (0, 0)
    };

    info!("Setting up boot_params from bzImage...");
    let mut boot_params_stack = match BootParams::from_bzimage(kernel_data) {
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


    // Override bootloader-provided fields
    boot_params.set_ext_ramdisk(initramfs_addr as u64, initramfs_size as u64);
    boot_params.hdr_mut().ramdisk_image = initramfs_addr as u32;
    boot_params.hdr_mut().ramdisk_size = initramfs_size as u32;
    

    // Set up command line with console=ttyS0 for serial output
    // Mask slow services to reach login quickly
    const CMDLINE: &[u8] = b"console=ttyS0,115200 earlyprintk=serial,ttyS0,115200 earlycon=uart8250,io,0x3f8 loglevel=7 debug cloud-init=disabled systemd.mask=snapd.service systemd.mask=snapd.seeded.service systemd.mask=systemd-networkd-wait-online.service\0";
    let cmdline_pages = (CMDLINE.len() as u64 + 4095) / 4096;
    let cmdline_base = unsafe {
        uefi::boot::allocate_pages(
            uefi::boot::AllocateType::AnyPages,
            uefi::boot::MemoryType::LOADER_DATA,
            cmdline_pages as usize,
        )
    };

    let (cmdline_addr, cmdline_ptr) = match cmdline_base {
        Ok(addr) => {
            info!("Command line allocated at 0x{:x}", addr.as_ptr() as u64);
            unsafe {
                core::ptr::copy_nonoverlapping(CMDLINE.as_ptr(), addr.as_ptr(), CMDLINE.len());
            }
            (addr.as_ptr() as u64, addr.as_ptr() as u32)
        }
        Err(e) => {
            info!("Failed to allocate command line memory: {:?}, booting without cmdline", e);
            (0, 0)
        }
    };

    // Set cmd_line_ptr for newer kernels (2.12+)
    if cmdline_ptr != 0 {
        boot_params.set_cmdline(cmdline_addr);
        boot_params.hdr_mut().type_of_loader = 0x21;
        boot_params.hdr_mut().ext_loader_type = 0;
    }

    // For EFI handover (XLF_EFI_HANDOVER_64), handover_offset is relative to bzImage start
    
    // handover_offset is relative to the start of the payload (startup_32)
    // The payload starts after the setup code.
    let setup_sects = header.setup_sects;
    let setup_sects = if setup_sects == 0 { 4 } else { setup_sects };
    let setup_size = (setup_sects as u64 + 1) * 512;
    
    // For 64-bit EFI handover, it's at handover_offset + 512
    let handover_offset = { header.handover_offset } as u64 + 512;
    
    let handover_addr = kernel_base.as_ptr() as u64 + setup_size + handover_offset;

        info!("Handover entry: 0x{:x}", handover_addr);

    info!("CMDLINE ptr: 0x{:x}, string: {}", cmdline_addr, core::str::from_utf8(&CMDLINE[..CMDLINE.len()-1]).unwrap_or("INVALID"));
    info!("Jumping to Linux kernel...");
    
    // Stall for 2 seconds to allow pre-jump screendump capture
    uefi::boot::stall(core::time::Duration::from_secs(2));

    let handover_entry: EfiHandoverEntry = unsafe { core::mem::transmute(handover_addr) };

    let system_table = system_table_raw().expect("System table not available").as_ptr();

    unsafe {
        let null_handle = core::mem::transmute(0usize);
        handover_entry(null_handle, system_table, boot_params as *mut _);
    }

    Status::LOAD_ERROR
}