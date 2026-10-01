import sys

content = open("systems/geos_pixel/src/decoder/pixel_decoder.rs").read()

new_method = """
    /// Decode a specific table from a PDB container
    pub fn decode_pdb_table(&mut self, data: &[u8], table_index: u8) -> Result<alloc::vec::Vec<u8>, &'static str> {
        let (pixels, width, height, bpp) = self.decode_frame(data)?;

        // Helper to read a single pixel's R channel at (x, 0)
        let get_r = |x: usize| -> u8 {
            pixels[x * bpp]
        };

        // Check magic bytes
        let magic = [get_r(0), get_r(1), get_r(2), get_r(3)];
        if magic != crate::pdb::PDB_MAGIC {
            return Err("Not a valid PDB frame (magic mismatch)");
        }

        let table_count = get_r(5);
        if table_index >= table_count {
            return Err("Table index out of bounds");
        }

        let mut x_offset = 6 + (table_index as usize * 40);
        x_offset += 16; // Skip name

        let mut read_u32 = || -> u32 {
            let mut buf = [0u8; 4];
            for i in 0..4 {
                buf[i] = get_r(x_offset);
                x_offset += 1;
            }
            u32::from_le_bytes(buf)
        };

        let x_min = read_u32();
        let y_min = read_u32();
        let x_max = read_u32();
        let y_max = read_u32();
        let row_count = read_u32();
        let row_length = read_u32();

        let expected_bytes = (row_count * row_length) as usize;
        let mut output = alloc::vec::Vec::with_capacity(expected_bytes);

        let table_width = x_max - x_min + 1;
        let table_height = y_max - y_min + 1;
        let mut grid_size = table_width.max(table_height).next_power_of_two();
        if grid_size < 2 { grid_size = 2; }

        let mut i = 0;
        while output.len() < expected_bytes {
            let (x, y) = crate::hilbert::HilbertCurve::d2xy(grid_size as usize, i);
            i += 1;

            let abs_x = x_min as usize + x as usize;
            let abs_y = y_min as usize + y as usize;

            if abs_x <= x_max as usize && abs_y <= y_max as usize {
                let pixel_idx = (abs_y * width + abs_x) * bpp;
                output.push(pixels[pixel_idx]);
                if output.len() < expected_bytes {
                    output.push(pixels[pixel_idx + 1]);
                }
                if output.len() < expected_bytes {
                    output.push(pixels[pixel_idx + 2]);
                }
            }
        }

        Ok(output)
    }
"""

# Insert before the last closing brace of impl PixelDecoder
idx = content.rfind("}\n}")
if idx != -1:
    content = content[:idx] + new_method + content[idx:]
    open("systems/geos_pixel/src/decoder/pixel_decoder.rs", "w").write(content)
    print("Patched!")
else:
    print("Could not find insertion point!")
