#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2025 Intel Corporation. All rights reserved.

# fail immediately on any errors
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Array of ALSA Git repository URLs.
declare -a REPOS=(
    "https://github.com/thesofproject/alsa-lib.git"
    "https://github.com/thesofproject/alsa-utils.git"
)

# Pinned commit IDs
declare -a COMMIT_ID=(
    "08b532cd3da9ac8f683bcb4e4beb9b74c39c1782"
    "9feb22ba45b48729729c8d194aaf1bc082a6842a"
)

# Directory where repositories and tools/ will be cloned/installed.
if [[ -n "${SOF_WORKSPACE:-}" ]]; then
    BASE_DIR="$SOF_WORKSPACE"
elif [[ -d "$(dirname "$REPO_ROOT")/sof" ]]; then
    BASE_DIR="$(dirname "$REPO_ROOT")"
else
    BASE_DIR="$(dirname "$REPO_ROOT")"
fi

declare -a CONFIGURE_ARGS=(
    "--prefix=${BASE_DIR}/tools"
    "--prefix=${BASE_DIR}/tools \
        --with-alsa-prefix=${BASE_DIR}/tools \
        --with-alsa-inc-prefix=${BASE_DIR}/tools/include \
        --with-sysroot=${BASE_DIR}/tools \
        --with-udev-rules-dir=${BASE_DIR}/tools \
        PKG_CONFIG_PATH=${BASE_DIR}/tools \
        LDFLAGS=-L${BASE_DIR}/tools/lib \
        --with-asound-state-dir=${BASE_DIR}/tools/var/lib/alsa \
        --with-systemdsystemunitdir=${BASE_DIR}/tools/lib/systemd/system"
)

declare -a TARGET_ARGS=(
    "--disable-old-symbols"
    "--enable-alsatopology"
)

check_commit() {
    local repo_dir="$1"
    local commit_id="$2"

    if [ -z "$commit_id" ]; then
        return 0
    fi

    if ! git -C "$repo_dir" rev-parse --quiet --verify "$commit_id" >/dev/null 2>&1; then
        return 1
    else
        return 0
    fi
}

update_repo() {
    local repo_dir="$1"
    echo "Updating repository: $repo_dir"
    git -C "$repo_dir" fetch --all
    git -C "$repo_dir" pull
}

build_and_install() {
    local repo_dir="$1"
    local configure_args="$2"
    local target_args="$3"

    echo "Building and installing: $repo_dir $configure_args $target_args"

    if [ ! -f "$repo_dir/gitcompile" ]; then
        echo "Error: gitcompile not found in $repo_dir" >&2
        exit 1
    fi

    if [ ! -f "$repo_dir/Makefile" ]; then
        # shellcheck disable=SC2086
        (cd "$repo_dir" && ./gitcompile $configure_args $target_args) || \
            { echo "configure failed in $repo_dir"; exit 1; }
    else
        (cd "$repo_dir" && make -j"$(nproc)") || { echo "make failed in $repo_dir"; exit 1; }
    fi

    (cd "$repo_dir" && make install) || { echo "make install failed in $repo_dir"; exit 1; }

    echo "Build and installation complete for $repo_dir"
}

mkdir -p "$BASE_DIR"

for ((i = 0; i < ${#REPOS[@]}; i++)); do
    repo_url=${REPOS[i]}
    repo_name=$(basename "$repo_url" .git)
    repo_dir="$BASE_DIR/$repo_name"

    if [ ! -d "$repo_dir" ]; then
        echo "Cloning repository: $repo_url"
        git clone "$repo_url" "$repo_dir" || { echo "git clone failed for $repo_url"; exit 1; }
    elif ! check_commit "$repo_dir" "${COMMIT_ID[i]}"; then
        update_repo "$repo_dir"
    else
        echo "Repository $repo_name is up to date."
    fi

    build_and_install "$repo_dir" "${CONFIGURE_ARGS[i]}" "${TARGET_ARGS[i]}"
done

echo "All ALSA repositories processed into ${BASE_DIR}/tools."
