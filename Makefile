# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2026 Intel Corporation. All rights reserved.
#
# Top-level Makefile for building, testing, installing, and packaging
# SOF topologies into RPM, DEB, and TGZ archives.

BUILD_DIR ?= $(CURDIR)/build
PREFIX ?= /lib/firmware
CMAKE_GENERATOR ?= Ninja
JOBS ?= $(shell nproc 2>/dev/null || echo 4)
CMAKE_ARGS ?=

.PHONY: all build configure topology1 topology2 tests \
        package packages rpm deb tgz package-rpm package-deb package-tgz \
        test check test-packages validate-packages install clean distclean help

all: build

configure:
	@if [ ! -f "$(BUILD_DIR)/CMakeCache.txt" ]; then \
		cmake -G "$(CMAKE_GENERATOR)" -S "$(CURDIR)" -B "$(BUILD_DIR)" \
			-DCMAKE_INSTALL_PREFIX="$(PREFIX)" $(CMAKE_ARGS); \
	fi

build: configure
	cmake --build "$(BUILD_DIR)" -j "$(JOBS)"

topology1: configure
	cmake --build "$(BUILD_DIR)" --target topologies1 -j "$(JOBS)"

topology2: configure
	cmake --build "$(BUILD_DIR)" --target topologies2 -j "$(JOBS)"

tests: configure
	cmake --build "$(BUILD_DIR)" --target tests -j "$(JOBS)"

rpm package-rpm: configure
	cmake --build "$(BUILD_DIR)" --target package-rpm -j "$(JOBS)"

deb package-deb: configure
	cmake --build "$(BUILD_DIR)" --target package-deb -j "$(JOBS)"

tgz package-tgz: configure
	cmake --build "$(BUILD_DIR)" --target package-tgz -j "$(JOBS)"

package packages: configure
	cmake --build "$(BUILD_DIR)" --target packages -j "$(JOBS)"

test-packages validate-packages: packages
	ctest --test-dir "$(BUILD_DIR)" --output-on-failure -V -R validate_packages

test check: packages
	ctest --test-dir "$(BUILD_DIR)" --output-on-failure

install: build
	DESTDIR="$(DESTDIR)" cmake --install "$(BUILD_DIR)" --prefix "$(PREFIX)"

clean distclean:
	$(RM) -r "$(BUILD_DIR)"

help:
	@echo "SOF Topologies Make Targets:"
	@echo "  make [all|build]        - Configure and build all production/dev topologies"
	@echo "  make package[s]         - Build RPM, DEB, and TGZ packages with pre-compiled topologies"
	@echo "  make rpm                - Build RPM (.noarch.rpm) package with pre-compiled topologies"
	@echo "  make deb                - Build Debian (.deb) package with pre-compiled topologies"
	@echo "  make tgz                - Build tarball (.tar.gz) package with pre-compiled topologies"
	@echo "  make test / make check  - Build packages and run all topology & package validation tests"
	@echo "  make validate-packages  - Build and validate RPM/DEB/TGZ paths, permissions, versions, and symlinks"
	@echo "  make install            - Install topologies to [DESTDIR=...] [PREFIX=/lib/firmware]"
	@echo "  make clean              - Remove $(BUILD_DIR)"
