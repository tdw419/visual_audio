import sys
from pathlib import Path

content = Path("tools/v4_boot_builder.py").read_text()

pack_func = """
def pack_unified_disk(manifest: dict, manifest_path: Path, output_path: Path):
    print(f"Packing unified disk image: {output_path}")
    import struct
    
    with open(output_path, 'wb') as out:
        # Magic
        out.write(b'V4BOOT00')
        
        # Manifest
        manifest_bytes = json.dumps(manifest).encode('utf-8')
        out.write(struct.pack('<Q', len(manifest_bytes)))
        out.write(manifest_bytes)
        
        # tiles.json
        tiles_dir = Path(manifest["sections"]["rootfs"]["tiles_dir"])
        tiles_json_bytes = (tiles_dir / "tiles.json").read_bytes()
        out.write(struct.pack('<Q', len(tiles_json_bytes)))
        out.write(tiles_json_bytes)
        
        # We also need to pack the actual PDB PNGs!
        # But wait, the UEFI bootloader will need the offsets of the PNGs!
        # Let's align to 4096 bytes
        def align():
            pos = out.tell()
            rem = pos % 4096
            if rem != 0:
                out.write(b'\\x00' * (4096 - rem))
                
        align()
        
        # Pack Kernel PDB
        kernel_path = Path(manifest["sections"]["kernel"]["pdb_file"])
        kernel_pos = out.tell()
        out.write(kernel_path.read_bytes())
        manifest["sections"]["kernel"]["disk_offset"] = kernel_pos
        
        align()
        
        # Pack Initramfs PDB
        init_path = Path(manifest["sections"]["initramfs"]["pdb_file"])
        init_pos = out.tell()
        out.write(init_path.read_bytes())
        manifest["sections"]["initramfs"]["disk_offset"] = init_pos
        
        # Update manifest on disk with the new offsets (requires rewriting the manifest area, but it's variable size!)
        # Better: just output the disk offsets in a new manifest, but the bootloader doesn't parse manifest right now, it parses tiles.json or we can parse manifest if we add tinyjson!
        # Actually, let's just make the bootloader parse tiles.json, and the kernel PNG is at a fixed position or tracked in tiles.json?
"""
