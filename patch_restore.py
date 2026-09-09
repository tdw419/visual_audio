import re

with open("systems/geos_pixel/src/pdb/decoder.rs", "r") as f:
    content = f.read()

decode_first_table = """    pub fn decode_first_table(&self) -> PdbResult<Vec<u8>> {
        if self.header.is_none() {
            return Err(PdbError::DecodingFailed);
        }
        let header = self.header.as_ref().unwrap();
        if header.tables.is_empty() {
            return Err(PdbError::DecodingFailed);
        }
        self.decode_table_by_metadata(&header.tables[0])
    }
"""

content = content.replace("    pub fn decode_table(&self", decode_first_table + "\n    pub fn decode_table(&self")

with open("systems/geos_pixel/src/pdb/decoder.rs", "w") as f:
    f.write(content)
