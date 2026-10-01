import re

with open("systems/v4_bootloader_x86/src/media.rs", "r") as f:
    data = f.read()

# Replace the loop with a single read_block call
old_code = """        for i in 0..blocks {
            let buf_offset = (i * block_size) as usize;
            self.device.read_block(start_lba + i, &mut buffer[buf_offset..buf_offset + block_size as usize])?;
        }"""
new_code = """        // Read all blocks in one operation for performance
        self.device.read_block(start_lba, &mut buffer)?;"""

data = data.replace(old_code, new_code)

with open("systems/v4_bootloader_x86/src/media.rs", "w") as f:
    f.write(data)
