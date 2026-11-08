#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2026 Intel Corporation. All rights reserved.

"""Validate SOF topology RPM, DEB, and TGZ packages.

Checks:
1. Package metadata & version data (Name, Version, Architecture, License, ABI summary).
2. File paths & completeness (/lib/firmware/intel/{sof-tplg,sof-ipc4-tplg,sof-ace-tplg},
   100% match with compiled production topologies, no stray build artifacts).
3. File & directory permissions (0644 for .tplg files, 0755 for directories,
   0777 for symlinks, root:root ownership).
4. Symbolic links (sof-ace-tplg -> sof-ipc4-tplg directory link and intra-directory
   .tplg symlinks such as sof-wcl-dmic-* -> sof-ptl-dmic-*, relative targets,
   no broken/dangling links).
5. Embedded binary version data & integrity (ALSA 'CoSA' header magic, ALSA ABI=5,
   SOF_ABI_MAJOR.SOF_ABI_MINOR.SOF_ABI_PATCH in SND_SOC_TPLG_TYPE_MANIFEST, and
   checksum match against build outputs).
"""

import argparse
import hashlib
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile

TPLG_MAGIC = b"CoSA"
HDR_STRUCT = struct.Struct("<4sIIIIIIII")
ALSA_TPLG_ABI_EXPECTED = 5
SND_SOC_TPLG_TYPE_MANIFEST = 8


def parse_abi_header(abi_header_path: pathlib.Path) -> tuple[int, int, int]:
    """Parse SOF_ABI_MAJOR, SOF_ABI_MINOR, SOF_ABI_PATCH from include/kernel/abi.h."""
    text = abi_header_path.read_text(encoding="utf-8")
    major_m = re.search(r"#define\s+SOF_ABI_MAJOR\s+(\d+)", text)
    minor_m = re.search(r"#define\s+SOF_ABI_MINOR\s+(\d+)", text)
    patch_m = re.search(r"#define\s+SOF_ABI_PATCH\s+(\d+)", text)
    if not (major_m and minor_m and patch_m):
        raise ValueError(f"Could not parse SOF_ABI_MAJOR/MINOR/PATCH from {abi_header_path}")
    return int(major_m.group(1)), int(minor_m.group(1)), int(patch_m.group(1))


