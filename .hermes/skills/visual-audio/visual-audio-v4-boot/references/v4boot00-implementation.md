# V4Boot00 Implementation Details

Session: 2026-08-22 (TASK_V404 completion)

## Actual Bootloader Implementation

### V4Boot00 Disk Reader (`media.rs`)

**Key Method**: `find_nth_png_tile(tile_index: usize)`

```rust
pub fn find_nth_png_tile(&mut self, tile_index: usize) -> Result<(u64, usize), &'static str> {
    let PNG_MAGIC: &[u8; 8] = b"\x89PNG\r\n\x1a\n";

    // 1. Get end of tiles.json block
    let (_tiles_offset, tiles_data) = self.locate_tiles_json()?;
    let mut scan_offset = _tiles_offset + tiles_data.len() as u64;

    // 2. Scan for PNG magic bytes in 64KB chunks
    let mut found_count = 0usize;
    let mut current_tile_start = 0u64;
    const CHUNK_SIZE: usize = 64 * 1024;

    while found_count <= tile_index {
        let chunk = self.read_bytes(scan_offset, CHUNK_SIZE)?;

        for i in 0..chunk.len().saturating_sub(8) {
            if &chunk[i..i+8] == PNG_MAGIC {
                if found_count == tile_index {
                    current_tile_start = scan_offset + i as u64;
                    found_count += 1;
                    break;
                }
                found_count += 1;
            }
        }

        // 3. Determine tile size by scanning for next PNG
        if found_count > tile_index {
            scan_offset = current_tile_start + 8;
            let mut size = 8usize;
            loop {
                let next_chunk = self.read_bytes(current_tile_start + size as u64, CHUNK_SIZE)?;
                for i in 0..next_chunk.len().saturating_sub(8) {
                    if &next_chunk[i..i+8] == PNG_MAGIC {
                        size += i;
                        return Ok((current_tile_start, size));
                    }
                }
                size += CHUNK_SIZE;
                if size > 256 * 1024 * 1024 { break; } // Sanity cap
            }
            return Ok((current_tile_start, size));
        }
        scan_offset += CHUNK_SIZE as u64;
    }

    Err("PNG tile not found")
}
```

**No-std Considerations**:
- No JSON parsing in bootloader (impossible without alloc/std)
- Sequential scanning by PNG magic bytes
- Fixed 64KB read chunks to control memory
- 256MB sanity cap on tile size

### Bootloader Boot Path (`bootloader_uefi.rs`)

```rust
// 1. Locate V4BOOT00 header
let (_tiles_json_offset, tiles_json_data) = match reader.locate_tiles_json() {
    Ok(res) => res,
    Err(_) => {
        // Fallback to V3 raw PNG scan
        let mut image = reader.read_bytes(0, scan_bytes)?;
        let decoder = PixelDecoder::new();
        let payload = decoder.decode_geos_pixel_container(&image)?;
        boot_elf(&payload);
        continue;
    }
};

// 2. Load kernel (tile 0)
let (kernel_offset, kernel_size) = reader.find_nth_png_tile(0)?;
let kernel_png = reader.read_bytes(kernel_offset, kernel_size)?;
let kernel_payload = decoder.decode_geos_pixel_container(&kernel_png)?;

// 3. Load initramfs (tile 1) - optional
let (initramfs_offset, initramfs_size) = match reader.find_nth_png_tile(1) {
    Ok((offset, size)) => (offset, size),
    Err(e) => {
        uefi::println!("Warning: No initramfs, booting kernel only...");
        boot_elf(&kernel_payload);
        continue;
    }
};
let initramfs_payload = decoder.decode_geos_pixel_container(&initramfs_png)?;

// 4. Handoff
boot_elf(&kernel_payload);
```

## Disk Layout (Actual)

```
Offset          Content
[0..8]          V4BOOT00 magic
[8..16]         Manifest size (u64 LE)
[16..X]         Manifest JSON (production metadata)
[X..X+8]        tiles.json size (u64 LE)
[X+8..Y]        tiles.json JSON:
                {
                  "note": "Bootloader uses sequential tile scanning",
                  "kernel_tile": 0,
                  "initramfs_tile": 1,
                  "rootfs_tiles_start": 2,
                  "rootfs_tile_count": 1
                }
[Y..Y+offset0]  kernel.pdb.png (PNG magic, tile 0)
[Y+offset0..]   initramfs.pdb.png (PNG magic, tile 1)
[...]           rootfs.0.0.pdb.png, rootfs.0.1.pdb.png, ... (tiles 2+)
```

**Tile Indexing Convention**:
- `tile 0`: kernel (single-tile PDB)
- `tile 1`: initramfs (single-tile PDB)
- `tile 2+`: rootfs tiles (tiled PDB)

