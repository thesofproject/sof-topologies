#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2026 Intel Corporation. All rights reserved.
#
# Install compiled SOF topologies (.tplg) to:
#   1. Local firmware directory (--dest /lib/firmware, default)
#   2. Offline/NFS rootfs (--rootfs /srv/nfs/rootfs)
#   3. sof-bin release tree (--sof-bin /path/to/sof-bin/v2.x.x --version v2.x)
#   4. Remote DUT via SSH (--ssh root@hostname)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOF_TOPOLOGY_REPO="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="${BUILD_TPLG_DIR:-$SOF_TOPOLOGY_REPO/build}"

DEST_PREFIX="/lib/firmware"
ROOTFS=""
SOF_BIN_DIR=""
VERSION_TAG=""
SSH_TARGET=""
COMPONENT="all"
DRY_RUN=false

usage()
{
	cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --build-dir <dir>     Build directory containing compiled topologies (default: $BUILD_DIR)
  --dest <prefix>       Local firmware root directory (default: /lib/firmware)
  --rootfs <dir>        Target rootfs directory (installs to <rootfs>/lib/firmware)
  --sof-bin <dir>       Install versioned directories into a sof-bin release folder
  --version <ver>       Version suffix for installation (e.g. v2.14 -> sof-ipc4-tplg-v2.14)
  --ssh <user@host>     Deploy topologies over SSH/rsync to remote DUT (/lib/firmware/intel)
  --component <comp>    Component to install: all, ipc3, ipc4, dev (default: all)
  --dry-run             Show actions without modifying target files
  -h, --help            Display this help message

Examples:
  # Install locally to /lib/firmware/intel/{sof-tplg,sof-ipc4-tplg,sof-ace-tplg}:
  sudo $(basename "$0")

  # Stage into an NFS rootfs:
  $(basename "$0") --rootfs /srv/nfs/aphid-rootfs

  # Populate a sof-bin release directory:
  $(basename "$0") --sof-bin ../sof-bin/v2.14.x --version v2.14

  # Deploy directly to a DUT over SSH:
  $(basename "$0") --ssh root@aphid
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--build-dir)
		BUILD_DIR="$2"
		shift 2
		;;
	--dest)
		DEST_PREFIX="$2"
		shift 2
		;;
	--rootfs)
		ROOTFS="$2"
		shift 2
		;;
	--sof-bin)
		SOF_BIN_DIR="$2"
		shift 2
		;;
	--version)
		VERSION_TAG="$2"
		shift 2
		;;
	--ssh)
		SSH_TARGET="$2"
		shift 2
		;;
	--component)
		COMPONENT="$2"
		shift 2
		;;
	--dry-run)
		DRY_RUN=true
		shift
		;;
	-h|--help)
		usage
		exit 0
		;;
	*)
		echo "Unknown option: $1" >&2
		usage
		exit 1
		;;
	esac
done

if [[ ! -d "$BUILD_DIR" ]]; then
	echo "ERROR: Build directory '$BUILD_DIR' does not exist. Run ./scripts/build-topology.sh first." >&2
	exit 1
fi

VER_SUFFIX=""
if [[ -n "$VERSION_TAG" ]]; then
	VER_SUFFIX="-${VERSION_TAG#-}"
fi

install_to_intel_dir()
{
	local target_intel_dir="$1"
	local ver_sfx="$2"

	local ipc3_dir="${target_intel_dir}/sof-tplg${ver_sfx}"
	local ipc4_dir="${target_intel_dir}/sof-ipc4-tplg${ver_sfx}"
	local ace_link="${target_intel_dir}/sof-ace-tplg${ver_sfx}"

	if [[ "$COMPONENT" == "all" || "$COMPONENT" == "ipc3" ]]; then
		echo "Installing IPC3 topologies -> ${ipc3_dir}"
		if ! "$DRY_RUN"; then
			mkdir -p "${ipc3_dir}"
			if [[ -d "${BUILD_DIR}/topology1/production" ]]; then
				cp -af "${BUILD_DIR}/topology1/production/"*.tplg "${ipc3_dir}/" 2>/dev/null || true
			fi
			if [[ -d "${BUILD_DIR}/topology2/production/ipc3" ]]; then
				cp -af "${BUILD_DIR}/topology2/production/ipc3/"*.tplg "${ipc3_dir}/" 2>/dev/null || true
			fi
		fi
	fi

	if [[ "$COMPONENT" == "all" || "$COMPONENT" == "ipc4" ]]; then
		echo "Installing IPC4 topologies -> ${ipc4_dir} (symlink: $(basename "${ace_link}"))"
		if ! "$DRY_RUN"; then
			mkdir -p "${ipc4_dir}"
			if [[ -d "${BUILD_DIR}/topology2/production" ]]; then
				cp -af "${BUILD_DIR}/topology2/production/"*.tplg "${ipc4_dir}/"
			fi
			ln -sfn "sof-ipc4-tplg${ver_sfx}" "${ace_link}"
		fi
	fi

	if [[ "$COMPONENT" == "dev" ]]; then
		local dev_dir="${target_intel_dir}/sof-ipc4-tplg-dev${ver_sfx}"
		echo "Installing development topologies -> ${dev_dir}"
		if ! "$DRY_RUN"; then
			mkdir -p "${dev_dir}"
			if [[ -d "${BUILD_DIR}/topology2/development" ]]; then
				cp -af "${BUILD_DIR}/topology2/development/"*.tplg "${dev_dir}/"
			fi
		fi
	fi
}

if [[ -n "$SSH_TARGET" ]]; then
	STAGE_DIR="$(mktemp -d)"
	trap 'rm -rf "$STAGE_DIR"' EXIT
	install_to_intel_dir "$STAGE_DIR/intel" "$VER_SUFFIX"
	echo "Deploying staged topologies to ${SSH_TARGET}:${DEST_PREFIX}/intel/"
	if ! "$DRY_RUN"; then
		rsync -avL --links "$STAGE_DIR/intel/" "${SSH_TARGET}:${DEST_PREFIX}/intel/"
	fi
	exit 0
fi

if [[ -n "$SOF_BIN_DIR" ]]; then
	if [[ -z "$VER_SUFFIX" ]]; then
		echo "ERROR: --version <ver> is required when using --sof-bin" >&2
		exit 1
	fi
	install_to_intel_dir "$SOF_BIN_DIR" "$VER_SUFFIX"
	exit 0
fi

if [[ -n "$ROOTFS" ]]; then
	TARGET_BASE="${ROOTFS%/}${DEST_PREFIX}"
else
	TARGET_BASE="${DEST_PREFIX}"
fi

install_to_intel_dir "${TARGET_BASE}/intel" "$VER_SUFFIX"
echo "Topology installation complete."
