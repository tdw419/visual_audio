import re

with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    content = f.read()

trans_code = """
        if magic != 0x25609513 {
            return Err(format!("Invalid request magic: 0x{:x}", magic).into());
        }

        let cmd_flags = stream.read_u16::<BigEndian>()?;
        let cmd = stream.read_u16::<BigEndian>()?;
        let mut handle = [0u8; 8];
        stream.read_exact(&mut handle)?;
        let offset = stream.read_u64::<BigEndian>()?;
        let length = stream.read_u32::<BigEndian>()?;

        trace!(
            "Request: cmd={}, flags={}, handle={:?}, offset={}, len={}",
            cmd,
            cmd_flags,
            handle,
            offset,
            length
        );
"""

content = re.sub(
r"""        if magic != 0x25609513 \{
            return Err\(format!\("Invalid request magic: 0x\{:x\}", magic\)\.into\(\)\);
        \}

        let cmd = stream\.read_u16::<BigEndian>\(\)\?;
        let mut handle = \[0u8; 8\];
        stream\.read_exact\(&mut handle\)\?;
        let offset = stream\.read_u64::<BigEndian>\(\)\?;
        let length = stream\.read_u32::<BigEndian>\(\)\?;

        trace!\(
            "Request: cmd=\{\}, handle=\{:\?\}, offset=\{\}, len=\{\}",
            cmd,
            handle,
            offset,
            length
        \);""", trans_code, content)

with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
    f.write(content)
