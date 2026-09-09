/* kernel.h -- minimal bare-metal shim for linux/kernel.h */
#ifndef _LINUX_KERNEL_H
#define _LINUX_KERNEL_H

#include <stddef.h>

#ifndef NULL
#define NULL ((void *)0)
#endif

#define ARRAY_SIZE(arr) (sizeof(arr) / sizeof((arr)[0]))

#define min(x, y) ((x) < (y) ? (x) : (y))
#define max(x, y) ((x) > (y) ? (x) : (y))

#endif
