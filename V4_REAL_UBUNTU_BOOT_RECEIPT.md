[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@030: virtio_pixel_rs_v4_x86: Linux boot protocol support (x86_64)
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@048: Scanning BlockIO device: block_size=512, total_blocks=309248
[ INFO]: v4_bootloader_x86/src/media.rs@107: Found V4BOOT00 at offset 68157440
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@059: Found V4BOOT00 header, tiles.json at offset 68159888
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@072: === V4 Boot Path (Linux bzImage) ===
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@073: Loading kernel PNG (tile 0)...
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@097: Kernel decoded: 15063432 bytes
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@106: Parsing bzImage...
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@116: bzImage header: version=0x020f, pref_address=0x1000000, payload_offset=0x2cc, handover_offset=0xe46ee0
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@123: Loading initramfs PNG (tile 1)...
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@130: Initramfs decoded: 1111171 bytes
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@170: === Linux Boot Protocol ===
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@205: Loading kernel (full bzImage)...
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@234: Loading initramfs...
[ INFO]: v4_bootloader_x86/src/bootloader_uefi.rs@323: Jumping to Linux kernel...
[    0.000000] Linux version 6.8.0-136-generic (buildd@lcy02-amd64-041) (x86_64-linux-gnu-gcc-13 (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, GNU ld (GNU Binutils for Ubuntu) 2.42) #136-Ubuntu SMP PREEMPT_DYNAMIC Wed Jul  1 21:53:05 UTC 2026 (Ubuntu 6.8.0-136.136-generic 6.8.12)
[    0.000000] Command line: console=ttyS0,115200 earlyprintk=serial,ttyS0,115200 earlycon=uart8250,io,0x3f8 loglevel=7 debug
...
[    0.537398]   with environment:
[    0.537572]     HOME=/
[    0.537704]     TERM=linux
=== V4 Bootloader Initramfs ===
Scanning for block devices...
Available block devices:
brw-------    1 0        0         253,   0 Aug 23 17:44 /dev/vda
brw-------    1 0        0         253,   1 Aug 23 17:44 /dev/vda1
brw-------    1 0        0         253,  14 Aug 23 17:44 /dev/vda14
brw-------    1 0        0         253,  15 Aug 23 17:44 /dev/vda15
brw-------    1 0        0         259,   0 Aug 23 17:44 /dev/vda16
Checking /dev/vda1...
[    2.549226] EXT4-fs (vda1): INFO: recovery required on readonly filesystem
[    2.550181] EXT4-fs (vda1): write access will be enabled during recovery
[    2.651583] EXT4-fs (vda1): recovery complete
[    2.654877] EXT4-fs (vda1): mounted filesystem 27e3fa4b-ecf6-45ef-ab1b-bd2fdd1d86d2 ro with ordered data mode. Quota mode: none.
Mounting /dev/vda1 to /newroot
Switching root...
[    2.709320] systemd[1]: Inserted module 'autofs4'
[    2.723041] systemd[1]: systemd 255.4-1ubuntu8.4 running in system mode (+PAM +AUDIT +SELINUX +APPARMOR +IMA +SMACK +SECCOMP +GCRYPT -GNUTLS +OPENSSL +ACL +BLKID +CURL +ELFUTILS +FIDO2 +IDN2 -IDN +IPTC +KMOD +LIBCRYPTSETUP +LIBFDISK +PCRE2 -PWQUALITY +P11KIT +QRENCODE +TPM2 +BZIP2 +LZ4 +XZ +ZLIB +ZSTD -BPF_FRAMEWORK -XKBCOMMON +UTMP +SYSVINIT default-hierarchy=unified)
[    2.724125] systemd[1]: Detected virtualization kvm.
[    2.724395] systemd[1]: Detected architecture x86-64.
[  OK  ] Created slice system-modprobe.slice - Slice /system/modprobe.
[  OK  ] Created slice system-systemd\x2dfsck.slice - Slice /system/systemd-fsck.
[  OK  ] Created slice user.slice - User and Session Slice.
[  OK  ] Started systemd-ask-password-console.path - Dispatch Password Requests to Console Directory Watch.
[  OK  ] Started systemd-ask-password-wall.path - Forward Password Requests to Wall Directory Watch.
[  OK  ] Reached target cryptsetup.target - Local Encrypted Volumes.
[  OK  ] Reached target paths.target - Path Units.
[  OK  ] Reached target slices.target - Slice Units.
[  OK  ] Listening on dbus.socket - D-Bus System Message Bus Socket.
[  OK  ] Listening on iscsid.socket - Open-iSCSI iscsid Socket.
         Starting lxd-installer.socket - Helper to install lxd snap on demand...
         Starting snapd.socket - Socket activation for snappy daemon...
[  OK  ] Listening on ssh.socket - OpenBSD Secure Shell server socket.
[  OK  ] Listening on uuidd.socket - UUID daemon activation socket.
[  OK  ] Listening on lxd-installer.socket - Helper to install lxd snap on demand.
[  OK  ] Listening on snapd.socket - Socket activation for snappy daemon.
[  OK  ] Reached target sockets.target - Socket Units.
...
[  OK  ] Started dbus.service - D-Bus System Message Bus.
[  OK  ] Finished dpkg-db-backup.service - Daily dpkg database backup service.
[  OK  ] Finished e2scrub_reap.service - Remove Stale Online ext4 Metadata Check Snapshots.
[  OK  ] Finished sysstat.service - Resets System Activity Logs.
[  OK  ] Started systemd-logind.service - User Login Management.
[  OK  ] Started unattended-upgrades.service - Unattended Upgrades Shutdown.
[  OK  ] Finished logrotate.service - Rotate log files.
[  OK  ] Finished grub-common.service - Record successful boot for GRUB.
         Starting grub-initrd-fallback.service - GRUB failed boot detection...
[  OK  ] Started polkit.service - Authorization Manager.
         Starting ModemManager.service - Modem Manager...
[  OK  ] Started udisks2.service - Disk Manager.
[  OK  ] Started rsyslog.service - System Logging Service.
