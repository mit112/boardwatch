"""The WAL-unsafe-filesystem guard (P3 item 8, the cross-OS half).

The corruption at risk is a Linux Docker container and the macOS host writing one DB file
over a bind-mount — a config a same-OS test cannot surface (WAL_DISCIPLINE.md), so the
mitigation is a runtime refusal, not a test. Detection is Linux-only, via
/proc/self/mountinfo: a host bind-mount shows up inside the container as
virtiofs/grpcfuse/etc., a named Docker volume shows up as the container's own ext4/overlay
and is safe. These fixtures are real mountinfo lines (the backend's own format), not a faked
platform constant — the guard's wiring is exercised separately by patching the detector.
"""

from __future__ import annotations

import sys

import pytest

from boardwatch.store.db import WalUnsafeFilesystemError, get_engine
from boardwatch.store.fs_safety import unsafe_wal_filesystem

# Docker Desktop bind-mount of a macOS host dir into the Linux container, VirtioFS backend.
_BIND_VIRTIOFS = """\
23 28 0:21 / / rw,relatime - overlay overlay rw,lowerdir=/a,upperdir=/b,workdir=/c
30 23 0:44 / /data rw,relatime - virtiofs docker-desktop-bind-mounts rw
"""

# Older Docker Desktop uses gRPC-FUSE for the same bind-mount; fstype is `fuse.grpcfuse`.
_BIND_GRPCFUSE = """\
23 28 0:21 / / rw,relatime - overlay overlay rw,lowerdir=/a
30 23 0:44 / /data rw,relatime - fuse.grpcfuse grpcfuse rw,user_id=0,group_id=0
"""

# A named Docker volume: the container's own ext4-backed storage, WAL-safe.
_NAMED_VOLUME = """\
23 28 0:21 / / rw,relatime - overlay overlay rw,lowerdir=/a
41 23 259:1 /var/lib/docker/volumes/boardwatch-data/_data /data rw,relatime - ext4 /dev/nvme0n1p1 rw
"""

# A network-mounted directory: NFS is WAL-unsafe wherever it is mounted.
_NFS_MOUNT = """\
23 28 0:21 / / rw,relatime - ext4 /dev/sda1 rw
55 23 0:52 / /mnt/nfs rw,relatime - nfs4 fileserver:/export rw,vers=4.2
"""

# /data on a safe ext4, but a sub-path is a separate NFS mount — longest-prefix must win.
_NESTED = """\
23 28 0:21 / / rw,relatime - ext4 /dev/sda1 rw
41 23 259:1 / /data rw,relatime - ext4 /dev/nvme0n1p1 rw
60 41 0:52 / /data/store rw,relatime - nfs4 fileserver:/export rw
"""

# A local NTFS/exFAT partition mounted via ntfs-3g reads as `fuseblk` — local disk, WAL-safe,
# must NOT be refused just because its name starts with "fuse".
_FUSEBLK = """\
23 28 0:21 / / rw,relatime - ext4 /dev/sda1 rw
70 23 8:2 / /data rw,relatime - fuseblk /dev/sdb1 rw,allow_other
"""

# A bind-mount whose mount point contains a space — mountinfo octal-escapes it as \\040.
_SPACED_BIND = """\
23 28 0:21 / / rw,relatime - overlay overlay rw,lowerdir=/a
30 23 0:44 / /data\\040dir rw,relatime - virtiofs docker-desktop-bind-mounts rw
"""


# The fixtures below are POSIX mount tables addressed by POSIX paths, and the detector resolves
# its argument with `os.path.realpath` before comparing. On Windows that rewrites "/data" to
# "\\data", which can never match a POSIX mount point, so every case here collapses onto the root
# mount: the three that expect a fstype FAIL, and the ones that expect None PASS FOR THE WRONG
# REASON — they would pass with an empty catalog too. A vacuous pass is worse than an honest skip,
# so the whole POSIX-addressed set is skipped rather than the failures alone.
#
# Production is unaffected, which is why this is a test-only skip: Windows has no
# /proc/self/mountinfo, so `unsafe_wal_filesystem` returns None before it ever compares a path.
# Detection is Linux-only by design (see the module docstring of store/fs_safety.py). The three
# platform-independent tests at the bottom of this file deliberately still run everywhere.
_posix_mount_table = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX mount-table fixture: Windows path normalization cannot match a POSIX mount point",
)


@_posix_mount_table
def test_a_bind_mounted_host_dir_reads_as_virtiofs() -> None:
    assert unsafe_wal_filesystem("/data", mountinfo_text=_BIND_VIRTIOFS) == "virtiofs"


@_posix_mount_table
def test_the_older_grpc_fuse_bind_mount_is_caught_by_the_fuse_prefix() -> None:
    assert unsafe_wal_filesystem("/data", mountinfo_text=_BIND_GRPCFUSE) == "fuse.grpcfuse"


@_posix_mount_table
def test_a_named_docker_volume_on_ext4_is_safe() -> None:
    assert unsafe_wal_filesystem("/data", mountinfo_text=_NAMED_VOLUME) is None


@_posix_mount_table
def test_a_path_on_the_container_overlay_root_is_safe() -> None:
    assert unsafe_wal_filesystem("/srv/app", mountinfo_text=_BIND_VIRTIOFS) is None


@_posix_mount_table
def test_an_nfs_mounted_directory_is_unsafe() -> None:
    assert unsafe_wal_filesystem("/mnt/nfs/boardwatch", mountinfo_text=_NFS_MOUNT) == "nfs4"


@_posix_mount_table
def test_longest_prefix_wins_a_safe_parent_does_not_clear_an_unsafe_child() -> None:
    assert unsafe_wal_filesystem("/data/store", mountinfo_text=_NESTED) == "nfs4"
    assert unsafe_wal_filesystem("/data", mountinfo_text=_NESTED) is None


@_posix_mount_table
def test_a_local_fuseblk_drive_is_not_refused() -> None:
    # ntfs-3g / exfat-fuse report `fuseblk`; it is local disk, so it must clear the "fuse" net.
    assert unsafe_wal_filesystem("/data/store", mountinfo_text=_FUSEBLK) is None


@_posix_mount_table
def test_a_bind_mount_point_with_a_space_is_still_detected() -> None:
    # The mount point is octal-escaped (\\040) in mountinfo; without decoding it, the guard
    # would fail to match the real path and miss an unsafe mount (a fail-open).
    assert unsafe_wal_filesystem("/data dir/store", mountinfo_text=_SPACED_BIND) == "virtiofs"


def test_no_mountinfo_means_no_detection_so_macos_and_windows_never_refuse() -> None:
    # An empty source stands in for a platform without /proc/self/mountinfo: the host side of
    # a bind-mount is normal local disk, so there is nothing to refuse and no false positive.
    assert unsafe_wal_filesystem("/data", mountinfo_text="") is None


def test_get_engine_refuses_a_wal_unsafe_filesystem(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("boardwatch.store.db.unsafe_wal_filesystem", lambda _path: "virtiofs")
    with pytest.raises(WalUnsafeFilesystemError) as excinfo:
        get_engine(tmp_path)
    message = str(excinfo.value)
    assert "virtiofs" in message
    assert excinfo.value.fstype == "virtiofs"
    # The message has to tell the operator the fix, not just the diagnosis.
    assert "named Docker volume" in message or "local disk" in message


def test_get_engine_opens_a_normal_local_dir(tmp_path) -> None:
    # A real call on the test's local tmp dir: the detector returns None on local disk, so the
    # engine is built. Guards the guard against refusing a legitimate run.
    engine = get_engine(tmp_path)
    assert engine is not None
