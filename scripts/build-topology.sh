#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2018-2026 Intel Corporation. All rights reserved.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOF_TOPOLOGY_REPO="$(dirname "$SCRIPT_DIR")"
: "${BUILD_TPLG_DIR:=$SOF_TOPOLOGY_REPO/build}"
: "${NO_PROCESSORS:=$(nproc)}"

print_usage()
{
	cat <<EOFUSAGE

Configures, builds, and optionally installs or packages SOF topologies.
By default (no flags), builds all topology1 and topology2 targets.

usage: $0 [-T|-X|-1|-Y|-2|-t|-s|-A|-C|-L|-p|-i <dir>|-h]
       -h Display help

       -T Rebuild all topologies (topology1 + topology2)
       -X, -1 Rebuild topology1 only (legacy M4 IPC3)
       -Y, -2 Rebuild topology2 only (alsaconf v2 IPC4 & IPC3)
       -t Rebuild test/topology/ (or test/topology/tplg-build.sh directly)
       -s Force sequential (one at a time) topology builds for debugging
       -A Clone and rebuild local ALSA lib and utils (alsatplg)
       -C No build, only clean CMake re-configuration
       -L Mirror/symlink built outputs into ../sof/tools/build_tools/topology
          for backward compatibility with legacy CI/testbench scripts
       -p Package built topologies into RPM, DEB, and TGZ archives via CPack
       -i <dir> Install built topologies into <dir> (e.g. /lib/firmware)
EOFUSAGE
}

reconfigure_build()
{
	rm -rf "$BUILD_TPLG_DIR"
	mkdir -p "$BUILD_TPLG_DIR"

	cmake -GNinja -S "$SOF_TOPOLOGY_REPO" -B "$BUILD_TPLG_DIR" \
		-DTPLG_SEQUENTIAL_BUILD="$TPLG_SEQUENTIAL_BUILD"
}

update_sequential_build_option()
{
	cmake -S "$SOF_TOPOLOGY_REPO" -B "$BUILD_TPLG_DIR" \
		-DTPLG_SEQUENTIAL_BUILD="$TPLG_SEQUENTIAL_BUILD" >/dev/null
}

make_target()
{
	local target="$1"
	( set -x
	  # shellcheck disable=SC2086
	  cmake --build "$BUILD_TPLG_DIR" -- -j "$NO_PROCESSORS" $target
	)
}

sync_compat_links()
{
	local sof_repo="${SOF_WORKSPACE:+${SOF_WORKSPACE}/sof}"
	if [ -z "$sof_repo" ] || [ ! -d "$sof_repo" ]; then
		sof_repo="$(dirname "$SOF_TOPOLOGY_REPO")/sof"
	fi
	if [ ! -d "$sof_repo/tools" ]; then
		return 0
	fi

	local compat_base="$sof_repo/tools/build_tools"
	mkdir -p "$compat_base/topology" "$compat_base/test"

	if [ -d "$BUILD_TPLG_DIR/topology1" ]; then
		rm -rf "$compat_base/topology/topology1"
		ln -sfn "$BUILD_TPLG_DIR/topology1" "$compat_base/topology/topology1"
		cp -af "$BUILD_TPLG_DIR/topology1/production/"*.tplg "$compat_base/topology/" 2>/dev/null || true
	fi
	if [ -d "$BUILD_TPLG_DIR/topology2" ]; then
		rm -rf "$compat_base/topology/topology2"
		ln -sfn "$BUILD_TPLG_DIR/topology2" "$compat_base/topology/topology2"
	fi
	if [ -d "$BUILD_TPLG_DIR/test/topology" ]; then
		rm -rf "$compat_base/test/topology"
		ln -sfn "$BUILD_TPLG_DIR/test/topology" "$compat_base/test/topology"
	fi
	echo "Updated compatibility links in $compat_base"
}

main()
{
	local DO_BUILD_alsa=false
	local DO_BUILD_topologies1=false
	local DO_BUILD_topologies2=false
	local DO_BUILD_tests=false
	local CMAKE_ONLY=false
	local BUILD_ALL=false
	local DO_COMPAT_LINK=false
	local DO_PACKAGE=false
	local INSTALL_DIR=""
	local TPLG_SEQUENTIAL_BUILD=OFF

	if [ $# -eq 0 ]; then
		BUILD_ALL=true
	fi

	while getopts "hTX1Y2tsACLpi:" OPTION; do
		case "$OPTION" in
		T) DO_BUILD_topologies1=true ; DO_BUILD_topologies2=true ;;
		X|1) DO_BUILD_topologies1=true ;;
		Y|2) DO_BUILD_topologies2=true ;;
		t) DO_BUILD_tests=true ;;
		s) TPLG_SEQUENTIAL_BUILD=ON ;;
		A) DO_BUILD_alsa=true ;;
		C) CMAKE_ONLY=true ;;
		L) DO_COMPAT_LINK=true ;;
		p) DO_PACKAGE=true ;;
		i) INSTALL_DIR="$OPTARG" ;;
		h) print_usage; exit 0 ;;
		*) print_usage; exit 1 ;;
		esac
	done
	shift "$((OPTIND - 1))"

	if ! "$DO_BUILD_topologies1" && ! "$DO_BUILD_topologies2" && ! "$DO_BUILD_tests" && ! "$CMAKE_ONLY" && ! "$DO_BUILD_alsa"; then
		BUILD_ALL=true
	fi

	if "$DO_BUILD_alsa"; then
		"$SCRIPT_DIR/build-alsa-tools.sh"
		if ! "$DO_BUILD_topologies1" && ! "$DO_BUILD_topologies2" && ! "$DO_BUILD_tests" && ! "$BUILD_ALL"; then
			exit 0
		fi
	fi

	if "$CMAKE_ONLY"; then
		reconfigure_build
		exit 0
	fi

	if [ ! -e "$BUILD_TPLG_DIR/build.ninja" ] && [ ! -e "$BUILD_TPLG_DIR/Makefile" ]; then
		reconfigure_build
	else
		update_sequential_build_option
	fi

	if "$BUILD_ALL"; then
		make_target ""
	else
		for target in topologies1 topologies2 tests; do
			if eval "\$DO_BUILD_$target"; then
				make_target "$target"
			fi
		done
	fi

	if "$DO_COMPAT_LINK"; then
		sync_compat_links
	fi

	if [ -n "$INSTALL_DIR" ]; then
		cmake --install "$BUILD_TPLG_DIR" --prefix "$INSTALL_DIR"
	fi

	if "$DO_PACKAGE"; then
		( cd "$BUILD_TPLG_DIR" && cpack )
	fi
}

main "$@"
