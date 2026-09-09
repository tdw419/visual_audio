import re

with open("systems/geos_pixel/src/pdb/decoder.rs", "r") as f:
    content = f.read()

decode_raw = """    pub fn decode_raw_tile(&self, bbox: BoundingBox, expected_bytes: usize) -> PdbResult<Vec<u8>> {
        let expected_triplets = (expected_bytes + 2) / 3;

        let width = bbox.x_max - bbox.x_min + 1;
        let height = bbox.y_max - bbox.y_min + 1;
        let mut grid_size = width.max(height).next_power_of_two();
        if grid_size < 2 { grid_size = 2; }

        let mut out = Vec::with_capacity(expected_bytes);

        let mut i = 0;
        let mut triplets_found = 0;
        while triplets_found < expected_triplets {
            let (x, y) = crate::hilbert::HilbertCurve::d2xy(grid_size as usize, i);
            i += 1;
            let abs_x = bbox.x_min + x as u32;
            let abs_y = bbox.y_min + y as u32;

            if abs_x <= bbox.x_max && abs_y <= bbox.y_max {
                let pixel = self.canvas.get_pixel(abs_x, abs_y);
                out.push(pixel[0]);
                out.push(pixel[1]);
                out.push(pixel[2]);
                triplets_found += 1;
            }
        }

        out.truncate(expected_bytes);
        Ok(out)
    }

    fn decode_table_by_metadata(&self,"""

content = content.replace("    fn decode_table_by_metadata(&self,", decode_raw)

with open("systems/geos_pixel/src/pdb/decoder.rs", "w") as f:
    f.write(content)
