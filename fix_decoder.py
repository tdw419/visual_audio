import re

with open("systems/geos_pixel/src/pdb/decoder.rs", "r") as f:
    content = f.read()

decode_table_by_metadata = """    pub fn decode_first_table(&self) -> PdbResult<Vec<u8>> {
        if self.header.is_none() {
            return Err(PdbError::DecodingFailed);
        }
        let header = self.header.as_ref().unwrap();
        if header.tables.is_empty() {
            return Err(PdbError::DecodingFailed);
        }
        self.decode_table_by_metadata(&header.tables[0])
    }

    pub fn decode_table(&self, table_name: &str) -> PdbResult<Vec<u8>> {
        if self.header.is_none() {
            return Err(PdbError::DecodingFailed);
        }

        let header = self.header.as_ref().unwrap();

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
    }

    fn decode_table_by_metadata(&self, metadata: &TableMetadata) -> PdbResult<Vec<u8>> {"""

content = re.sub(r'    pub fn decode_table\(&self, table_name: &str\) -> PdbResult<Vec<u8>> \{\n        if self\.header\.is_none\(\) \{\n            return Err\(PdbError::DecodingFailed\);\n        \}\n\n        let header = self\.header\.as_ref\(\)\.unwrap\(\);\n\n        // Find table by name\n        let metadata = header\n            \.tables\n            \.iter\(\)\n            \.find\(\|t\| \{\n                let name_str = std::str::from_utf8\(&t\.name\)\n                    \.unwrap_or\(""\)\n                    \.trim_end_matches\(\'\\0\'\);\n                name_str == table_name\n            \}\)\n            \.ok_or\(PdbError::DecodingFailed\)\?;', decode_table_by_metadata, content)

with open("systems/geos_pixel/src/pdb/decoder.rs", "w") as f:
    f.write(content)