def md5sum(path: pathlib.Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_tplg_binary_version(
    path: pathlib.Path,
    expected_abi: tuple[int, int, int],
    ipc_version: int,
) -> tuple[bool, str]:
    """Validate CoSA blocks and embedded SOF ABI version inside a .tplg binary."""
    data = path.read_bytes()
    if len(data) < HDR_STRUCT.size:
        return False, f"file too small ({len(data)} bytes)"

    offset = 0
    manifest_abi = None
    manifest_priv_sz = None

    while offset < len(data):
        if offset + HDR_STRUCT.size > len(data):
            return False, f"truncated block header at offset {offset}"
        magic, abi, _ver, blk_type, hdr_size, _vtype, payload_bytes, _idx, _cnt = (
            HDR_STRUCT.unpack_from(data, offset)
        )
        if magic != TPLG_MAGIC:
            return False, f"invalid block magic {magic!r} at offset {offset}"
        if abi != ALSA_TPLG_ABI_EXPECTED:
            return False, f"unexpected ALSA topology ABI {abi} (expected {ALSA_TPLG_ABI_EXPECTED})"
        if hdr_size != HDR_STRUCT.size:
            return False, f"unexpected block header size {hdr_size} (expected {HDR_STRUCT.size})"

        payload_start = offset + hdr_size
        payload_end = payload_start + payload_bytes
        if payload_end > len(data):
            return False, f"block payload extends past EOF ({payload_end} > {len(data)})"

        if blk_type == SND_SOC_TPLG_TYPE_MANIFEST:
            man_data = data[payload_start:payload_end]
            if len(man_data) < 112:
                return False, f"manifest block too short ({len(man_data)} < 112)"
            priv_sz = struct.unpack_from("<I", man_data, 108)[0]
            priv_data = man_data[112 : 112 + priv_sz]
            manifest_priv_sz = priv_sz
            if ipc_version == 3 and priv_sz >= 3 and len(priv_data) >= 3:
                manifest_abi = struct.unpack_from("<BBB", priv_data, 0)
            elif ipc_version == 4 and priv_sz >= 6 and len(priv_data) >= 6:
                manifest_abi = struct.unpack_from("<HHH", priv_data, 0)
            else:
                return (
                    False,
                    f"unexpected manifest priv_size={priv_sz} for IPC{ipc_version}",
                )

        offset = payload_end

    if manifest_abi is None:
        return False, "missing SND_SOC_TPLG_TYPE_MANIFEST (type 8) block"

    if manifest_abi != expected_abi:
        return (
            False,
            f"manifest SOF ABI {manifest_abi} != expected {expected_abi} (priv_size={manifest_priv_sz})",
        )

    return True, "ok"


def collect_expected_build_artefacts(
    build_dir: pathlib.Path,
) -> tuple[dict[str, pathlib.Path], dict[str, pathlib.Path], dict[str, str]]:
    """Return expected (ipc3_files, ipc4_files, ipc4_symlinks) from the build directory."""
    ipc3_files: dict[str, pathlib.Path] = {}
    ipc4_files: dict[str, pathlib.Path] = {}
    ipc4_symlinks: dict[str, str] = {}

    t1_prod = build_dir / "topology1" / "production"
    if t1_prod.is_dir():
        for p in sorted(t1_prod.glob("*.tplg")):
            ipc3_files[p.name] = p

    t2_ipc3 = build_dir / "topology2" / "production" / "ipc3"
    if t2_ipc3.is_dir():
        for p in sorted(t2_ipc3.glob("*.tplg")):
            ipc3_files[p.name] = p

    t2_prod = build_dir / "topology2" / "production"
    if t2_prod.is_dir():
        for p in sorted(t2_prod.glob("*.tplg")):
            if p.is_symlink():
                ipc4_symlinks[p.name] = os.readlink(p)
            else:
                ipc4_files[p.name] = p

    return ipc3_files, ipc4_files, ipc4_symlinks


def verify_extracted_tree(
    pkg_label: str,
    extract_root: pathlib.Path,
    install_prefix: str,
    vendor_dir: str,
    version_suffix: str,
    expected_abi: tuple[int, int, int],
    expected_ipc3: dict[str, pathlib.Path],
    expected_ipc4: dict[str, pathlib.Path],
    expected_ipc4_symlinks: dict[str, str],
    strict_tree: bool = True,
) -> list[str]:
    """Validate paths, permissions, symlinks, and embedded binary ABI version data in root."""
    errors: list[str] = []
    rel_prefix = install_prefix.lstrip("/")
    vendor_root = extract_root / rel_prefix / vendor_dir

    if not vendor_root.is_dir():
        errors.append(f"[{pkg_label}] missing vendor directory: /{rel_prefix}/{vendor_dir}")
        return errors

    ipc3_dir_name = f"sof-tplg{version_suffix}"
    ipc4_dir_name = f"sof-ipc4-tplg{version_suffix}"
    ace_link_name = f"sof-ace-tplg{version_suffix}"

    ipc3_dir = vendor_root / ipc3_dir_name
    ipc4_dir = vendor_root / ipc4_dir_name
    ace_link = vendor_root / ace_link_name

    for dpath in (ipc3_dir, ipc4_dir):
        if dpath.is_dir():
            dmode = dpath.stat().st_mode & 0o777
            if dmode != 0o755:
                errors.append(
                    f"[{pkg_label}] directory {dpath.name}: filesystem mode {oct(dmode)}, expected 0o755"
                )

    # 1. Check directory symlink: sof-ace-tplg -> sof-ipc4-tplg
    if not ace_link.is_symlink():
        errors.append(f"[{pkg_label}] {ace_link_name} is missing or not a symbolic link")
    else:
        link_target = os.readlink(ace_link)
        if link_target != ipc4_dir_name:
            errors.append(
                f"[{pkg_label}] {ace_link_name} symlink target is '{link_target}', expected '{ipc4_dir_name}'"
            )
        if os.path.isabs(link_target):
            errors.append(f"[{pkg_label}] {ace_link_name} must be a relative symlink, got '{link_target}'")
        resolved_ace = (ace_link.parent / link_target).resolve()
        if resolved_ace != ipc4_dir.resolve() or not resolved_ace.is_dir():
            errors.append(f"[{pkg_label}] {ace_link_name} does not resolve to {ipc4_dir_name}")

    # 2. Ensure no unexpected subdirectories or non-.tplg files exist anywhere in extract_root
    if strict_tree:
        allowed_dirs = {
            extract_root,
            *(extract_root / p for p in pathlib.Path(rel_prefix).parents if str(p) != "."),
            extract_root / rel_prefix,
            vendor_root,
            ipc3_dir,
            ipc4_dir,
        }
        for root, dirs, files in os.walk(extract_root, followlinks=False):
            root_p = pathlib.Path(root)
            for d in dirs:
                dp = root_p / d
                if dp.is_symlink():
                    if dp != ace_link:
                        errors.append(
                            f"[{pkg_label}] unexpected directory symlink: {dp.relative_to(extract_root)}"
                        )
                    continue
                if dp not in allowed_dirs:
                    errors.append(
                        f"[{pkg_label}] unexpected directory in package: /{dp.relative_to(extract_root)}"
                    )
            for f in files:
                fp = root_p / f
                if fp == ace_link:
                    continue
                if fp.suffix != ".tplg":
                    errors.append(
                        f"[{pkg_label}] unexpected non-topology file in package: /{fp.relative_to(extract_root)}"
                    )
                if root_p not in (ipc3_dir, ipc4_dir):
                    errors.append(
                        f"[{pkg_label}] .tplg file in wrong directory: /{fp.relative_to(extract_root)}"
                    )

    # 3. Check IPC3 topologies (paths, permissions, checksums, and binary ABI version)
    if expected_ipc3:
        if not ipc3_dir.is_dir():
            errors.append(f"[{pkg_label}] missing IPC3 directory: /{ipc3_dir.relative_to(extract_root)}")
        else:
            actual_ipc3 = {p.name: p for p in ipc3_dir.iterdir() if p.suffix == ".tplg"}
            missing_ipc3 = sorted(set(expected_ipc3) - set(actual_ipc3))
            extra_ipc3 = sorted(set(actual_ipc3) - set(expected_ipc3))
            if missing_ipc3:
                errors.append(f"[{pkg_label}] missing {len(missing_ipc3)} IPC3 topologies: {missing_ipc3[:5]}")
            if extra_ipc3:
                errors.append(f"[{pkg_label}] unexpected IPC3 topologies: {extra_ipc3[:5]}")

            for name, pkg_file in sorted(actual_ipc3.items()):
                if pkg_file.is_symlink():
                    errors.append(f"[{pkg_label}] unexpected symlink in IPC3 dir: {name}")
                    continue
                fmode = pkg_file.stat().st_mode & 0o777
                if fmode != 0o644:
                    errors.append(
                        f"[{pkg_label}] IPC3 {name}: filesystem mode {oct(fmode)}, expected 0o644"
                    )
                ok, msg = validate_tplg_binary_version(pkg_file, expected_abi, ipc_version=3)
                if not ok:
                    errors.append(f"[{pkg_label}] IPC3 {name}: {msg}")
                if name in expected_ipc3:
                    if md5sum(pkg_file) != md5sum(expected_ipc3[name]):
                        errors.append(f"[{pkg_label}] IPC3 {name}: MD5 mismatch against built file")

    # 4. Check IPC4 topologies & symlinks (paths, permissions, targets, checksums, and binary ABI version)
    if expected_ipc4 or expected_ipc4_symlinks:
        if not ipc4_dir.is_dir():
            errors.append(f"[{pkg_label}] missing IPC4 directory: /{ipc4_dir.relative_to(extract_root)}")
        else:
            actual_ipc4_regular: dict[str, pathlib.Path] = {}
            actual_ipc4_symlinks: dict[str, str] = {}
            for p in ipc4_dir.iterdir():
                if p.is_symlink():
                    actual_ipc4_symlinks[p.name] = os.readlink(p)
                elif p.is_file() and p.suffix == ".tplg":
                    actual_ipc4_regular[p.name] = p

            missing_ipc4 = sorted(set(expected_ipc4) - set(actual_ipc4_regular))
            extra_ipc4 = sorted(set(actual_ipc4_regular) - set(expected_ipc4))
            if missing_ipc4:
                errors.append(f"[{pkg_label}] missing {len(missing_ipc4)} IPC4 topologies: {missing_ipc4[:5]}")
            if extra_ipc4:
                errors.append(f"[{pkg_label}] unexpected IPC4 regular topologies: {extra_ipc4[:5]}")

            missing_links = sorted(set(expected_ipc4_symlinks) - set(actual_ipc4_symlinks))
            extra_links = sorted(set(actual_ipc4_symlinks) - set(expected_ipc4_symlinks))
            if missing_links:
                errors.append(f"[{pkg_label}] missing IPC4 symlinks: {missing_links}")
            if extra_links:
                errors.append(f"[{pkg_label}] unexpected IPC4 symlinks: {extra_links}")

            for link_name, expected_target in sorted(expected_ipc4_symlinks.items()):
                if link_name not in actual_ipc4_symlinks:
                    continue
                actual_target = actual_ipc4_symlinks[link_name]
                if actual_target != expected_target:
                    errors.append(
                        f"[{pkg_label}] symlink {link_name} -> '{actual_target}', expected '{expected_target}'"
                    )
                if os.path.isabs(actual_target):
                    errors.append(f"[{pkg_label}] symlink {link_name} must be relative, got '{actual_target}'")
                resolved_target = ipc4_dir / actual_target
                if not resolved_target.is_file():
                    errors.append(f"[{pkg_label}] broken symlink {link_name} -> '{actual_target}'")

            for name, pkg_file in sorted(actual_ipc4_regular.items()):
                fmode = pkg_file.stat().st_mode & 0o777
                if fmode != 0o644:
                    errors.append(
                        f"[{pkg_label}] IPC4 {name}: filesystem mode {oct(fmode)}, expected 0o644"
                    )
                ok, msg = validate_tplg_binary_version(pkg_file, expected_abi, ipc_version=4)
                if not ok:
                    errors.append(f"[{pkg_label}] IPC4 {name}: {msg}")
                if name in expected_ipc4:
                    if md5sum(pkg_file) != md5sum(expected_ipc4[name]):
                        errors.append(f"[{pkg_label}] IPC4 {name}: MD5 mismatch against built file")

    return errors


def validate_deb_package(
    deb_path: pathlib.Path,
    expected_version: str,
    expected_abi: tuple[int, int, int],
    install_prefix: str,
    vendor_dir: str,
    version_suffix: str,
    expected_ipc3: dict[str, pathlib.Path],
    expected_ipc4: dict[str, pathlib.Path],
    expected_ipc4_symlinks: dict[str, str],
) -> list[str]:
    """Validate a .deb package's control metadata, permissions, paths, links, and binaries."""
    errors: list[str] = []
    label = f"DEB ({deb_path.name})"

    if not deb_path.is_file() or deb_path.stat().st_size == 0:
        return [f"[{label}] package file does not exist or is empty: {deb_path}"]

    # 1. Control metadata & version check
    for field, expected_val in [
        ("Package", "sof-topology"),
        ("Version", expected_version),
        ("Architecture", "all"),
    ]:
        res = subprocess.run(
            ["dpkg-deb", "-f", str(deb_path), field],
            capture_output=True,
            text=True,
            check=True,
        )
        actual_val = res.stdout.strip()
        if actual_val != expected_val:
            errors.append(f"[{label}] control field {field}='{actual_val}', expected '{expected_val}'")

    desc_res = subprocess.run(
        ["dpkg-deb", "-f", str(deb_path), "Description"],
        capture_output=True,
        text=True,
        check=True,
    )
    abi_str = f"{expected_abi[0]}.{expected_abi[1]}.{expected_abi[2]}"
    if f"ABI {abi_str}" not in desc_res.stdout:
        errors.append(f"[{label}] Description does not mention 'ABI {abi_str}': {desc_res.stdout.strip()}")

    # 2. Archive listing: permissions & ownership check
    list_res = subprocess.run(
        ["dpkg-deb", "-c", str(deb_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in list_res.stdout.splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        perms, owner_group = parts[0], parts[1]
        path_part = parts[5]
        if owner_group != "root/root":
            errors.append(f"[{label}] {path_part}: ownership is '{owner_group}', expected 'root/root'")
        if perms.startswith("d"):
            if perms != "drwxr-xr-x":
                errors.append(f"[{label}] directory {path_part}: permissions '{perms}', expected 'drwxr-xr-x' (0755)")
        elif perms.startswith("l"):
            if perms != "lrwxrwxrwx":
                errors.append(f"[{label}] symlink {path_part}: permissions '{perms}', expected 'lrwxrwxrwx' (0777)")
        elif perms.startswith("-"):
            if perms != "-rw-r--r--":
                errors.append(f"[{label}] file {path_part}: permissions '{perms}', expected '-rw-r--r--' (0644)")

    # 3. Extract and validate file paths, symlinks, and embedded binary ABI versions
    with tempfile.TemporaryDirectory(prefix="sof-tplg-deb-") as tmpdir:
        extract_root = pathlib.Path(tmpdir)
        subprocess.run(["dpkg-deb", "-x", str(deb_path), str(extract_root)], check=True)
        errors.extend(
            verify_extracted_tree(
                label,
                extract_root,
                install_prefix,
                vendor_dir,
                version_suffix,
                expected_abi,
                expected_ipc3,
                expected_ipc4,
                expected_ipc4_symlinks,
            )
        )

    # 4. Full dpkg install, verify (-V), and remove (-r) cycle in an isolated root
    if shutil.which("fakeroot") and shutil.which("dpkg"):
        with tempfile.TemporaryDirectory(prefix="sof-tplg-dpkg-inst-") as tmpdir:
            inst_root = pathlib.Path(tmpdir)
            admindir = inst_root / "var/lib/dpkg"
            (admindir / "info").mkdir(parents=True)
            (admindir / "updates").mkdir(parents=True)
            (admindir / "status").write_text("", encoding="utf-8")
            log_file = inst_root / "var/log/dpkg.log"
            log_file.parent.mkdir(parents=True)

            base_cmd = [
                "fakeroot",
                "dpkg",
                f"--instdir={inst_root}",
                f"--admindir={admindir}",
                f"--log={log_file}",
                "--force-not-root",
                "--force-script-chrootless",
                "--force-architecture",
            ]
            inst_res = subprocess.run(
                [*base_cmd, "-i", str(deb_path)],
                capture_output=True,
                text=True,
            )
            if inst_res.returncode != 0:
                errors.append(f"[{label}] dpkg -i failed: {inst_res.stderr.strip()}")
            else:
                ver_res = subprocess.run(
                    [*base_cmd, "-V", "sof-topology"],
                    capture_output=True,
                    text=True,
                )
                if ver_res.returncode != 0 or ver_res.stdout.strip():
                    errors.append(
                        f"[{label}] dpkg -V reported verification issues: {ver_res.stdout.strip()} {ver_res.stderr.strip()}"
                    )
                errors.extend(
                    verify_extracted_tree(
                        f"{label} dpkg-install",
                        inst_root,
                        install_prefix,
                        vendor_dir,
                        version_suffix,
                        expected_abi,
                        expected_ipc3,
                        expected_ipc4,
                        expected_ipc4_symlinks,
                        strict_tree=False,
                    )
                )
                rm_res = subprocess.run(
                    [*base_cmd, "-r", "sof-topology"],
                    capture_output=True,
                    text=True,
                )
                if rm_res.returncode != 0:
                    errors.append(f"[{label}] dpkg -r failed: {rm_res.stderr.strip()}")
                else:
                    vendor_root = inst_root / install_prefix.lstrip("/") / vendor_dir
                    for leftover in (
                        f"sof-tplg{version_suffix}",
                        f"sof-ipc4-tplg{version_suffix}",
                        f"sof-ace-tplg{version_suffix}",
                    ):
                        lp = vendor_root / leftover
                        if lp.exists() or lp.is_symlink():
                            errors.append(f"[{label}] dpkg -r left behind /{lp.relative_to(inst_root)}")

    return errors


def validate_rpm_package(
    rpm_path: pathlib.Path,
    expected_version: str,
    expected_abi: tuple[int, int, int],
    install_prefix: str,
    vendor_dir: str,
    version_suffix: str,
    expected_ipc3: dict[str, pathlib.Path],
    expected_ipc4: dict[str, pathlib.Path],
    expected_ipc4_symlinks: dict[str, str],
) -> list[str]:
    """Validate an .rpm package's header metadata, permissions, paths, links, and binaries."""
    errors: list[str] = []
    label = f"RPM ({rpm_path.name})"

    if not rpm_path.is_file() or rpm_path.stat().st_size == 0:
        return [f"[{label}] package file does not exist or is empty: {rpm_path}"]

    # 1. Header metadata & version check
    qf = "%{NAME}|%{VERSION}|%{ARCH}|%{LICENSE}|%{SUMMARY}"
    res = subprocess.run(
        ["rpm", "-qp", "--qf", qf, str(rpm_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    name, ver, arch, lic, summary = res.stdout.strip().split("|", 4)
    if name != "sof-topology":
        errors.append(f"[{label}] NAME='{name}', expected 'sof-topology'")
    if ver != expected_version:
        errors.append(f"[{label}] VERSION='{ver}', expected '{expected_version}'")
    if arch != "noarch":
        errors.append(f"[{label}] ARCH='{arch}', expected 'noarch'")
    if lic != "BSD-3-Clause":
        errors.append(f"[{label}] LICENSE='{lic}', expected 'BSD-3-Clause'")
    abi_str = f"{expected_abi[0]}.{expected_abi[1]}.{expected_abi[2]}"
    if f"ABI {abi_str}" not in summary:
        errors.append(f"[{label}] SUMMARY does not mention 'ABI {abi_str}': {summary}")

    # 2. File permissions, ownership & symlink table via rpm query
    files_qf = "[%{FILEMODES:perms}|%{FILEUSERNAME}:%{FILEGROUPNAME}|%{FILENAMES}|%{FILELINKTOS}\n]"
    files_res = subprocess.run(
        ["rpm", "-qp", "--qf", files_qf, str(rpm_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in files_res.stdout.splitlines():
        if not line.strip():
            continue
        perms, owner_group, fname, _linkto = line.split("|", 3)
        if owner_group != "root:root":
            errors.append(f"[{label}] {fname}: ownership is '{owner_group}', expected 'root:root'")
        if perms.startswith("d"):
            if perms != "drwxr-xr-x":
                errors.append(f"[{label}] directory {fname}: permissions '{perms}', expected 'drwxr-xr-x' (0755)")
        elif perms.startswith("l"):
            if perms != "lrwxrwxrwx":
                errors.append(f"[{label}] symlink {fname}: permissions '{perms}', expected 'lrwxrwxrwx' (0777)")
        elif perms.startswith("-"):
            if perms != "-rw-r--r--":
                errors.append(f"[{label}] file {fname}: permissions '{perms}', expected '-rw-r--r--' (0644)")

    # 3. Extract RPM payload and validate paths, links, and embedded binary ABI versions
    with tempfile.TemporaryDirectory(prefix="sof-tplg-rpm-") as tmpdir:
        extract_root = pathlib.Path(tmpdir)
        if shutil.which("rpm2cpio") and shutil.which("cpio"):
            p1 = subprocess.Popen(["rpm2cpio", str(rpm_path)], stdout=subprocess.PIPE)
            assert p1.stdout is not None
            subprocess.run(
                ["cpio", "-idm", "--quiet"],
                stdin=p1.stdout,
                cwd=str(extract_root),
                check=True,
            )
            p1.stdout.close()
            if p1.wait() != 0:
                errors.append(f"[{label}] rpm2cpio failed on {rpm_path}")
                return errors
        else:
            errors.append(f"[{label}] rpm2cpio or cpio not found on PATH")
            return errors

        errors.extend(
            verify_extracted_tree(
                label,
                extract_root,
                install_prefix,
                vendor_dir,
                version_suffix,
                expected_abi,
                expected_ipc3,
                expected_ipc4,
                expected_ipc4_symlinks,
            )
        )

    # 4. Full rpm install (-ivh), verify (-V), and erase (-e) cycle in an isolated root
    if shutil.which("fakeroot") and shutil.which("rpm"):
        with tempfile.TemporaryDirectory(prefix="sof-tplg-rpm-inst-") as tmpdir:
            inst_root = pathlib.Path(tmpdir)
            rpmdb = inst_root / "rpmdb"
            rpmdb.mkdir(parents=True)
            reloc_fw = inst_root / install_prefix.lstrip("/")

            inst_res = subprocess.run(
                [
                    "fakeroot",
                    "rpm",
                    "--dbpath",
                    str(rpmdb),
                    "--relocate",
                    f"{install_prefix}={reloc_fw}",
                    "--badreloc",
                    "--nodeps",
                    "--ignorearch",
                    "--ignoreos",
                    "-ivh",
                    str(rpm_path),
                ],
                capture_output=True,
                text=True,
            )
            if inst_res.returncode != 0:
                errors.append(f"[{label}] rpm -ivh failed: {inst_res.stderr.strip()}")
            else:
                ver_res = subprocess.run(
                    ["fakeroot", "rpm", "--dbpath", str(rpmdb), "-V", "sof-topology"],
                    capture_output=True,
                    text=True,
                )
                if ver_res.returncode != 0 or ver_res.stdout.strip():
                    errors.append(
                        f"[{label}] rpm -V reported verification issues: {ver_res.stdout.strip()} {ver_res.stderr.strip()}"
                    )
                errors.extend(
                    verify_extracted_tree(
                        f"{label} rpm-install",
                        inst_root,
                        install_prefix,
                        vendor_dir,
                        version_suffix,
                        expected_abi,
                        expected_ipc3,
                        expected_ipc4,
                        expected_ipc4_symlinks,
                        strict_tree=False,
                    )
                )
                rm_res = subprocess.run(
                    ["fakeroot", "rpm", "--dbpath", str(rpmdb), "-e", "sof-topology"],
                    capture_output=True,
                    text=True,
                )
                if rm_res.returncode != 0:
                    errors.append(f"[{label}] rpm -e failed: {rm_res.stderr.strip()}")
                else:
                    vendor_root = reloc_fw / vendor_dir
                    for leftover in (
                        f"sof-tplg{version_suffix}",
                        f"sof-ipc4-tplg{version_suffix}",
                        f"sof-ace-tplg{version_suffix}",
                    ):
                        lp = vendor_root / leftover
                        if lp.exists() or lp.is_symlink():
                            errors.append(f"[{label}] rpm -e left behind /{lp.relative_to(inst_root)}")

    return errors


def validate_tgz_package(
    tgz_path: pathlib.Path,
    expected_abi: tuple[int, int, int],
    install_prefix: str,
    vendor_dir: str,
    version_suffix: str,
    expected_ipc3: dict[str, pathlib.Path],
    expected_ipc4: dict[str, pathlib.Path],
    expected_ipc4_symlinks: dict[str, str],
) -> list[str]:
    """Validate a .tar.gz CPack archive's permissions, paths, links, and binaries."""
    errors: list[str] = []
    label = f"TGZ ({tgz_path.name})"

    if not tgz_path.is_file() or tgz_path.stat().st_size == 0:
        return [f"[{label}] archive file does not exist or is empty: {tgz_path}"]

    with tempfile.TemporaryDirectory(prefix="sof-tplg-tgz-") as tmpdir:
        extract_root = pathlib.Path(tmpdir)
        with tarfile.open(tgz_path, "r:gz") as tf:
            members = tf.getmembers()
            if not members:
                return [f"[{label}] archive is empty"]
            top_prefix = members[0].name.split("/")[0]
            for m in members:
                mode = m.mode & 0o777
                if m.isdir():
                    if mode != 0o755:
                        errors.append(f"[{label}] directory {m.name}: mode {oct(mode)}, expected 0o755")
                elif m.isfile():
                    if mode != 0o644:
                        errors.append(f"[{label}] file {m.name}: mode {oct(mode)}, expected 0o644")
            tf.extractall(extract_root, filter="fully_trusted")

        archive_root = extract_root / top_prefix
        errors.extend(
            verify_extracted_tree(
                label,
                archive_root,
                install_prefix,
                vendor_dir,
                version_suffix,
                expected_abi,
                expected_ipc3,
                expected_ipc4,
                expected_ipc4_symlinks,
            )
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=pathlib.Path, required=True, help="CMake build directory")
    parser.add_argument("--abi-header", type=pathlib.Path, required=True, help="Path to include/kernel/abi.h")
    parser.add_argument("--expected-version", default=None, help="Expected package version (default: ABI version)")
    parser.add_argument("--install-prefix", default="/lib/firmware", help="Expected install prefix in DEB/RPM")
    parser.add_argument("--vendor-dir", default="intel", help="Vendor subdir under install prefix")
    parser.add_argument("--version-suffix", default="", help="Optional version suffix for topology dirs")
    parser.add_argument(
        "--validate-installed-root",
        type=pathlib.Path,
        default=None,
        help="Validate an already-installed root filesystem (e.g. / after sudo dpkg -i or rpm -ivh)",
    )
    parser.add_argument(
        "--no-build-if-missing",
        action="store_true",
        help="Fail instead of running cpack if DEB/RPM packages are not yet built",
    )
    args = parser.parse_args()

    build_dir = args.build_dir.resolve()
    abi_header = args.abi_header.resolve()
    expected_abi = parse_abi_header(abi_header)
    abi_version_str = f"{expected_abi[0]}.{expected_abi[1]}.{expected_abi[2]}"
    expected_version = args.expected_version or abi_version_str

    expected_ipc3, expected_ipc4, expected_ipc4_symlinks = collect_expected_build_artefacts(build_dir)
    if not expected_ipc3 and not expected_ipc4:
        print(f"ERROR: No compiled topologies found in {build_dir}", file=sys.stderr)
        return 1

    if args.validate_installed_root is not None:
        inst_root = args.validate_installed_root.resolve()
        errors = verify_extracted_tree(
            f"Installed root ({inst_root})",
            inst_root,
            args.install_prefix,
            args.vendor_dir,
            args.version_suffix,
            expected_abi,
            expected_ipc3,
            expected_ipc4,
            expected_ipc4_symlinks,
            strict_tree=False,
        )
        if errors:
            for err in errors:
                print(f"FAIL: {err}", file=sys.stderr)
            print(f"\nInstalled root validation FAILED with {len(errors)} error(s).", file=sys.stderr)
            return 1
        print(
            f"Validated installed topologies under {inst_root}{args.install_prefix}/{args.vendor_dir}:\n"
            f"  - IPC3 topologies: {len(expected_ipc3)} files in sof-tplg{args.version_suffix}\n"
            f"  - IPC4 topologies: {len(expected_ipc4)} files + {len(expected_ipc4_symlinks)} symlinks in "
            f"sof-ipc4-tplg{args.version_suffix}\n"
            f"  - Directory symlink: sof-ace-tplg{args.version_suffix} -> sof-ipc4-tplg{args.version_suffix}\n"
            f"  - Permissions: 0755 dirs, 0644 files, SOF ABI {abi_version_str}"
        )
        return 0

    deb_path = build_dir / f"sof-topology_{expected_version}_all.deb"
    rpm_path = build_dir / f"sof-topology-{expected_version}-1.noarch.rpm"
    tgz_path = build_dir / f"sof-topology-{expected_version}-Linux.tar.gz"

    if (not deb_path.is_file() or not rpm_path.is_file() or not tgz_path.is_file()) and not args.no_build_if_missing:
        print(f"Building DEB, RPM, and TGZ packages in {build_dir} via CPack...")
        subprocess.run(["cpack", "-G", "DEB;RPM;TGZ"], cwd=str(build_dir), check=True)

    all_errors: list[str] = []

    all_errors.extend(
        validate_deb_package(
            deb_path,
            expected_version,
            expected_abi,
            args.install_prefix,
            args.vendor_dir,
            args.version_suffix,
            expected_ipc3,
            expected_ipc4,
            expected_ipc4_symlinks,
        )
    )
    all_errors.extend(
        validate_rpm_package(
            rpm_path,
            expected_version,
            expected_abi,
            args.install_prefix,
            args.vendor_dir,
            args.version_suffix,
            expected_ipc3,
            expected_ipc4,
            expected_ipc4_symlinks,
        )
    )
    all_errors.extend(
        validate_tgz_package(
            tgz_path,
            expected_abi,
            args.install_prefix,
            args.vendor_dir,
            args.version_suffix,
            expected_ipc3,
            expected_ipc4,
            expected_ipc4_symlinks,
        )
    )

    if all_errors:
        for err in all_errors:
            print(f"FAIL: {err}", file=sys.stderr)
        print(f"\nPackage validation FAILED with {len(all_errors)} error(s).", file=sys.stderr)
        return 1

    print(
        f"Validated DEB ({deb_path.name}), RPM ({rpm_path.name}), and TGZ ({tgz_path.name}):\n"
        f"  - Version: {expected_version} (SOF ABI {abi_version_str}, ALSA ABI {ALSA_TPLG_ABI_EXPECTED})\n"
        f"  - IPC3 topologies: {len(expected_ipc3)} files in {args.install_prefix}/{args.vendor_dir}/sof-tplg{args.version_suffix}\n"
        f"  - IPC4 topologies: {len(expected_ipc4)} files + {len(expected_ipc4_symlinks)} symlinks in "
        f"{args.install_prefix}/{args.vendor_dir}/sof-ipc4-tplg{args.version_suffix}\n"
        f"  - Directory symlink: sof-ace-tplg{args.version_suffix} -> sof-ipc4-tplg{args.version_suffix}\n"
        f"  - Permissions: 0755 dirs, 0644 files, 0777 symlinks, root:root ownership"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
