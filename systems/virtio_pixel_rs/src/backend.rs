use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::os::unix::io::{AsRawFd, FromRawFd};
use std::collections::HashMap;

use anyhow::Result;
use log::{error, info, warn};
use nix::sys::socket::{recvmsg, ControlMessageOwned, MsgFlags};
use nix::unistd::{dup, write};
use std::os::fd::OwnedFd;

use super::SpatialMkvExtractor;

/// QEMU memory region descriptor from SET_MEM_TABLE
#[derive(Debug, Clone)]
pub struct VhostUserMemoryRegion {
    pub guest_phys_addr: u64,
    pub memory_size: u64,
    pub userspace_addr: u64,
    pub mmap_offset: u64,
}

/// Mapped QEMU memory region (mutable)
#[derive(Debug)]
pub struct MemoryRegion {
    pub region: VhostUserMemoryRegion,
    pub mmap: memmap2::MmapMut,
    pub guest_phys_base: u64,
    pub size: u64,
}

/// Guest memory with GPA translation
#[derive(Debug)]
pub struct GuestMemory {
    regions: Vec<MemoryRegion>,
    // Migration dirty-page log (VHOST_USER_PROTOCOL_F_LOG_SHMFD): a bitmap,
    // one bit per 4KB guest page across the whole guest address space,
    // shared with QEMU via an mmap'd fd from SET_LOG_BASE. Only touched
    // when logging is actually negotiated (VHOST_F_LOG_ALL in SET_FEATURES) -
    // marking dirty pages here is what lets QEMU migrate/snapshot a VM with
    // this vhost-user device attached at all; without it QEMU refuses any
    // migration outright ("Migration disabled: ... lacks ... LOG_SHMFD").
    log_mmap: Option<memmap2::MmapMut>,
    log_enabled: bool,
}

const VHOST_LOG_PAGE: u64 = 4096;

/// VirtIO virtqueue state
#[derive(Debug)]
pub struct VirtQueue {
    pub num: u32,            // queue size
    pub desc: u64,           // descriptor table guest physical address
    pub avail: u64,          // available ring guest physical address
    pub used: u64,           // used ring guest physical address
    pub ready: bool,         // queue is ready to process
    pub last_avail_idx: u16, // last processed available index
    pub last_used_idx: u16,  // last used index written
    pub avail_addr: u64,     // Full avail ring GPA (for idx access)
    pub call_fd: Option<OwnedFd>, // eventfd for signaling QEMU on completion
}

impl Default for VirtQueue {
    fn default() -> Self {
        Self {
            num: 0,
            desc: 0,
            avail: 0,
            used: 0,
            ready: false,
            last_avail_idx: 0,
            last_used_idx: 0,
            avail_addr: 0,
            call_fd: None,
        }
    }
}

/// VirtIO descriptor (16 bytes)
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct VirtqDesc {
    pub addr: u64,   // Guest physical address of buffer
    pub len: u32,    // Length of buffer
    pub flags: u16,  // VRING_DESC_F_NEXT, VRING_DESC_F_WRITE, etc.
    pub next: u16,   // Next descriptor index if VRING_DESC_F_NEXT
}

// Descriptor flags
pub const VRING_DESC_F_NEXT: u16 = 1;
pub const VRING_DESC_F_WRITE: u16 = 2;
pub const VRING_DESC_F_INDIRECT: u16 = 4;

/// VirtIO available ring (minimum layout)
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct VirtqAvail {
    pub flags: u16,
    pub idx: u16,  // Guest writes this when adding new descriptors
    // ring[]: [u16; N]  // Starts at offset 4
    // used_event: u16   // Only if VIRTIO_F_EVENT_IDX
}

/// VirtIO used element (8 bytes)
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct VirtqUsedElem {
    pub id: u32,   // Descriptor head index
    pub len: u32,  // Bytes written by device
}

/// VirtIO used ring
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct VirtqUsed {
    pub flags: u16,
    pub idx: u16,  // Device writes this when completing requests
    // ring[]: [VirtqUsedElem; N]  // Starts at offset 4
    // avail_event: u16   // Only if VIRTIO_F_EVENT_IDX
}

/// VirtIO block request header (16 bytes)
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct VirtioBlkReq {
    pub r#type: u32,  // VIRTIO_BLK_T_IN=0 (read), VIRTIO_BLK_T_OUT=1 (write)
    pub ioprio: u32,  // I/O priority (unused)
    pub sector: u64,  // Sector number on disk
}

// Block request types
pub const VIRTIO_BLK_T_IN: u32 = 0;
pub const VIRTIO_BLK_T_OUT: u32 = 1;
pub const VIRTIO_BLK_T_FLUSH: u32 = 4;

// Block status codes
pub const VIRTIO_BLK_S_OK: u8 = 0;
pub const VIRTIO_BLK_S_IOERR: u8 = 1;
pub const VIRTIO_BLK_S_UNSUPP: u8 = 2;

impl GuestMemory {
    pub fn new() -> Self {
        Self {
            regions: Vec::new(),
            log_mmap: None,
            log_enabled: false,
        }
    }

    pub fn set_log_base(&mut self, mmap: memmap2::MmapMut) {
        info!("Dirty-page log region mapped ({} bytes)", mmap.len());
        self.log_mmap = Some(mmap);
    }

    pub fn set_logging_enabled(&mut self, enabled: bool) {
        self.log_enabled = enabled;
    }

