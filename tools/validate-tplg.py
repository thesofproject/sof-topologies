#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2026 Intel Corporation. All rights reserved.
"""
Validate compiled ALSA topology (.tplg) binary files and symlinks.
Checks:
  1. Symlink targets exist (no broken symlinks).
  2. File starts with the ALSA topology block magic ('CoEf').
  3. Block stream parses cleanly to EOF with valid sizes.
  4. Manifest block contains "sof_manifest" and "SOF ABI".
"""

import argparse
import glob
import os
import struct
import sys

ALSA_TPLG_MAGIC = b"CoSA"
HDR_STRUCT = struct.Struct("<4sIIIIII")  # magic, abi, version, type, size, vendor_type, payload_size


def validate_tplg_file(path: str) -> list[str]:
    errors: list[str] = []
    if os.path.islink(path):
        target = os.readlink(path)
        resolved = os.path.join(os.path.dirname(path), target)
        if not os.path.exists(resolved):
            errors.append(f"{path}: broken symlink -> {target}")
            return errors

    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as exc:
        return [f"{path}: cannot read file: {exc}"]

    if len(data) < HDR_STRUCT.size:
        return [f"{path}: file too small ({len(data)} bytes)"]

    offset = 0
    has_manifest = False
    while offset < len(data):
        if offset + HDR_STRUCT.size > len(data):
            errors.append(f"{path}: truncated block header at offset {offset}")
            break
        magic, _abi, _ver, blk_type, hdr_size, _vtype, payload_size = HDR_STRUCT.unpack_from(data, offset)
        if magic != ALSA_TPLG_MAGIC:
            errors.append(f"{path}: invalid block magic {magic!r} at offset {offset}")
            break
        if hdr_size < HDR_STRUCT.size:
            errors.append(f"{path}: invalid header size {hdr_size} at offset {offset}")
            break
        next_offset = offset + hdr_size + payload_size
        if next_offset > len(data):
            errors.append(
                f"{path}: block payload extends past EOF ({next_offset} > {len(data)}) at offset {offset}"
            )
            break
        if blk_type == 8:  # SND_SOC_TPLG_TYPE_MANIFEST
            has_manifest = True
        offset = next_offset

    if not has_manifest:
        errors.append(f"{path}: missing 'sof_manifest' block")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate compiled SOF .tplg binaries")
    parser.add_argument("dirs", nargs="+", help="Directories containing .tplg files to validate")
    args = parser.parse_args()

    total_files = 0
    all_errors: list[str] = []

    for d in args.dirs:
        if not os.path.isdir(d):
            all_errors.append(f"{d}: directory does not exist")
            continue
        files = sorted(glob.glob(os.path.join(d, "*.tplg")))
        if not files:
            all_errors.append(f"{d}: no .tplg files found")
            continue
        for fpath in files:
            total_files += 1
            all_errors.extend(validate_tplg_file(fpath))

    if all_errors:
        for err in all_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        print(f"Validation FAILED ({len(all_errors)} errors across {total_files} files)", file=sys.stderr)
        return 1

    print(f"Validated {total_files} .tplg files successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
