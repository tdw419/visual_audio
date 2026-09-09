import re

with open("systems/geos_pixel/src/pdb/decoder.rs", "r") as f:
    content = f.read()

decode_table_new = """    pub fn decode_table(&self, table_name: &str) -> PdbResult<Vec<u8>> {
        if self.header.is_none() {
            return Err(PdbError::DecodingFailed);
        }

        let header = self.header.as_ref().unwrap();

        let mut available = Vec::new();
        for t in &header.tables {
            let name_str = std::str::from_utf8(&t.name).unwrap_or("").trim_end_matches('\\0');
            available.push(name_str.to_string());
        }
        println!("Looking for table {}, available: {:?}", table_name, available);

        // Find table by name
        let metadata = header
            .tables
            .iter()
            .find(|t| {
                let name_str = std::str::from_utf8(&t.name)
                    .unwrap_or("")
                    .trim_end_matches('\\0');
                name_str == table_name
            })
            .ok_or(PdbError::DecodingFailed)?;

        self.decode_table_by_metadata(metadata)
    }"""

content = re.sub(r'    pub fn decode_table\(&self, table_name: &str\) -> PdbResult<Vec<u8>> \{.*?self\.decode_table_by_metadata\(metadata\)\n    \}', decode_table_new, content, flags=re.DOTALL)

with open("systems/geos_pixel/src/pdb/decoder.rs", "w") as f:
    f.write(content)