    /// Mark the guest pages covering [gpa, gpa+len) dirty in the migration
    /// log, if a log region is mapped and logging is currently negotiated.
    fn mark_dirty(&mut self, gpa: u64, len: usize) {
        if !self.log_enabled {
            return;
        }
        let Some(log) = self.log_mmap.as_mut() else { return };

        let start_page = gpa / VHOST_LOG_PAGE;
        let end_page = (gpa + len as u64 - 1) / VHOST_LOG_PAGE;
        for page in start_page..=end_page {
            let byte_idx = (page / 8) as usize;
            let bit = (page % 8) as u8;
            if byte_idx < log.len() {
                log[byte_idx] |= 1 << bit;
            }
        }
    }

    pub fn add_region(&mut self, region: VhostUserMemoryRegion, mmap: memmap2::MmapMut) {
        let guest_phys_base = region.guest_phys_addr;
        let size = region.memory_size;
        info!(
            "Added memory region: GPA 0x{:x} size {} MB",
            guest_phys_base,
            size / (1024 * 1024)
        );
        self.regions.push(MemoryRegion {
            region,
            mmap,
            guest_phys_base,
            size,
        });
    }

    /// Translate guest physical address to host memory offset
    pub fn translate(&self, gpa: u64) -> Option<(usize, usize)> {
        for mr in &self.regions {
            let offset = gpa.wrapping_sub(mr.guest_phys_base);
            if offset < mr.size {
                return Some((mr.guest_phys_base as usize, offset as usize));
            }
        }
        None
    }

    /// Translate userspace address (UVA from QEMU) to host memory offset
    pub fn translate_user(&self, uva: u64) -> Option<(usize, usize)> {
        for mr in &self.regions {
            let base = mr.region.userspace_addr;
            let offset = uva.wrapping_sub(base);
            if offset < mr.size {
                return Some((mr.guest_phys_base as usize, offset as usize));
            }
        }
        None
    }

    /// Read from guest physical address
    pub fn read(&self, gpa: u64, len: usize) -> Result<Vec<u8>> {
        if let Some((base, offset)) = self.translate(gpa) {
            for mr in &self.regions {
                if mr.guest_phys_base as usize == base {
                    let end = offset + len;
                    if end <= mr.mmap.len() {
                        return Ok(mr.mmap[offset..end].to_vec());
                    }
                }
            }
        }
        Err(anyhow::anyhow!("GPA 0x{:x} out of range", gpa))
    }

    /// Write to guest physical address
    pub fn write(&mut self, gpa: u64, data: &[u8]) -> Result<()> {
        if let Some((base, offset)) = self.translate(gpa) {
            for mr in &mut self.regions {
                if mr.guest_phys_base as usize == base {
                    let end = offset + data.len();
                    if end <= mr.mmap.len() {
                        mr.mmap[offset..end].copy_from_slice(data);
                        self.mark_dirty(gpa, data.len());
                        return Ok(());
                    }
                }
            }
        }
        Err(anyhow::anyhow!("GPA 0x{:x} out of range (write)", gpa))
    }

    /// Read from userspace virtual address
    pub fn read_user(&self, uva: u64, len: usize) -> Result<Vec<u8>> {
        if let Some((base, offset)) = self.translate_user(uva) {
            for mr in &self.regions {
                if mr.guest_phys_base as usize == base {
                    let end = offset + len;
                    if end <= mr.mmap.len() {
                        return Ok(mr.mmap[offset..end].to_vec());
                    }
                }
            }
        }
        Err(anyhow::anyhow!("UVA 0x{:x} out of range", uva))
    }

    /// Write to userspace virtual address
    pub fn write_user(&mut self, uva: u64, data: &[u8]) -> Result<()> {
        if let Some((base, offset)) = self.translate_user(uva) {
            for mr in &mut self.regions {
                if mr.guest_phys_base as usize == base {
                    let end = offset + data.len();
                    if end <= mr.mmap.len() {
                        mr.mmap[offset..end].copy_from_slice(data);
                        self.mark_dirty(base as u64 + offset as u64, data.len());
                        return Ok(());
                    }
                }
            }
        }
        Err(anyhow::anyhow!("UVA 0x{:x} out of range (write)", uva))
    }
}

/// Simple vhost-user-blk server that handles the protocol manually
pub struct VirtioPixelServer {
    extractor: Arc<Mutex<SpatialMkvExtractor>>,
    socket_path: PathBuf,
    guest_memory: GuestMemory,
    queues: Vec<VirtQueue>,
    running: bool,

    // WGPU acceleration (Phase 2-4)
    // TODO: Initialize WGPU device and HilbertDecoder
    texture_cache: HashMap<usize, ()>,  // Placeholder for texture cache
}

impl VirtioPixelServer {
    pub fn new(extractor: Arc<Mutex<SpatialMkvExtractor>>, socket_path: PathBuf) -> Self {
        Self {
            extractor,
            socket_path,
            guest_memory: GuestMemory::new(),
            queues: Vec::new(),
            running: false,
            // Phase 2-4: WGPU fields initialized in run()
            texture_cache: HashMap::new(),
        }
    }

