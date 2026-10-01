#!/bin/busybox sh
/bin/busybox mkdir -p /proc /sys /dev /newroot
/bin/busybox mount -t proc proc /proc
/bin/busybox mount -t sysfs sysfs /sys
/bin/busybox mount -t devtmpfs devtmpfs /dev
echo "BL002_INITRAMFS_START"
for m in crc64 crc64-rocksoft t10-pi scsi_common scsi_mod libata sd_mod ata_piix ata_generic mbcache ext2; do
  /bin/busybox insmod /lib/modules/$m.ko && echo "BL002_MODULE_OK $m" || echo "BL002_MODULE_FAIL $m"
done
/bin/busybox sleep 1
echo BL002_DEV_LISTING_START
/bin/busybox ls -la /dev
echo BL002_DEV_LISTING_END
if [ ! -e /dev/sda ]; then
  echo BL002_NO_SDA_NODE_MKNOD_FALLBACK
  /bin/busybox mknod /dev/sda b 8 0
fi
/bin/busybox mount -t ext2 -o rw /dev/sda /newroot
if [ $? -eq 0 ]; then echo "BL002_ROOT_MOUNTED"; else echo "BL002_ROOT_MOUNT_FAILED"; /bin/busybox sh; fi
exec /bin/busybox switch_root /newroot /sbin/init
