/* zconf.h -- minimal bare-metal shim for kernel zlib (linux/zconf.h) */
#ifndef _ZCONF_H
#define _ZCONF_H

typedef unsigned char  Byte;  /* 8 bits */
typedef unsigned int   uInt;  /* 16 bits or more */
typedef unsigned long  uLong; /* 32 bits or more */
typedef void     *voidp;

#ifndef MAX_WBITS
#define MAX_WBITS 15
#endif
#ifndef DEF_WBITS
#define DEF_WBITS MAX_WBITS
#endif

#endif /* _ZCONF_H */
