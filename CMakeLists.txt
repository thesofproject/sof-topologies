# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.17)

if("${CMAKE_CURRENT_SOURCE_DIR}" STREQUAL "${CMAKE_CURRENT_BINARY_DIR}")
	message(FATAL_ERROR
		" In-source builds are not supported.\n"
		" Please remove CMakeCache.txt and the CMakeFiles directory.\n"
		" Then specify a build directory. Example: cmake -Bbuild ..."
	)
endif()

project(SOF_TOPOLOGY NONE)

option(BUILD_TOPOLOGY1 "Build legacy M4-based v1 (IPC3) topologies" ON)
option(BUILD_TOPOLOGY2 "Build class-based v2 (IPC4 & IPC3) topologies" ON)
option(BUILD_DEV_TOPOLOGIES "Build development and benchmark topologies" ON)
option(BUILD_TEST_TOPOLOGIES "Build test/topology matrix by default" OFF)

set(SOF_TPLG_VERSION_SUFFIX "" CACHE STRING "Optional version suffix for installed topology directories (e.g. -v2.14)")
set(SOF_TPLG_INSTALL_VENDOR_DIR "intel" CACHE STRING "Subdirectory under CMAKE_INSTALL_PREFIX for installed topologies")

if(CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT)
	set(CMAKE_INSTALL_PREFIX "/lib/firmware" CACHE PATH "Default firmware install prefix" FORCE)
endif()

# Resolve SOF ABI header (include/kernel/abi.h)
# 1. Explicit -DSOF_ABI_HEADER=/path/to/abi.h
# 2. External SOF checkout via -DSOF_ROOT_SOURCE_DIRECTORY=/path/to/sof
# 3. Local standalone copy in ${PROJECT_SOURCE_DIR}/include/kernel/abi.h
if(NOT SOF_ABI_HEADER)
	if(DEFINED SOF_ROOT_SOURCE_DIRECTORY AND EXISTS "${SOF_ROOT_SOURCE_DIRECTORY}/src/include/kernel/abi.h")
		set(SOF_ABI_HEADER "${SOF_ROOT_SOURCE_DIRECTORY}/src/include/kernel/abi.h")
	else()
		set(SOF_ABI_HEADER "${PROJECT_SOURCE_DIR}/include/kernel/abi.h")
	endif()
endif()
get_filename_component(SOF_ABI_HEADER "${SOF_ABI_HEADER}" ABSOLUTE)
message(STATUS "Using SOF ABI header: ${SOF_ABI_HEADER}")

# Parse ABI version from header for packaging metadata
file(READ "${SOF_ABI_HEADER}" _abi_contents)
string(REGEX MATCH "#define[ \t]+SOF_ABI_MAJOR[ \t]+([0-9]+)" _ "${_abi_contents}")
set(SOF_ABI_MAJOR "${CMAKE_MATCH_1}")
string(REGEX MATCH "#define[ \t]+SOF_ABI_MINOR[ \t]+([0-9]+)" _ "${_abi_contents}")
set(SOF_ABI_MINOR "${CMAKE_MATCH_1}")
string(REGEX MATCH "#define[ \t]+SOF_ABI_PATCH[ \t]+([0-9]+)" _ "${_abi_contents}")
set(SOF_ABI_PATCH "${CMAKE_MATCH_1}")
set(SOF_ABI_VERSION_STRING "${SOF_ABI_MAJOR}.${SOF_ABI_MINOR}.${SOF_ABI_PATCH}")
message(STATUS "SOF Topology ABI version: ${SOF_ABI_VERSION_STRING}")

