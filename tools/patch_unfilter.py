import re

with open("systems/geos_pixel/src/decoder/pixel_decoder.rs", "r") as f:
    data = f.read()

# Replace the inner loops of unfilter_png with an optimized version
optimized_unfilter = """
        for y in 0..height {
            let src_offset = y * (row_bytes + 1);
            let filter_type = decompressed[src_offset];
            let row_src = &decompressed[src_offset + 1 .. src_offset + 1 + row_bytes];
            let dst_offset = y * row_bytes;

            if filter_type == 0 {
                // Fast path for None filter
                pixels[dst_offset..dst_offset + row_bytes].copy_from_slice(row_src);
                continue;
            }

            for x in 0..row_bytes {
                let a = if x >= bpp { pixels[dst_offset + x - bpp] } else { 0 };
                let b = if y > 0 { pixels[dst_offset - row_bytes + x] } else { 0 };
                let c = if y > 0 && x >= bpp { pixels[dst_offset - row_bytes + x - bpp] } else { 0 };

                let raw = row_src[x];
                let val = match filter_type {
                    1 => raw.wrapping_add(a), // Sub
                    2 => raw.wrapping_add(b), // Up
                    3 => raw.wrapping_add(((a as u16 + b as u16) / 2) as u8), // Average
                    4 => { // Paeth
                        let p = a as i32 + b as i32 - c as i32;
                        let pa = (p - a as i32).abs();
                        let pb = (p - b as i32).abs();
                        let pc = (p - c as i32).abs();
                        let pr = if pa <= pb && pa <= pc { a }
                                 else if pb <= pc { b }
                                 else { c };
                        raw.wrapping_add(pr)
                    }
                    _ => return Err("Unknown filter type"),
                };
                pixels[dst_offset + x] = val;
            }
        }
"""

data = re.sub(
    r'for y in 0\.\.height \{.*?(?=Ok\(\(pixels, width, height, bpp\)\))',
    optimized_unfilter.strip() + '\n\n        ',
    data,
    flags=re.DOTALL
)

with open("systems/geos_pixel/src/decoder/pixel_decoder.rs", "w") as f:
    f.write(data)