## Verification Script Pattern

**File**: `tools/verify_v4_disk.py`

**Key Verification Steps**:

1. **Magic byte detection**:
   ```python
   magic = data[:8]
   assert magic == b"V4BOOT00"
   ```

2. **PNG tile scanning** (simulates bootloader logic):
   ```python
   while scan_offset < len(data):
       if data[scan_offset:scan_offset+8] == PNG_MAGIC:
           png_offsets.append(scan_offset)
   ```

3. **PNG structure validation**:
   ```python
   # Check IHDR chunk
   ihdr_len = struct.unpack('>I', png_data[8:12])[0]
   ihdr_type = png_data[12:16]
   assert ihdr_type == b'IHDR'

   # Verify power-of-2 dimensions (Hilbert requirement)
   width = struct.unpack('>I', png_data[16:20])[0]
   height = struct.unpack('>I', png_data[20:24])[0]
   assert (width & (width - 1)) == 0
   assert (height & (height - 1)) == 0
   ```

## Pitfall: UEFI Boot Requires ESP Partition

**Problem**: V4Boot00 raw disks are not recognized by UEFI firmware

**Root Cause**: UEFI firmware looks for:
1. GPT partition table
2. EFI System Partition (ESP) with FAT32 filesystem
3. `EFI/BOOT/BOOTX64.EFI` bootloader in ESP

**Solution**: Create properly partitioned disk:

```bash
# Using sgdisk (requires sudo)
sgdisk -Z disk.img              # Zap existing partitions
sgdisk -o disk.img              # Create GPT
sgdisk -n 1:2048:+64M disk.img  # ESP (64MB)
sgdisk -t 1:C12A7328-F81F-11D2-BA4B-00A0C93EC93B disk.img  # ESP type
sgdisk -n 2:0:0 disk.img        # Data partition (V4BOOT00)
sgdisk -t 2:0FC63DAF-8483-4772-8E79-3D69D8477DE4 disk.img  # Linux FS

# Format ESP as FAT32
losetup -o 1048576 --sizelimit $((64*1024*1024)) /dev/loop0 disk.img
mkfs.vfat -F 32 /dev/loop0

# Copy bootloader
mount /dev/loop0 /mnt/esp
mkdir -p /mnt/esp/EFI/BOOT
cp bootloader_uefi_v4.efi /mnt/esp/EFI/BOOT/BOOTX64.EFI
```

**Reference Script**: `tools/create_v4_uefi_disk.sh` (requires sudo for losetup/mount)

## Verified Working Commands

```bash
# 1. Build V4 bootloader
cargo build --release --target x86_64-unknown-uefi -p v4_bootloader_x86

# 2. Build encoding tools
cargo build --release --example encode_file_to_pdb
cargo build --release --example compile_v4_1_tiled

# 3. Create V4 boot image
python3 tools/v4_boot_builder.py \
  --kernel /path/to/vmlinuz \
  --initramfs /path/to/initramfs.cpio.gz \
  --rootfs /path/to/rootfs.ext4 \
  --output /tmp/ubuntu_v4.img

# 4. Verify disk format
python3 tools/verify_v4_disk.py

# 5. Create UEFI bootable disk (requires sudo)
sudo bash tools/create_v4_uefi_disk.sh

# 6. Boot test (UEFI + virtio-blk)
qemu-system-x86_64 \
  -bios /usr/share/ovmf/OVMF.fd \
  -drive format=raw,file=/tmp/v4_uefi_disk.img,if=none,id=disk \
  -device virtio-blk-pci,drive=disk,bootindex=1 \
  -nographic -serial mon:stdio -smp 2 -m 512M
```

## Performance Characteristics

| Metric | Value |
|--------|-------|
| PNG detection (per 64KB chunk) | <1ms |
| Tile size determination | O(tile_size) scanning |
| Bootloader build time | <2s |
| Encoding (kernel+initramfs) | <5s |
| Tiled rootfs encoding | Depends on size (16MB example ~1s) |

## Files Modified This Session

- `systems/v4_bootloader_x86/src/media.rs`: Added `find_nth_png_tile()`
- `systems/v4_bootloader_x86/src/bootloader_uefi.rs`: Filled V4 boot path TODOs
- `tools/v4_boot_builder.py`: Complete V4BOOT00 packer
- `tools/verify_v4_disk.py`: Verification script
- `tools/create_v4_uefi_disk.sh`: ESP partition creation script
- `tools/create_v4_uefi_disk.py`: Python ESP partition creation
- `systems/geos_pixel/examples/encode_file_to_pdb.rs`: Fixed import path (`geos_pixel::pdb::`)