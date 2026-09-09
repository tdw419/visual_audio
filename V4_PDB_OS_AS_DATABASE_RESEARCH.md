# Research: How much of Ubuntu is already a database?

Grounded against the real disk image in this repo:
`ubuntu-24.04-server-cloudimg-amd64.raw` (3.5GB, GPT, ext4 root on partition 1),
inspected read-only via `guestfish` (no mount/root needed — reusable for future PDB
compiler work without touching the live image).

## What's actually there (verified, not assumed)

| Subsystem | Path | Structure | Verified in this image |
|---|---|---|---|
| Package DB | `/var/lib/dpkg/status` | Flat text, RFC822-style stanzas, one per package | 679,862 bytes, one file |
| Package file lists | `/var/lib/dpkg/info/*.list` | One flat file per installed package, newline-delimited paths | Hundreds of `.list` files present (bash, libkrb5-3, libjpeg-turbo8, ...) |
| APT state | `/var/lib/apt/{extended_states,lists,mirrors,periodic}` | Mixed: text + cached index files | Present |
| Users/auth | `/etc/passwd`, `/etc/shadow` | Flat colon-delimited rows, fixed schema | 1667 / 814 bytes |
| System journal | `/var/log/journal/` | Binary structured log (systemd-journald's own binary format, has its own header/hash-table/object layout) | Present, `drwxr-sr-x+` |
| GUI settings (dconf) | `/etc/dconf` | N/A on this image | **Not present** — dconf is desktop-only; this is a server cloud image. Confirmed absent, don't assume it exists on all Ubuntu variants. |
| Filesystem itself | ext4 | inode table + extent B-trees + directory htrees — literally a B-tree DB already | (implicit, whole image) |

## What this means for the schema question

Your instinct was right, but the picture splits into three tiers of "already-a-database,"
each wanting a different PDB table shape:

**Tier 1 — trivially tabular, ready today.**
`/etc/passwd`, `/etc/shadow`, `/var/lib/dpkg/status`. Fixed or near-fixed row schema,
small, text-based. These convert to real PDB tables (columns, typed rows) with a
straightforward line parser — no filesystem walk needed, no binary format to reverse.
This is the cheapest, highest-value slice of "Approach B" (file-level PDB) and doesn't
require touching ext4 at all.

**Tier 2 — one-file-per-entity, list-shaped.**
`/var/lib/dpkg/info/*.list` (one file per package, listing that package's installed
paths) and the `.list`/`.md5sums` siblings. Natural fit as a `File_Metadata`-style table:
row = (package_name, installed_path), sourced directly from files that already exist in
this shape — no new semantic design needed, just ingestion.

**Tier 3 — already has its own binary DB format, don't re-invent it.**
`/var/log/journal/*` (systemd binary journal) and ext4 itself (inode/extent B-trees).
These are NOT good early PDB targets: journald's format has its own hash tables and
object headers, and re-deriving that as PDB tables is a full parser project on its own.
Correct move here is Approach A (block-level blob passthrough) for these specific
subtrees — store them as opaque blobs in PDB, keep native tools (journalctl, e2fsprogs)
as the read path, and only revisit if GPU-native journal querying becomes an actual goal.

## Revised recommendation for v4 vs v4.1 vs v5

- **v4 (done)**: blob-table PoC, byte-identical round-trip. Correctly scoped — proves the
  container mechanics, nothing more. No change needed here.
- **v4.1**: before tiling for a full rootfs, don't just scale the blob approach uniformly.
  Split the target: Tier 1 files (passwd/shadow/dpkg status) go in as real semantic
  tables now, since the parser is trivial and this is where "GPU queries /etc/passwd
  directly" becomes true today. Everything else (bulk of the rootfs, ext4 image, journal)
  stays blob-tiled, deferred to the tiling work already scoped.
- **v5**: only the Tier 2 slice (dpkg file-list-as-table) is realistic near-term semantic
  work. dconf is off the table for server images (doesn't exist) and only relevant if a
  desktop variant becomes a target — check `ubuntu_desktop_pxc1_v3_selfhost` before
  assuming dconf applies there. Journal/ext4-native (Tier 3) is a distinct, much larger
  project — don't fold it into the same milestone as Tier 1/2 work.

## Practical note for whoever builds this next

`guestfish --ro -a <image> -m /dev/sda1` inspects any of the repo's raw/qcow2 disk
images without mounting, root, or a running QEMU instance — useful for any future
PDB compiler that needs to walk a real rootfs for Tier 1/2 extraction.
