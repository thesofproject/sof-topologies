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

ABI_MODE="${2:-ipc4}"

ABI_MAJOR=$(awk '/^ *# *define *SOF_ABI_MAJOR / { print $3 }' "$ABI_H")
ABI_MINOR=$(awk '/^ *# *define *SOF_ABI_MINOR / { print $3 }' "$ABI_H")
ABI_PATCH=$(awk '/^ *# *define *SOF_ABI_PATCH / { print $3 }' "$ABI_H")

cat <<EOF_HEADER
Object.Base.manifest.1 {
	name "sof_manifest"
	Object.Base.data.1 {
		name "SOF ABI"
EOF_HEADER

print_1byte()
{
	printf '0x%02x' "$(("$1" & 0xff))"
}

print_2bytes()
{
	printf '0x%02x,0x%02x' "$(("$1" & 0xff))" "$((("$1" & 0xff00) >> 8))"
}

printf '\t\tbytes\t\"'
for vers in $ABI_MAJOR $ABI_MINOR; do
	case "$ABI_MODE" in
		ipc3) print_1byte "$vers" ;;
		ipc4) print_2bytes "$vers" ;;
	esac
	printf ','
done

case "$ABI_MODE" in
	ipc3) print_1byte "$ABI_PATCH" ;;
	ipc4) print_2bytes "$ABI_PATCH" ;;
esac

printf '\"\n\t}\n}\n'
