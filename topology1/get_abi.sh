#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2019 Intel Corporation. All rights reserved.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -n "$1" ] && [ -f "$1" ]; then
	ABI_H="$1"
elif [ -n "$1" ] && [ -f "$1/include/kernel/abi.h" ]; then
	ABI_H="$1/include/kernel/abi.h"
elif [ -n "$1" ] && [ -f "$1/src/include/kernel/abi.h" ]; then
	ABI_H="$1/src/include/kernel/abi.h"
elif [ -f "${SCRIPT_DIR}/../include/kernel/abi.h" ]; then
	ABI_H="${SCRIPT_DIR}/../include/kernel/abi.h"
elif [ -f "${SCRIPT_DIR}/../../../src/include/kernel/abi.h" ]; then
	ABI_H="${SCRIPT_DIR}/../../../src/include/kernel/abi.h"
else
	echo "ERROR: Cannot find kernel/abi.h (arg: ${1:-<none>})" >&2
	exit 1
fi

MAJOR=$(grep '#define SOF_ABI_MAJOR ' "$ABI_H" | grep -E ".[[:digit:]]$" -o)
MINOR=$(grep '#define SOF_ABI_MINOR ' "$ABI_H" | grep -E ".[[:digit:]]$" -o)
PATCH=$(grep '#define SOF_ABI_PATCH ' "$ABI_H" | grep -E ".[[:digit:]]$" -o)
MAJOR_SHIFT=$(grep '#define SOF_ABI_MAJOR_SHIFT' "$ABI_H" | grep -E ".[[:digit:]]$" -o)
MINOR_SHIFT=$(grep '#define SOF_ABI_MINOR_SHIFT' "$ABI_H" | grep -E ".[[:digit:]]$" -o)

major_val=$((MAJOR << MAJOR_SHIFT))
minor_val=$((MINOR << MINOR_SHIFT))
abi_version_3_8=$((3 << MAJOR_SHIFT | 8 << MINOR_SHIFT))
abi_version=$((major_val | minor_val))
abi_version_3_9_or_greater=$((abi_version > abi_version_3_8))
abi_version_3_17=$((3 << MAJOR_SHIFT | 17 << MINOR_SHIFT))
abi_version_3_17_or_greater=$((abi_version >= abi_version_3_17))

printf "define(\`SOF_ABI_MAJOR', \`0x%02x')\n" $MAJOR > abi.h
printf "define(\`SOF_ABI_MINOR', \`0x%02x')\n" $MINOR >> abi.h
printf "define(\`SOF_ABI_PATCH', \`0x%02x')\n" $PATCH >> abi.h
printf "define(\`SOF_ABI_VERSION', \`0x%x')\n" $abi_version >> abi.h
printf "define(\`SOF_ABI_VERSION_3_9_OR_GRT', \`%d')\n" \
	$abi_version_3_9_or_greater >> abi.h
printf "define(\`SOF_ABI_VERSION_3_17_OR_GRT', \`%d')\n" \
	$abi_version_3_17_or_greater >> abi.h
