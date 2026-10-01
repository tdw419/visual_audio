/* zlib.h -- minimal bare-metal shim for kernel zlib (linux/zlib.h)
 * Only the inflate-side API used by lib/zlib_inflate is provided.
 */
#ifndef _ZLIB_H
#define _ZLIB_H

#include "zconf.h"

struct internal_state;

typedef struct z_stream_s {
    const Byte *next_in;   /* next input byte */
    uLong avail_in;        /* number of bytes available at next_in */
    uLong    total_in;     /* total nb of input bytes read so far */

    Byte    *next_out;     /* next output byte should be put there */
    uLong avail_out;       /* remaining free space at next_out */
    uLong    total_out;    /* total nb of bytes output so far */

    char     *msg;         /* last error message, NULL if no error */
    struct internal_state *state; /* not visible by applications */

    void     *workspace;   /* memory allocated for this stream */

    int     data_type;     /* best guess about the data type */
    uLong   adler;         /* adler32 value of the uncompressed data */
    uLong   reserved;
} z_stream;

typedef z_stream *z_streamp;

/* constants */
#define Z_NO_FLUSH      0
#define Z_PARTIAL_FLUSH 1
#define Z_PACKET_FLUSH  2
#define Z_SYNC_FLUSH    3
#define Z_FULL_FLUSH    4
#define Z_FINISH        5
#define Z_BLOCK         6

#define Z_OK            0
#define Z_STREAM_END    1
#define Z_NEED_DICT     2
#define Z_ERRNO        (-1)
#define Z_STREAM_ERROR (-2)
#define Z_DATA_ERROR   (-3)
#define Z_MEM_ERROR    (-4)
#define Z_BUF_ERROR    (-5)
#define Z_VERSION_ERROR (-6)

#define Z_DEFLATED   8

/* inflate-side API used by lib/zlib_inflate */
extern int zlib_inflate_workspacesize(void);
extern int zlib_inflateReset(z_streamp strm);
extern int zlib_inflateInit2(z_streamp strm, int windowBits);
extern int zlib_inflate(z_streamp strm, int flush);
extern int zlib_inflateEnd(z_streamp strm);

#endif /* _ZLIB_H */