set(SOF_TOPOLOGY_BINARY_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
set(SOF_TOPOLOGY1_SOURCE_DIR "${PROJECT_SOURCE_DIR}/topology1")
set(SOF_TOPOLOGY2_SOURCE_DIR "${PROJECT_SOURCE_DIR}/topology2")

include("${PROJECT_SOURCE_DIR}/cmake/alsatplg.cmake")

alsatplg_version(STATUS ALSATPLG_VERSION_NUMBER)
if(NOT STATUS EQUAL 0)
	message(WARNING "${ALSATPLG_CMD} failed: ${STATUS}; all topologies skipped")
	return()
else()
	if(${ALSATPLG_VERSION_NUMBER} VERSION_LESS "1.2.5")
		message(WARNING "All topologies skipped: minimum alsatplg version 1.2.5, found ${ALSATPLG_VERSION_NUMBER}.")
		return()
	endif()
	message(STATUS "alsatplg: ${ALSATPLG_CMD} (version ${ALSATPLG_VERSION_NUMBER})")
endif()

add_custom_target(topologies ALL)

if(BUILD_TOPOLOGY1)
	add_dependencies(topologies topologies1)
	add_subdirectory(topology1)
endif()

if(BUILD_TOPOLOGY2)
	add_subdirectory(topology2)
endif()

add_subdirectory(test)

# ---------------------------------------------------------------------------
# Installation Support (cmake --install <build_dir> [--prefix /lib/firmware])
# ---------------------------------------------------------------------------
set(_install_base "${SOF_TPLG_INSTALL_VENDOR_DIR}")
set(_ipc3_dest "${_install_base}/sof-tplg${SOF_TPLG_VERSION_SUFFIX}")
set(_ipc4_dest "${_install_base}/sof-ipc4-tplg${SOF_TPLG_VERSION_SUFFIX}")
set(_ace_link_name "sof-ace-tplg${SOF_TPLG_VERSION_SUFFIX}")
set(_ipc4_dir_name "sof-ipc4-tplg${SOF_TPLG_VERSION_SUFFIX}")

if(BUILD_TOPOLOGY1)
	install(
		DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/topology1/production/"
		DESTINATION "${_ipc3_dest}"
		COMPONENT ipc3-prod
		FILES_MATCHING PATTERN "*.tplg"
	)
endif()

if(BUILD_TOPOLOGY2)
	install(
		DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/topology2/production/ipc3/"
		DESTINATION "${_ipc3_dest}"
		COMPONENT ipc3-prod
		FILES_MATCHING PATTERN "*.tplg"
	)
	install(
		DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/topology2/production/"
		DESTINATION "${_ipc4_dest}"
		COMPONENT ipc4-prod
		FILES_MATCHING
		PATTERN "ipc3" EXCLUDE
		PATTERN "*.tplg"
	)
	# Create sof-ace-tplg -> sof-ipc4-tplg symlink on install
	install(CODE "
		set(_dest_dir \"\$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}/${_install_base}\")
		file(MAKE_DIRECTORY \"\${_dest_dir}\")
		execute_process(
			COMMAND \"${CMAKE_COMMAND}\" -E create_symlink \"${_ipc4_dir_name}\" \"\${_dest_dir}/${_ace_link_name}\"
		)
	" COMPONENT ipc4-prod)

	if(BUILD_DEV_TOPOLOGIES)
		install(
			DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/topology2/development/"
			DESTINATION "${_install_base}/sof-ipc4-tplg-dev${SOF_TPLG_VERSION_SUFFIX}"
			COMPONENT dev
			EXCLUDE_FROM_ALL
			FILES_MATCHING PATTERN "*.tplg"
		)
	endif()
endif()

# ---------------------------------------------------------------------------
# Testing / Validation Support (ctest --test-dir <build_dir>)
# ---------------------------------------------------------------------------
enable_testing()
find_package(Python3 COMPONENTS Interpreter QUIET)
if(Python3_Interpreter_FOUND)
	if(BUILD_TOPOLOGY1)
		add_test(
			NAME validate_topology1_prod
			COMMAND ${Python3_EXECUTABLE} "${PROJECT_SOURCE_DIR}/tools/validate-tplg.py"
			        "${CMAKE_CURRENT_BINARY_DIR}/topology1/production"
		)
		add_test(
			NAME validate_topology1_pcm_parse
			COMMAND ${Python3_EXECUTABLE} "${PROJECT_SOURCE_DIR}/tools/tplgtool2.py"
			        -d pcm -t "${CMAKE_CURRENT_BINARY_DIR}/topology1/production" "*.tplg"
		)
	endif()
	if(BUILD_TOPOLOGY2)
		add_test(
			NAME validate_topology2_prod
			COMMAND ${Python3_EXECUTABLE} "${PROJECT_SOURCE_DIR}/tools/validate-tplg.py"
			        "${CMAKE_CURRENT_BINARY_DIR}/topology2/production"
			        "${CMAKE_CURRENT_BINARY_DIR}/topology2/production/ipc3"
		)
		if(BUILD_DEV_TOPOLOGIES)
			add_test(
				NAME validate_topology2_dev
				COMMAND ${Python3_EXECUTABLE} "${PROJECT_SOURCE_DIR}/tools/validate-tplg.py"
				        "${CMAKE_CURRENT_BINARY_DIR}/topology2/development"
			)
		endif()
	endif()
endif()

# ---------------------------------------------------------------------------
# Packaging Support (cpack / ninja package)
# ---------------------------------------------------------------------------
set(CPACK_PACKAGE_NAME "sof-topology")
set(CPACK_PACKAGE_VENDOR "Sound Open Firmware Project")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "SOF ALSA Topology Binaries (IPC3 & IPC4)")
set(CPACK_PACKAGE_VERSION_MAJOR "${SOF_ABI_MAJOR}")
set(CPACK_PACKAGE_VERSION_MINOR "${SOF_ABI_MINOR}")
set(CPACK_PACKAGE_VERSION_PATCH "${SOF_ABI_PATCH}")
set(CPACK_GENERATOR "TGZ")
include(CPack)