    pub fn run(&mut self) -> Result<()> {
        // Remove old socket if exists
        if self.socket_path.exists() {
            std::fs::remove_file(&self.socket_path)?;
        }

        // Create Unix domain socket
        let listener = std::os::unix::net::UnixListener::bind(&self.socket_path)?;
        info!("Listening on {}", self.socket_path.display());

        self.running = true;

        loop {
            // Accept QEMU connection
            let (mut stream, _addr) = listener.accept()?;
            // Set non-blocking so we can poll virtqueues between protocol messages
            stream.set_nonblocking(true)?;
            info!("QEMU connected!");

            // Reset state for new connection
            // Clear guest_memory (SET_MEM_TABLE must be resent)
            // Clear queue FDs (will be resent) but preserve queue metadata for restore operations
            self.guest_memory = GuestMemory::new();
            for q in &mut self.queues {
                q.call_fd = None;
            }
            info!("Connection state reset (guest_memory cleared, FDs cleared, queue metadata preserved)");

            // Handle vhost-user protocol messages
            loop {
                if let Err(e) = self.handle_message(&mut stream) {
                    if let Some(nix_err) = e.downcast_ref::<nix::errno::Errno>() {
                        if *nix_err == nix::errno::Errno::EAGAIN
                            || *nix_err == nix::errno::Errno::EWOULDBLOCK
                        {
                            // Timeout! Poll virtqueues.
                            for i in 0..self.queues.len() {
                                let _ = self.poll_virtqueue(i);
                            }
                            continue;
                        }
                    }

                    // For io::Error (e.g. from stream.read_exact)
                    if let Some(io_err) = e.downcast_ref::<std::io::Error>() {
                        if io_err.kind() == std::io::ErrorKind::WouldBlock
                            || io_err.kind() == std::io::ErrorKind::TimedOut
                        {
                            for i in 0..self.queues.len() {
                                let _ = self.poll_virtqueue(i);
                            }
                            continue;
                        }
                    }

                    error!("Error handling message: {:?}", e);
                    break; // Break inner loop, will accept new connection
                }
            } // End inner loop

            info!("Connection closed, accepting new connections...");
        } // End outer loop

        info!("Backend stopped");
        Ok(())
    }

