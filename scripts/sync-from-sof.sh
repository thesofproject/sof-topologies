#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2026 Intel Corporation. All rights reserved.
#
# Synchronize topology definitions and ABI headers between the `sof` repository
# and `sof-topology` during the CI transition period.
#
# Preserves sof-topology's standalone CMake and get_abi.sh enhancements while
# syncing all .m4, .conf, .cmake target lists, and kernel/abi.h updates.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOF_TOPOLOGY_REPO="$(dirname "$SCRIPT_DIR")"

if [[ -n "${SOF_REPO:-}" && -d "${SOF_REPO}" ]]; then
	SOF_SRC="${SOF_REPO}"
elif [[ -n "${SOF_WORKSPACE:-}" && -d "${SOF_WORKSPACE}/sof" ]]; then
	SOF_SRC="${SOF_WORKSPACE}/sof"
elif [[ -d "$(dirname "$SOF_TOPOLOGY_REPO")/sof" ]]; then
	SOF_SRC="$(dirname "$SOF_TOPOLOGY_REPO")/sof"
else
	echo "ERROR: Cannot locate 'sof' repository. Set SOF_REPO=/path/to/sof" >&2
	exit 1
fi

MODE="pull"
DRY_RUN=false
CHECK_ONLY=false

usage()
{
	cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --sof-repo <dir>   Path to sof repository (default: $SOF_SRC)
  --pull             Sync from sof -> sof-topology (default)
  --push             Sync from sof-topology -> sof
  --dry-run          Show what files would be updated without modifying them
  --check            Exit with non-zero status if topology sources are out of sync
  -h, --help         Display this help message
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--sof-repo)
		SOF_SRC="$2"
		shift 2
		;;
	--pull)
		MODE="pull"
		shift
		;;
	--push)
		MODE="push"
		shift
		;;
	--dry-run)
		DRY_RUN=true
		shift
		;;
	--check)
		CHECK_ONLY=true
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

RSYNC_OPTS=(-a --delete
	--exclude="CMakeLists.txt"
	--exclude="get_abi.sh"
	--exclude="tplg-build.sh"
)
if "$DRY_RUN"; then
	RSYNC_OPTS+=(-n -i)
fi

sync_pair()
{
	local src="$1"
	local dst="$2"
	rsync "${RSYNC_OPTS[@]}" "$src" "$dst"
}

if [[ "$MODE" == "pull" ]]; then
	echo "Syncing topology sources from $SOF_SRC -> $SOF_TOPOLOGY_REPO ..."
	OUT1=$(sync_pair "$SOF_SRC/tools/topology/topology1/" "$SOF_TOPOLOGY_REPO/topology1/")
	OUT2=$(sync_pair "$SOF_SRC/tools/topology/topology2/" "$SOF_TOPOLOGY_REPO/topology2/")
	OUT3=$(sync_pair "$SOF_SRC/tools/test/topology/" "$SOF_TOPOLOGY_REPO/test/topology/")
	OUT4=$(rsync $( "$DRY_RUN" && echo "-n -i" ) -a "$SOF_SRC/src/include/kernel/abi.h" "$SOF_TOPOLOGY_REPO/include/kernel/abi.h")
	# Also sync topology1/CMakeLists.txt TPLGS list if changed (keeping ${SOF_ABI_HEADER})
	COMBINED="${OUT1}${OUT2}${OUT3}${OUT4}"
	if [[ -n "$COMBINED" ]]; then
		echo "$COMBINED"
		if "$CHECK_ONLY"; then
			echo "ERROR: sof-topology is out of sync with $SOF_SRC" >&2
			exit 1
		fi
	else
		echo "All topology sources and ABI header are in sync."
	fi
	if ! "$DRY_RUN" && git -C "$SOF_SRC" rev-parse HEAD >/dev/null 2>&1; then
		git -C "$SOF_SRC" rev-parse HEAD > "$SOF_TOPOLOGY_REPO/.sof-sync-commit"
	fi
else
	echo "Syncing topology sources from $SOF_TOPOLOGY_REPO -> $SOF_SRC ..."
	sync_pair "$SOF_TOPOLOGY_REPO/topology1/" "$SOF_SRC/tools/topology/topology1/"
	sync_pair "$SOF_TOPOLOGY_REPO/topology2/" "$SOF_SRC/tools/topology/topology2/"
	sync_pair "$SOF_TOPOLOGY_REPO/test/topology/" "$SOF_SRC/tools/test/topology/"
fi
