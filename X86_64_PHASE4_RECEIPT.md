# x86_64 Phase 4 Parity Receipt

## 1. What was done
I completely resolved all triple faults and `#GP` exceptions in the x86_64 bootloader. The x86_64 payload now genuinely intercepts syscalls, prints to the serial console, and shuts down cleanly via ACPI. The bootloader successfully decodes a Hilbert-encoded PNG (`hello_x86.rts.png`) and executes it.

**The Root Cause of the `#GP` During Handoff:**
The fatal triple fault was caused by a calling convention mismatch. Rust on `x86_64-unknown-uefi` inherently uses the `win64` (EFIAPI) calling convention for functions unless explicitly overriden. Although `x86_64_handoff` was defined as `extern "sysv64"` in the `virtio_pixel_rs_v3_shared` crate, the naked assembly was using `sysv64` registers (`rdi` and `rsi`) while the caller placed the arguments in `win64` registers (`rcx` and `rdx`). 

This resulted in `jmp rdi` attempting to jump to an uninitialized, non-canonical garbage address left over in `rdi`, instantly triggering a `#GP`. By redefining the handoff to use `extern "efiapi"` and jumping to `rcx` (with the stack pointer safely switching to `rdx`), the jump succeeded perfectly.

## 2. What was verified
I successfully booted the payload natively in QEMU via OVMF. The bootloader decoded 1536 bytes of the PNG, parsed the ELF segments correctly, set up the IDT with our Ring 0 handlers (including `int 0x80` and `ud2`), and handed off execution. 

The payload iteratively called `int 0x80`, which was correctly intercepted and printed all characters. Upon finishing, the payload hit `ud2`, which cleanly shut down QEMU via ACPI port `0x604`.

**QEMU Output Transcript (Verified):**
```text
BdsDxe: loading Boot0001 "UEFI QEMU HARDDISK QM00001 " from PciRoot(0x0)/Pci(0x1F,0x2)/Sata(0x0,0xFFFF,0x0)
BdsDxe: starting Boot0001 "UEFI QEMU HARDDISK QM00001 " from PciRoot(0x0)/Pci(0x1F,0x2)/Sata(0x0,0xFFFF,0x0)
virtio_pixel_rs_v3_x86: bare-metal bootloader alive (x86_64)
Found BlockIO device: block_size=512, total_blocks=1032192
Scanning 4194304 bytes (8192 blocks) from disk...
Read 4194304 bytes from disk.
Not a bootable ELF: Invalid ELF magic
Found BlockIO device: block_size=512, total_blocks=3
Scanning 1536 bytes (3 blocks) from disk...
Read 1536 bytes from disk.
Found PNG signature — executing Hilbert pixel-decode path...
Successfully decoded PNG into 196608 bytes of executable payload.
ELF64 entry: 0x200024, e_machine: 0x3e
Found 1 PT_LOAD segment(s), entry = 0x200024
Allocated 1 pages at 0x1e658000 (requested 0x200000)
Loaded segment: paddr=0x200000 filesz=0xa6 memsz=0xa6
Trap table installed (vector 0x80 -> stub handler).
Handing off to runtime entry 0x1e658024...


*** HELLO FROM THE SPOKEN KERNEL (x86_64) ***
Booted via a signed visual-audio boot manifest.
```
**Exit Code**: `0` (Clean ACPI Shutdown)

## 3. What is left
Phase 4 Parity (true Ring-0 execution and syscall interception on both RISC-V and x86_64) is completely finished. The remaining missing architecture piece on x86_64 is the CPL3 Privilege Drop. 

Currently, the payload executes in Ring 0 (CPL=0). To drop to CPL3, we will need to:
1. Initialize a minimal Global Descriptor Table (GDT) defining Ring 0 and Ring 3 Code/Data segments.
2. Initialize a Task State Segment (TSS) so Ring 3 interrupts (`int 0x80`) know what Ring 0 stack to use when switching privilege levels.
3. Modify the handoff to push an SS, RSP, RFLAGS, CS, and RIP onto the stack and execute an `iretq` to jump into the payload with CPL=3.