        fn handle_message(&mut self, stream: &mut std::os::unix::net::UnixStream) -> Result<()> {
        let mut hdr_buf = [0u8; 12];
        let mut iov = [std::io::IoSliceMut::new(&mut hdr_buf)];
        let cmsg_buf_size = 16 + (8 * 4);
        let mut cmsg_buf = vec![0u8; cmsg_buf_size];

        use nix::sys::socket::{recvmsg, ControlMessageOwned, MsgFlags};
        use std::os::unix::io::AsRawFd;

        let mut recv_fds = Vec::new();
        let bytes_read = {
            let msg: nix::sys::socket::RecvMsg<nix::sys::socket::UnixAddr> = recvmsg(
                stream.as_raw_fd(),
                &mut iov,
                Some(&mut cmsg_buf),
                MsgFlags::empty(),
            )?;
            for cmsg in msg.cmsgs() {
                if let ControlMessageOwned::ScmRights(scn_fds) = cmsg {
                    recv_fds.extend(scn_fds);
                }
            }
            msg.bytes
        };

        if bytes_read == 0 {
            return Err(anyhow::anyhow!("Connection closed by peer"));
        }

        let request = u32::from_le_bytes([hdr_buf[0], hdr_buf[1], hdr_buf[2], hdr_buf[3]]);
        let flags = u32::from_le_bytes([hdr_buf[4], hdr_buf[5], hdr_buf[6], hdr_buf[7]]);
        let size = u32::from_le_bytes([hdr_buf[8], hdr_buf[9], hdr_buf[10], hdr_buf[11]]) as usize;

        let mut payload = vec![0u8; size];
        if size > 0 {
            use std::io::Read;
            stream.read_exact(&mut payload)?;
        }

        log::info!("VhostUser request={} flags=0x{:x} size={}", request, flags, size);

        let (mut reply_payload, fds_to_send) = match request {
            1 => (self.handle_get_features(&payload)?, vec![]),
            2 => (self.handle_set_features(&payload)?, vec![]),
            3 => (self.handle_set_owner(&payload)?, vec![]),
            4 => (self.handle_reset_owner(&payload)?, vec![]),
            5 => self.handle_set_mem_table(&payload, &recv_fds)?,
            6 => self.handle_set_log_base(&payload, &recv_fds)?,
            8 => (self.handle_set_vring_num(&payload)?, vec![]),
            9 => (self.handle_set_vring_addr(&payload)?, vec![]),
            10 => (self.handle_set_vring_base(&payload)?, vec![]),
            11 => (self.handle_get_vring_base(&payload)?, vec![]),
            12 => (self.handle_set_vring_kick(&payload)?, vec![]),
            13 => self.handle_set_vring_call(&payload, &recv_fds)?,
            14 => (self.handle_set_vring_err(&payload)?, vec![]),
            15 => (self.handle_get_protocol_features(&payload)?, vec![]),
            16 => (self.handle_set_protocol_features(&payload)?, vec![]),
            17 => (self.handle_get_queue_num(&payload)?, vec![]),
            18 => (self.handle_set_vring_enable(&payload)?, vec![]),
            24 => {
                let capacity = { self.extractor.lock().unwrap().decoded_size / 512 };
                let config_space = capacity.to_le_bytes(); // 8 bytes

                let mut reply = payload.to_vec(); // clone request payload which has offset/size/flags

                let config_offset = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]) as usize;
                let config_size = u32::from_le_bytes([payload[4], payload[5], payload[6], payload[7]]) as usize;

                for i in 0..config_size {
                    if config_offset + i < config_space.len() {
                        if 12 + i < reply.len() {
                            reply[12 + i] = config_space[config_offset + i];
                        }
                    }
                }
                (reply, vec![])
            },
            _ => {
                log::warn!("Unsupported message type: {}", request);
                (vec![], vec![])
            }
        };

        // Only close received FDs that were NOT returned by the handler
        // (handlers may duplicate FDs they want to keep, like callfds)
        let fds_to_keep: std::collections::HashSet<std::os::fd::RawFd> = fds_to_send.iter().copied().collect();
        for fd in recv_fds {
            if !fds_to_keep.contains(&fd) {
                let _ = nix::unistd::close(fd);
            }
        }

        // QEMU expects reply if NEED_REPLY flag is set or for GET requests
        // VHOST_USER_NEED_REPLY_MASK is 0x8
        let need_reply = (flags & 0x8) != 0 || request == 1 || request == 6 || request == 11 || request == 15 || request == 17 || request == 24;

        if need_reply {
            let mut reply_header = [0u8; 12];
            reply_header[0..4].copy_from_slice(&request.to_le_bytes());
            let reply_flags: u32 = 0x5; // REPLY | VERSION 1
            reply_header[4..8].copy_from_slice(&reply_flags.to_le_bytes());
            
            let final_payload = if (flags & 0x8) != 0 && reply_payload.is_empty() {
                vec![0u8; 8]
            } else {
                reply_payload
            };

            let reply_size = final_payload.len() as u32;
            reply_header[8..12].copy_from_slice(&reply_size.to_le_bytes());

            use std::io::Write;
            stream.write_all(&reply_header)?;
            if !final_payload.is_empty() {
                stream.write_all(&final_payload)?;
            }
        }

        Ok(())
    }
    fn handle_set_owner(&self, _payload: &[u8]) -> Result<Vec<u8>> {
        Ok(vec![])
    }

    fn handle_reset_owner(&self, _payload: &[u8]) -> Result<Vec<u8>> {
        Ok(vec![])
    }

    fn handle_get_features(&self, _payload: &[u8]) -> Result<Vec<u8>> {
        // Writes land in an in-memory sector overlay (see SpatialMkvExtractor::write),
        // not VIRTIO_BLK_F_RO(5) anymore, so the guest can mount rw.
        // VHOST_F_LOG_ALL (26) lets QEMU negotiate migration dirty-page
        // logging - without advertising it, QEMU refuses migration/snapshot
        // outright for any VM with this device attached.
        //
        // FIX: QEMU 8.2.2 REQUIRES VHOST_USER_F_PROTOCOL_FEATURES (bit 30)
        // to be set, otherwise it never calls GET_PROTOCOL_FEATURES and
        // the negotiation stalls before SET_MEM_TABLE and GET_CONFIG.
        //
        // Response format: 0x4000000410000000
        // - Upper bits (32+): VirtIO device features
        //   - Bit 32: VIRTIO_F_VERSION_1
        // - Lower bits (0-31): vhost features
        //   - Bit 26: VHOST_F_LOG_ALL (migration support)
        //   - Bit 30: VHOST_USER_F_PROTOCOL_FEATURES (required by QEMU 8.2.2)
        let features = (1u64 << 26) | (1u64 << 30) | (1u64 << 32);
        info!("GET_FEATURES returning: 0x{:016x}", features);
        info!("  - VIRTIO_F_VERSION_1 (bit 32) enabled");
        info!("  - VHOST_F_LOG_ALL (bit 26) for migration support");
        info!("  - VHOST_USER_F_PROTOCOL_FEATURES (bit 30) - REQUIRED for QEMU 8.2.2");
        Ok(features.to_le_bytes().to_vec())
    }

    fn handle_set_features(&mut self, payload: &[u8]) -> Result<Vec<u8>> {
        if payload.len() >= 8 {
            let features = u64::from_le_bytes(payload[0..8].try_into().unwrap());
            let log_all = (features & (1 << 26)) != 0;
            self.guest_memory.set_logging_enabled(log_all);
            if log_all {
                info!("Migration dirty-page logging enabled (VHOST_F_LOG_ALL negotiated)");
            }
        }
        Ok(vec![])
    }

    /// VHOST_USER_SET_LOG_BASE (6): QEMU sends the dirty-page log's mmap
    /// size/offset in the payload and the shared fd via ancillary data.
    /// Without handling this, QEMU can't complete migration even after we
    /// advertise VHOST_USER_PROTOCOL_F_LOG_SHMFD - it still needs somewhere
    /// to actually receive the log.
    fn handle_set_log_base(&mut self, payload: &[u8], recv_fds: &[std::os::fd::RawFd]) -> Result<(Vec<u8>, Vec<std::os::fd::RawFd>)> {
        if payload.len() < 16 || recv_fds.is_empty() {
            warn!("SET_LOG_BASE: missing payload or fd");
            return Ok((vec![0u8; 8], vec![]));
        }

        let mmap_size = u64::from_le_bytes(payload[0..8].try_into().unwrap());
        let mmap_offset = u64::from_le_bytes(payload[8..16].try_into().unwrap());

        // dup() so the mmap owns its own fd - the generic dispatch loop
        // closes every fd in recv_fds after the handler returns regardless
        // of which handler ran, so holding onto the original would double-close.
        let owned_fd = unsafe { OwnedFd::from_raw_fd(dup(recv_fds[0])?) };
        let mmap = unsafe {
            memmap2::MmapOptions::new()
                .len(mmap_size as usize)
                .offset(mmap_offset)
                .map_mut(&owned_fd)?
        };
        self.guest_memory.set_log_base(mmap);
        Ok((vec![0u8; 8], vec![]))
    }

    fn handle_set_vring_num(&mut self, payload: &[u8]) -> Result<Vec<u8>> {
        // ... (keep logic, but replace Ok at end)
        let idx = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]) as usize;
        let num = u32::from_le_bytes([payload[4], payload[5], payload[6], payload[7]]) as usize;
        
        while self.queues.len() <= idx {
            self.queues.push(VirtQueue::default());
        }
        self.queues[idx].num = num as u32;
        
        Ok(vec![])
    }

    fn handle_set_vring_addr(&mut self, payload: &[u8]) -> Result<Vec<u8>> {
        let idx = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]);
        let flags = u32::from_le_bytes([payload[4], payload[5], payload[6], payload[7]]);
        let desc = u64::from_le_bytes([
            payload[8],
            payload[9],
            payload[10],
            payload[11],
            payload[12],
            payload[13],
            payload[14],
            payload[15],
        ]);
        let avail = u64::from_le_bytes([
            payload[24],
            payload[25],
            payload[26],
            payload[27],
            payload[28],
            payload[29],
            payload[30],
            payload[31],
        ]);
        let log_addr = u64::from_le_bytes([
            payload[32],
            payload[33],
            payload[34],
            payload[35],
            payload[36],
            payload[37],
            payload[38],
            payload[39],
        ]);
        let used = u64::from_le_bytes([
            payload[16],
            payload[17],
            payload[18],
            payload[19],
            payload[20],
            payload[21],
            payload[22],
            payload[23],
        ]);

        info!(
            "SET_VRING_ADDR: index={} flags={} desc=0x{:x} avail=0x{:x} used=0x{:x}",
            idx, flags, desc, avail, used
        );

        if self.queues.len() > idx as usize {
            self.queues[idx as usize].desc = desc;
            self.queues[idx as usize].avail = avail;
            self.queues[idx as usize].used = used;
        }

        Ok(vec![])
    }

    fn handle_set_vring_base(&mut self, payload: &[u8]) -> Result<Vec<u8>> {
        let idx = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]);
        let base = u32::from_le_bytes([
            payload[4],
            payload[5],
            payload[6],
            payload[7],
        ]);

        info!("SET_VRING_BASE: index={} base={}", idx, base);

        if self.queues.len() > idx as usize {
            // base initializes both avail and used tracking - on a
            // migration resume the guest's own driver state (part of the
            // migrated RAM) already expects the used ring to continue from
            // this same index. Only setting last_avail_idx left used_idx at
            // its fresh-process default of 0, so post-resume completions
            // landed at the wrong used-ring slots ("req.0:id N is not a
            // head!" / I/O errors on the guest side).
            self.queues[idx as usize].last_avail_idx = base as u16;
            self.queues[idx as usize].last_used_idx = base as u16;
        }

        Ok(vec![])
    }

    fn handle_get_vring_base(&self, payload: &[u8]) -> Result<Vec<u8>> {
        // Was hardcoded to always report last_avail_idx=0 regardless of the
        // queue's real position - harmless for normal operation (nothing
        // reads this reply outside migration) but it silently corrupted
        // migration/snapshot: QEMU saves this value as the guest's true
        // ring position, so resuming from a snapshot replayed every queue
        // from index 0 while the guest kernel's own idea of the ring had
        // already advanced, producing "Guest index inconsistent with Host
        // index" and refusing to resume.
        let idx = if payload.len() >= 4 {
            u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]) as usize
        } else {
            0
        };
        let last_avail_idx = self.queues.get(idx).map(|q| q.last_avail_idx).unwrap_or(0);
        info!("GET_VRING_BASE: index={} last_avail_idx={}", idx, last_avail_idx);

        let mut reply = [0u8; 8];
        reply[0..4].copy_from_slice(&(idx as u32).to_le_bytes());
        reply[4..8].copy_from_slice(&(last_avail_idx as u32).to_le_bytes());
        Ok(reply.to_vec())
    }

    fn handle_set_vring_kick(&mut self, _payload: &[u8]) -> Result<Vec<u8>> {
        info!("SET_VRING_KICK");
        // Poll virtqueue 0 for new requests
        if let Err(e) = self.poll_virtqueue(0) {
            error!("Error polling virtqueue: {}", e);
        }
        Ok(vec![])
    }

    fn handle_set_vring_call(&mut self, payload: &[u8], fds: &[std::os::fd::RawFd]) -> Result<(Vec<u8>, Vec<std::os::fd::RawFd>)> {
        let idx = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]);
        let flags = u32::from_le_bytes([payload[4], payload[5], payload[6], payload[7]]);

        info!(
            "SET_VRING_CALL: index={} flags={} fds={}",
            idx,
            flags,
            fds.len()
        );

        // Store the callfd (eventfd for signaling QEMU)
        if !fds.is_empty() {
            let fd = fds[0];
            info!("  Storing callfd={} for queue {}", fd, idx);

            while self.queues.len() <= idx as usize {
                self.queues.push(VirtQueue::default());
            }
            // dup() so we own a copy - the original stays in recv_fds
            // and gets preserved by the main loop since we return it
            let owned_fd = unsafe { OwnedFd::from_raw_fd(dup(fd)?) };
            self.queues[idx as usize].call_fd = Some(owned_fd);

            // Return the original fd so main loop won't close it
            Ok((vec![], fds.to_vec()))
        } else {
            warn!("  No FD passed in SET_VRING_CALL");
            Ok((vec![], vec![]))
        }
    }

    fn handle_set_vring_err(&self, _payload: &[u8]) -> Result<Vec<u8>> {
        info!("SET_VRING_ERR");
        Ok(vec![])
    }

    fn handle_set_mem_table(
        &mut self,
        payload: &[u8],
        fds: &[std::os::fd::RawFd],
    ) -> Result<(Vec<u8>, Vec<std::os::fd::RawFd>)> {
        let num_regions = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]);
        let padding = u32::from_le_bytes([payload[4], payload[5], payload[6], payload[7]]);

        info!(
            "SET_MEM_TABLE: {} regions (padding={}) fds={}",
            num_regions,
            padding,
            fds.len()
        );

        // Each region is 32 bytes (4x u64)
        let mut regions = Vec::new();
        for i in 0..num_regions as usize {
            let offset = 8 + i * 32;
            let region = VhostUserMemoryRegion {
                guest_phys_addr: u64::from_le_bytes([
                    payload[offset],
                    payload[offset + 1],
                    payload[offset + 2],
                    payload[offset + 3],
                    payload[offset + 4],
                    payload[offset + 5],
                    payload[offset + 6],
                    payload[offset + 7],
                ]),
                memory_size: u64::from_le_bytes([
                    payload[offset + 8],
                    payload[offset + 9],
                    payload[offset + 10],
                    payload[offset + 11],
                    payload[offset + 12],
                    payload[offset + 13],
                    payload[offset + 14],
                    payload[offset + 15],
                ]),
                userspace_addr: u64::from_le_bytes([
                    payload[offset + 16],
                    payload[offset + 17],
                    payload[offset + 18],
                    payload[offset + 19],
                    payload[offset + 20],
                    payload[offset + 21],
                    payload[offset + 22],
                    payload[offset + 23],
                ]),
                mmap_offset: u64::from_le_bytes([
                    payload[offset + 24],
                    payload[offset + 25],
                    payload[offset + 26],
                    payload[offset + 27],
                    payload[offset + 28],
                    payload[offset + 29],
                    payload[offset + 30],
                    payload[offset + 31],
                ]),
            };

            info!(
                "  Region {}: GPA 0x{:x} size {}MB userspace 0x{:x} mmap_offset 0x{:x}",
                i,
                region.guest_phys_addr,
                region.memory_size / (1024 * 1024),
                region.userspace_addr,
                region.mmap_offset
            );

            regions.push(region);
        }

        // Mmap regions using received FDs
        for (i, region) in regions.iter().enumerate() {
            if i < fds.len() {
                let fd = fds[i];
                let mmap_size = region.memory_size as usize;
                let mmap_offset = region.mmap_offset as usize;

                info!(
                    "  Mmaping region {} with fd={} size={}MB offset=0x{:x}",
                    i,
                    fd,
                    mmap_size / (1024 * 1024),
                    mmap_offset
                );

                // Convert raw FD to OwnedFd for safe ownership
                let owned_fd = unsafe { OwnedFd::from_raw_fd(dup(fd)?) };

                // mmap the region with the received FD
                let mmap = unsafe {
                    memmap2::MmapOptions::new()
                        .len(mmap_size)
                        .offset(mmap_offset as u64)
                        .map_mut(&owned_fd)?
                };

                self.guest_memory.add_region(region.clone(), mmap);
            } else {
                warn!(
                    "  Region {} has no associated FD (have {}, need {})",
                    i,
                    fds.len(),
                    regions.len()
                );
            }
        }

        info!(
            "SET_MEM_TABLE: mmap'd {} regions into GuestMemory",
            self.guest_memory.regions.len()
        );

        // Return reply and empty FDs list (we're keeping the mem FDs in the mmap)
        Ok((vec![], vec![]))
    }

    /// Read a VirtIO descriptor from guest memory
    fn read_descriptor(&self, queue_idx: usize, desc_idx: u16) -> Result<VirtqDesc> {
        if queue_idx >= self.queues.len() {
            return Err(anyhow::anyhow!("Invalid queue index {}", queue_idx));
        }

        let queue = &self.queues[queue_idx];
        let desc_uva = queue.desc + (desc_idx as u64) * 16; // VirtqDesc is 16 bytes

        let desc_bytes = self.guest_memory.read_user(desc_uva, 16)?;
        if desc_bytes.len() < 16 {
            return Err(anyhow::anyhow!("Descriptor read truncated at UVA 0x{:x}", desc_uva));
        }

        let addr = u64::from_le_bytes([
            desc_bytes[0],
            desc_bytes[1],
            desc_bytes[2],
            desc_bytes[3],
            desc_bytes[4],
            desc_bytes[5],
            desc_bytes[6],
            desc_bytes[7],
        ]);
        let len = u32::from_le_bytes([
            desc_bytes[8],
            desc_bytes[9],
            desc_bytes[10],
            desc_bytes[11],
        ]);
        let flags = u16::from_le_bytes([
            desc_bytes[12],
            desc_bytes[13],
        ]);
        let next = u16::from_le_bytes([
            desc_bytes[14],
            desc_bytes[15],
        ]);

        Ok(VirtqDesc {
            addr,
            len,
            flags,
            next,
        })
    }

    /// Read available ring idx from guest memory (at avail_gpa + 2)
    fn read_avail_idx(&self, queue_idx: usize) -> Result<u16> {
        if queue_idx >= self.queues.len() {
            return Err(anyhow::anyhow!("Invalid queue index {}", queue_idx));
        }

        let queue = &self.queues[queue_idx];
        let idx_uva = queue.avail + 2; // avail.idx is at offset 2

        let idx_bytes = self.guest_memory.read_user(idx_uva, 2)?;
        if idx_bytes.len() < 2 {
            return Err(anyhow::anyhow!("avail.idx read truncated at UVA 0x{:x}", idx_uva));
        }

        let idx = u16::from_le_bytes([idx_bytes[0], idx_bytes[1]]);
        Ok(idx)
    }

    /// Read descriptor head from avail.ring[]
    fn read_avail_ring_entry(&self, queue_idx: usize, idx: u16) -> Result<u16> {
        if queue_idx >= self.queues.len() {
            return Err(anyhow::anyhow!("Invalid queue index {}", queue_idx));
        }

        let queue = &self.queues[queue_idx];
        let num = queue.num as u16;
        let ring_idx = (idx % num) as usize;
        let ring_uva = queue.avail + 4 + (ring_idx as u64) * 2; // avail.ring starts at offset 4

        let entry_bytes = self.guest_memory.read_user(ring_uva, 2)?;
        if entry_bytes.len() < 2 {
            return Err(anyhow::anyhow!(
                "avail.ring[{}] read truncated at UVA 0x{:x}",
                ring_idx,
                ring_uva
            ));
        }

        let head = u16::from_le_bytes([entry_bytes[0], entry_bytes[1]]);
        Ok(head)
    }

    /// Write used element to guest memory
    fn write_used_elem(&mut self, queue_idx: usize, head: u16, len: u32) -> Result<()> {
        if queue_idx >= self.queues.len() {
            return Err(anyhow::anyhow!("Invalid queue index {}", queue_idx));
        }

        let queue = &mut self.queues[queue_idx];
        let num = queue.num as u16;
        let used_idx = queue.last_used_idx;
        let ring_idx = (used_idx % num) as usize;
        let ring_uva = queue.used + 4 + (ring_idx as u64) * 8; // used.ring starts at offset 4

        // Write VirtqUsedElem (8 bytes)
        let mut elem_bytes = [0u8; 8];
        elem_bytes[0..4].copy_from_slice(&(head as u32).to_le_bytes());
        elem_bytes[4..8].copy_from_slice(&len.to_le_bytes());
        self.guest_memory.write_user(ring_uva, &elem_bytes)?;

        // Update used.idx
        let idx_uva = queue.used + 2;
        let new_idx = used_idx.wrapping_add(1);
        queue.last_used_idx = new_idx;
        let idx_bytes = new_idx.to_le_bytes();
        self.guest_memory.write_user(idx_uva, &idx_bytes)?;

        Ok(())
    }

    /// Poll virtqueue for new requests and process them
    fn poll_virtqueue(&mut self, queue_idx: usize) -> Result<()> {
        // Check queue exists and is ready
        if queue_idx >= self.queues.len() {
            return Ok(()); // Queue not initialized yet
        }
        if !self.queues[queue_idx].ready {
            return Ok(()); // Queue not ready yet
        }

        let avail_idx = self.read_avail_idx(queue_idx)?;
        let last_avail = self.queues[queue_idx].last_avail_idx;

            if avail_idx == last_avail {
            return Ok(()); // No new requests
        }

        let num_new = avail_idx.wrapping_sub(last_avail);
        info!(
            "Queue {} has {} new requests (avail_idx={}, last_avail={})",
            queue_idx, num_new, avail_idx, last_avail
        );

        // Process each new descriptor
        for _ in 0..num_new {
            let req_idx = self.queues[queue_idx].last_avail_idx;
            let head = self.read_avail_ring_entry(queue_idx, req_idx)?;

            info!("Processing request {} with descriptor head {}", req_idx, head);

            // Walk descriptor chain (Header → Data → Status)
            let descriptors = self.walk_descriptor_chain(queue_idx, head)?;

            // Handle VirtIO block request
            self.handle_virtio_block_request(&descriptors)?;
            // Complete request (write used ring)
            self.write_used_elem(queue_idx, head, 0)?;

            // Advance avail_idx
            self.queues[queue_idx].last_avail_idx =
                self.queues[queue_idx].last_avail_idx.wrapping_add(1);
        }

        // Signal QEMU that requests are complete
        self.trigger_callfd(queue_idx)?;

        Ok(())
    }

    /// Walk descriptor chain and return all descriptors in order
    fn walk_descriptor_chain(&self, queue_idx: usize, head: u16) -> Result<Vec<VirtqDesc>> {
        let mut descriptors = Vec::new();
        let mut desc_idx = head;
        let mut seen = std::collections::HashSet::new();

        loop {
            if seen.contains(&desc_idx) {
                return Err(anyhow::anyhow!("Descriptor cycle detected at idx {}", desc_idx));
            }
            seen.insert(desc_idx);

            let desc = self.read_descriptor(queue_idx, desc_idx)?;
            descriptors.push(desc);

            if desc.flags & VRING_DESC_F_NEXT == 0 {
                break;
            }
            desc_idx = desc.next;
        }

        Ok(descriptors)
    }

    /// Signal QEMU that requests are complete via callfd eventfd
    fn trigger_callfd(&mut self, queue_idx: usize) -> Result<()> {
        if queue_idx >= self.queues.len() {
            return Err(anyhow::anyhow!("Invalid queue index {}", queue_idx));
        }

        if let Some(call_fd) = &self.queues[queue_idx].call_fd {
            // Write 1 to eventfd to wake up QEMU
            let val = 1u64.to_ne_bytes();
            if let Err(e) = write(call_fd, &val) {
                error!("Failed to trigger callfd for queue {}: {}", queue_idx, e);
            } else {
                info!("Triggered callfd for queue {} (woke QEMU)", queue_idx);
            }
        } else {
            warn!("No callfd set for queue {}", queue_idx);
        }

        Ok(())
    }

    /// Handle VirtIO block request (Header → Data → Status)
    fn handle_virtio_block_request(&mut self, descriptors: &[VirtqDesc]) -> Result<()> {
        // Expect at least 3 descriptors: Header, Data, Status
        if descriptors.len() < 3 {
            return Err(anyhow::anyhow!(
                "Expected 3+ descriptors, got {}",
                descriptors.len()
            ));
        }

        let header_desc = &descriptors[0];
        let data_desc = &descriptors[1];
        let status_desc = &descriptors[2];

        // Read request header
        let header_bytes = self.guest_memory.read(header_desc.addr, header_desc.len as usize)?;
        if header_bytes.len() < 16 {
            return Err(anyhow::anyhow!("Request header truncated"));
        }

        let req_type = u32::from_le_bytes([
            header_bytes[0],
            header_bytes[1],
            header_bytes[2],
            header_bytes[3],
        ]);
        let sector = u64::from_le_bytes([
            header_bytes[8],
            header_bytes[9],
            header_bytes[10],
            header_bytes[11],
            header_bytes[12],
            header_bytes[13],
            header_bytes[14],
            header_bytes[15],
        ]);

        info!(
            "Block request: type={} sector={} data_len={} status_len={}",
            req_type,
            sector,
            data_desc.len,
            status_desc.len
        );

        // Handle read request (T_IN=0)
        if req_type == VIRTIO_BLK_T_IN {
            // Calculate offset in the 7GB decoded data space
            let offset = sector * 512;

            // Extract Hilbert pixels from SpatialMkvExtractor
            let decoded_data = {
                let mut extractor = self.extractor.lock().unwrap();
                extractor.read(offset, data_desc.len as u64)?
            };

            // Write decoded bytes to data buffer
            self.guest_memory.write(data_desc.addr, &decoded_data)?;
            info!(
                "  Extracted {} Hilbert bytes at offset 0x{:x} (sector {})",
                decoded_data.len(), offset, sector
            );
        } else if req_type == VIRTIO_BLK_T_OUT {
            // Writes land in an in-memory sector overlay, not the source MKV -
            // re-encoding video frames on every write is a much bigger project.
            let offset = sector * 512;
            let write_data = self.guest_memory.read(data_desc.addr, data_desc.len as usize)?;

            let mut extractor = self.extractor.lock().unwrap();
            extractor.write(offset, &write_data)?;
            info!(
                "  Wrote {} bytes to overlay at offset 0x{:x} (sector {})",
                write_data.len(), offset, sector
            );
        }

        // Write status OK
        self.guest_memory.write(status_desc.addr, &[VIRTIO_BLK_S_OK])?;
        info!("  Wrote VIRTIO_BLK_S_OK to status byte");

        Ok(())
    }
    fn handle_get_protocol_features(&self, _payload: &[u8]) -> Result<Vec<u8>> {
        // VHOST_USER_PROTOCOL_F_MQ (0) | VHOST_USER_PROTOCOL_F_LOG_SHMFD (1) |
        // VHOST_USER_PROTOCOL_F_REPLY_ACK (3) | VHOST_USER_PROTOCOL_F_CONFIG (9)
        let features = (1u64 << 0) | (1u64 << 1) | (1u64 << 3) | (1u64 << 9);
        Ok(features.to_le_bytes().to_vec())
    }

    fn handle_get_queue_num(&self, _payload: &[u8]) -> Result<Vec<u8>> {
        let num: u64 = 1;
        Ok(num.to_le_bytes().to_vec())
    }

    fn handle_set_protocol_features(&self, _payload: &[u8]) -> Result<Vec<u8>> {
        Ok(vec![])
    }

    fn handle_set_vring_enable(&mut self, payload: &[u8]) -> Result<Vec<u8>> {
        if payload.len() >= 8 {
            let idx = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]) as usize;
            let enable = u32::from_le_bytes([payload[4], payload[5], payload[6], payload[7]]);
            
            if idx < self.queues.len() {
                self.queues[idx].ready = enable != 0;
                info!("SET_VRING_ENABLE: index={} enable={}", idx, enable);
            }
        }
        Ok(vec![])
    }
}
