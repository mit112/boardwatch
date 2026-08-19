"""Refuse to open the store on a filesystem where SQLite's WAL journaling is unsafe.

WAL relies on shared memory and POSIX advisory locks that do not hold across a network or a
host<->container filesystem boundary. boardwatch ships a Docker image over a host-mounted DB,
which is exactly the Linux-container-plus-macOS-host configuration that corrupted job-apps'
primary key (WAL_DISCIPLINE.md, PROGRAM.md §3.P3 item 8). GitHub's macOS runners cannot run
Docker, so that config can never be a green CI check — the mitigation is a runtime refusal,
not a test (D-241).

Detection is Linux-only, via /proc/self/mountinfo. A host bind-mount shows up inside the
container as virtiofs/grpcfuse/9p/etc.; a named Docker volume shows up as the container's own
ext4/overlay and is safe — so the guard fires on precisely the dangerous config and clears
the recommended one. On any platform without /proc/self/mountinfo (macOS, Windows) the host
side is normal local disk, so detection returns None and never refuses a legitimate run.
"""

from __future__ import annotations

import os
from pathlib import Path

_MOUNTINFO = Path("/proc/self/mountinfo")

#: Closed, versioned catalog of filesystem types where SQLite WAL cannot hold its locks:
#: network shares and the virtualized bind-mount backends Docker Desktop exposes. Any fstype
#: whose name starts with "fuse" is also treated as unsafe (gRPC-FUSE, sshfs, s3fs, …).
WAL_UNSAFE_FSTYPES = frozenset(
    {
        "nfs",
        "nfs4",
        "cifs",
        "smbfs",
        "smb2",
        "smb3",
        "9p",
        "virtiofs",
        "vboxsf",
        "osxfs",
        "grpcfuse",
        "afpfs",
        "ncpfs",
        "glusterfs",
        "lustre",
        "ceph",
    }
)


def _read_mountinfo() -> str | None:
    """The Linux mount table, or None on any platform that has no /proc/self/mountinfo."""
    try:
        return _MOUNTINFO.read_text()
    except OSError:
        return None


def _unescape(field: str) -> str:
    """Decode the octal escapes the kernel writes into mountinfo path fields.

    mountinfo escapes space, tab, newline, and backslash; a mount point with a space is
    `\\040`. Without this, `_contains` would compare an escaped mount point against a real
    (decoded) path and MISS an unsafe mount — a fail-open the guard must not have. Backslash
    is decoded last so a decoded value is never re-interpreted.
    """
    return (
        field.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def _fstype_for_path(path: str, mountinfo_text: str) -> str | None:
    """The filesystem type of the mount that contains `path` (longest mount-point wins)."""
    target = os.path.realpath(path)
    best_point = ""
    best_fstype: str | None = None
    for line in mountinfo_text.splitlines():
        pre, sep, post = line.partition(" - ")
        if not sep:
            continue
        pre_fields = pre.split()
        post_fields = post.split()
        if len(pre_fields) < 5 or not post_fields:
            continue
        mount_point = _unescape(pre_fields[4])
        fstype = post_fields[0]
        if _contains(mount_point, target) and len(mount_point) >= len(best_point):
            best_point = mount_point
            best_fstype = fstype
    return best_fstype


def _contains(mount_point: str, target: str) -> bool:
    """Whether `target` sits at or under `mount_point`, matching on path boundaries."""
    if mount_point == "/":
        return True
    return target == mount_point or target.startswith(mount_point.rstrip("/") + "/")


def unsafe_wal_filesystem(path: str | Path, *, mountinfo_text: str | None = None) -> str | None:
    """Return the offending filesystem type if `path` is on a WAL-unsafe filesystem, else None.

    `mountinfo_text` is a seam for tests; in production it reads /proc/self/mountinfo, which
    only Linux has. A None (missing) mount table means no detection and no refusal.
    """
    text = mountinfo_text if mountinfo_text is not None else _read_mountinfo()
    if not text:
        return None
    fstype = _fstype_for_path(str(path), text)
    if fstype is None:
        return None
    # `fuse.<name>` (grpcfuse, sshfs, s3fs, …) and bare `fuse` are userspace network/remote
    # mounts; `fuseblk` is a LOCAL block device (ntfs-3g, exfat-fuse) and must not be refused.
    if fstype in WAL_UNSAFE_FSTYPES or fstype == "fuse" or fstype.startswith("fuse."):
        return fstype
    return None
