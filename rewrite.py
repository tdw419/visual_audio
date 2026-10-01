with open("systems/geos_pixel_nbd/src/main.rs", "r") as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if line.startswith("fn nbd_handshake<S: Read + Write>"):
        start_idx = i
    if start_idx != -1 and line.startswith("// NBD Transmission Phase"):
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    new_lines = lines[:start_idx]
    new_lines.append("""fn nbd_handshake<S: std::io::Read + std::io::Write>(
    mut stream: S,
    export_size: u64,
    flags: u16,
) -> Result<(), Box<dyn std::error::Error>> {
    log::info!("Starting raw NBD handshake");

    stream.write_u64::<byteorder::BigEndian>(NBD_MAGIC)?;
    stream.write_u64::<byteorder::BigEndian>(IHAVEOPT)?;

    let handshake_flags: u16 = (1 << 0) | (1 << 1); // FIXED_NEWSTYLE | NO_ZEROES
    stream.write_u16::<byteorder::BigEndian>(handshake_flags)?;

    let client_flags = stream.read_u32::<byteorder::BigEndian>()?;
    log::info!("Client flags: 0x{:x}", client_flags);
    
    let no_zeroes = (client_flags & (1 << 1)) != 0;

    loop {
        let magic = stream.read_u64::<byteorder::BigEndian>()?;
        if magic != 0x49484156454F5054 {
            return Err(format!("Invalid option magic: 0x{:x}", magic).into());
        }

        let opt = stream.read_u32::<byteorder::BigEndian>()?;
        let opt_len = stream.read_u32::<byteorder::BigEndian>()?;

        log::info!("Received NBD_OPT_{} (length {})", opt, opt_len);

        match opt {
            7 => { // NBD_OPT_GO
                let mut name_buf = vec![0u8; opt_len as usize];
                stream.read_exact(&mut name_buf)?;
                let name = String::from_utf8_lossy(&name_buf).trim_end_matches('\\0').to_string();
                log::info!("Client requested export via GO: '{}'", name);

                stream.write_u64::<byteorder::BigEndian>(0x3e889045565a9)?;
                stream.write_u32::<byteorder::BigEndian>(opt)?;
                stream.write_u32::<byteorder::BigEndian>(3)?; // NBD_REP_INFO
                stream.write_u32::<byteorder::BigEndian>(12)?; 
                stream.write_u16::<byteorder::BigEndian>(0)?; // NBD_INFO_EXPORT
                stream.write_u64::<byteorder::BigEndian>(export_size)?;
                stream.write_u16::<byteorder::BigEndian>(flags)?;

                stream.write_u64::<byteorder::BigEndian>(0x3e889045565a9)?;
                stream.write_u32::<byteorder::BigEndian>(opt)?;
                stream.write_u32::<byteorder::BigEndian>(1)?; // NBD_REP_ACK
                stream.write_u32::<byteorder::BigEndian>(0)?; 

                log::info!("Sent NBD_OPT_GO ACK with export size {}", export_size);
                break;
            }
            1 => { // NBD_OPT_EXPORT_NAME
                let mut export_name = vec![0u8; opt_len as usize];
                stream.read_exact(&mut export_name)?;
                log::info!("Client sent NBD_OPT_EXPORT_NAME (legacy): '{}'", String::from_utf8_lossy(&export_name));

                stream.write_u64::<byteorder::BigEndian>(export_size)?;
                stream.write_u16::<byteorder::BigEndian>(flags)?;
                
                if !no_zeroes {
                    stream.write_all(&[0u8; 124])?;
                }
                
                log::info!("Sent NBD_OPT_EXPORT_NAME response with export size {}", export_size);
                break;
            }
            2 => { // NBD_OPT_ABORT
                stream.write_u64::<byteorder::BigEndian>(0x3e889045565a9)?;
                stream.write_u32::<byteorder::BigEndian>(opt)?;
                stream.write_u32::<byteorder::BigEndian>(1)?; // NBD_REP_ACK
                stream.write_u32::<byteorder::BigEndian>(0)?;
                return Err("Client aborted connection".into());
            }
            _ => {
                if opt_len > 0 {
                    let mut discard = vec![0u8; opt_len as usize];
                    stream.read_exact(&mut discard)?;
                }
                stream.write_u64::<byteorder::BigEndian>(0x3e889045565a9)?;
                stream.write_u32::<byteorder::BigEndian>(opt)?;
                stream.write_u32::<byteorder::BigEndian>(1 | (1 << 31))?; // NBD_REP_ERR_UNSUP
                stream.write_u32::<byteorder::BigEndian>(0)?;
                log::info!("Rejected unsupported option NBD_OPT_{}", opt);
            }
        }
    }

    log::info!("NBD handshake complete");
    Ok(())
}
\n""")
    new_lines.extend(lines[end_idx:])
    
    with open("systems/geos_pixel_nbd/src/main.rs", "w") as f:
        f.writelines(new_lines)
    print("Patched successfully!")
else:
    print(f"Failed to find indices: {start_idx}, {end_idx}")
