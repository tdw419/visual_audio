import re

with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    content = f.read()

# Fix NBD_REP_MAGIC
content = content.replace("const NBD_OPT_MAGIC: u64 = 0x25609513; // Magic for option negotiation phase",
                          "const NBD_OPT_MAGIC: u64 = 0x49484156454F5054;\nconst NBD_REP_MAGIC: u64 = 0x3e889045565a9;")
content = content.replace("const NBD_REP_INFO: u32 = 4;", "const NBD_REP_INFO: u32 = 3;") # INFO is 3, not 4

# Let's completely rewrite the handshake function using regex
handshake_code = """
fn nbd_handshake<S: Read + Write>(
    mut stream: S,
    export_size: u64,
    flags: u16,
) -> Result<(), Box<dyn std::error::Error>> {
    info!("Starting raw NBD handshake");

    // 1. Server sends "NBDMAGIC" and "IHAVEOPT"
    stream.write_all(b"NBDMAGIC")?;
    stream.write_all(b"IHAVEOPT")?;

    // 2. Server sends handshake flags (FIXED_NEWSTYLE | NO_ZEROES)
    let handshake_flags: u16 = (1 << 0) | (1 << 1);
    stream.write_u16::<BigEndian>(handshake_flags)?;

    // 3. Client sends client flags
    let client_flags = stream.read_u32::<BigEndian>()?;
    info!("Client flags: 0x{:x}", client_flags);
    
    let no_zeroes = (client_flags & (1 << 1)) != 0;

    // 4. Option negotiation loop
    loop {
        let magic = stream.read_u64::<BigEndian>()?;
        if magic != 0x49484156454F5054 {
            return Err(format!("Invalid option magic: 0x{:x}", magic).into());
        }

        let opt = stream.read_u32::<BigEndian>()?;
        let opt_len = stream.read_u32::<BigEndian>()?;

        info!("Received NBD_OPT_{} (length {})", opt, opt_len);

        match opt {
            NBD_OPT_GO => {
                // Read export name
                let mut name_buf = vec![0u8; opt_len as usize];
                stream.read_exact(&mut name_buf)?;
                let name = String::from_utf8_lossy(&name_buf).trim_end_matches('\0').to_string();
                info!("Client requested export via GO: '{}'", name);
                
                // For NBD_OPT_GO, name_buf contains name_len (u32), name, info_reqs_len (u16), info_reqs...
                // Wait, no. NBD_OPT_GO data format:
                // 32 bits: length of export name
                // name
                // 16 bits: number of info requests
                // info requests...
                
                // Let's just consume the whole opt_len, we already read it into name_buf.

                // Send NBD_REP_INFO (NBD_INFO_EXPORT)
                stream.write_u64::<BigEndian>(0x3e889045565a9)?;
                stream.write_u32::<BigEndian>(opt)?;
                stream.write_u32::<BigEndian>(NBD_REP_INFO)?;
                stream.write_u32::<BigEndian>(12)?; // length: 2 (info) + 8 (size) + 2 (flags)
                stream.write_u16::<BigEndian>(NBD_INFO_EXPORT)?;
                stream.write_u64::<BigEndian>(export_size)?;
                stream.write_u16::<BigEndian>(flags)?;

                // Send NBD_REP_ACK
                stream.write_u64::<BigEndian>(0x3e889045565a9)?;
                stream.write_u32::<BigEndian>(opt)?;
                stream.write_u32::<BigEndian>(NBD_REP_ACK)?;
                stream.write_u32::<BigEndian>(0)?; // length 0

                info!("Sent NBD_OPT_GO ACK with export size {}", export_size);
                break; // Handshake complete
            }
            NBD_OPT_EXPORT_NAME => {
                let mut export_name = vec![0u8; opt_len as usize];
                stream.read_exact(&mut export_name)?;
                info!("Client sent NBD_OPT_EXPORT_NAME (legacy): '{}'", String::from_utf8_lossy(&export_name));

                stream.write_u64::<BigEndian>(export_size)?;
                stream.write_u16::<BigEndian>(flags)?;
                
                if !no_zeroes {
                    stream.write_all(&[0u8; 124])?;
                }
                
                break;
            }
            NBD_OPT_ABORT => {
                info!("Client requested abort");
                stream.write_u64::<BigEndian>(0x3e889045565a9)?;
                stream.write_u32::<BigEndian>(opt)?;
                stream.write_u32::<BigEndian>(NBD_REP_ACK)?;
                stream.write_u32::<BigEndian>(0)?;
                return Err("Client aborted connection".into());
            }
            _ => {
                // Read and discard option data
                if opt_len > 0 {
                    let mut discard = vec![0u8; opt_len as usize];
                    stream.read_exact(&mut discard)?;
                }

                // Send ERR_UNSUP
                stream.write_u64::<BigEndian>(0x3e889045565a9)?;
                stream.write_u32::<BigEndian>(opt)?;
                stream.write_u32::<BigEndian>(NBD_REP_ERR_UNSUP)?;
                stream.write_u32::<BigEndian>(0)?;
                info!("Rejected unsupported option NBD_OPT_{}", opt);
            }
        }
    }

    info!("NBD handshake complete");
    Ok(())
}
"""

content = re.sub(r'fn nbd_handshake<S: Read \+ Write>.*?Ok\(\)\)\n\}', handshake_code, content, flags=re.DOTALL)
with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
    f.write(content)
