/* probe_data.S — embed the real Alpine initrd gzip bytes as a data symbol.
 * Assembled with the probe; linked at 0x80000000 like the other bare-metal tests.
 */
.section .rodata
.align 4
.global initrd_gz_start
initrd_gz_start:
.incbin "initrd.gz.bin"
.global initrd_gz_end
initrd_gz_end:

/* small gzip payload: 342 bytes -> 90,000 bytes of repeated text.
 * Fast inflate workload for quick A/B on the GPU core. */
.align 4
.global small_gz_start
small_gz_start:
.incbin "small.gz.bin"
.global small_gz_end
small_gz_end:

.section .bss
.align 4
.global probe_out_buf
probe_out_buf:
.space 12 * 1024 * 1024   /* decompressed output (expect 11,600,900) */
.global probe_out_buf_end
probe_out_buf_end:

.align 4
.global small_out_buf
small_out_buf:
.space 256 * 1024         /* decompressed small output (expect 90,000) */

.align 12
.global probe_stack_top
.space 8192
probe_stack_top:
