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

set(SOF_PACKAGE_VERSION "${SOF_ABI_VERSION_STRING}" CACHE STRING "Package version for RPM/DEB/TGZ artifacts")
if(SOF_PACKAGE_VERSION MATCHES "^([0-9]+)\\.([0-9]+)\\.([0-9]+)")
	set(SOF_PKG_VERSION_MAJOR "${CMAKE_MATCH_1}")
	set(SOF_PKG_VERSION_MINOR "${CMAKE_MATCH_2}")
	set(SOF_PKG_VERSION_PATCH "${CMAKE_MATCH_3}")
else()
	set(SOF_PKG_VERSION_MAJOR "${SOF_ABI_MAJOR}")
	set(SOF_PKG_VERSION_MINOR "${SOF_ABI_MINOR}")
	set(SOF_PKG_VERSION_PATCH "${SOF_ABI_PATCH}")
endif()

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

set(_tplg_file_perms OWNER_READ OWNER_WRITE GROUP_READ WORLD_READ)
set(_tplg_dir_perms OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)
set(CMAKE_INSTALL_DEFAULT_DIRECTORY_PERMISSIONS ${_tplg_dir_perms})

if(BUILD_TOPOLOGY1)
	install(
		DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/topology1/production/"
		DESTINATION "${_ipc3_dest}"
		COMPONENT ipc3-prod
		FILE_PERMISSIONS ${_tplg_file_perms}
		DIRECTORY_PERMISSIONS ${_tplg_dir_perms}
		FILES_MATCHING
		PATTERN "CMakeFiles" EXCLUDE
		PATTERN "*.tplg"
	)
endif()

if(BUILD_TOPOLOGY2)
	install(
		DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/topology2/production/ipc3/"
		DESTINATION "${_ipc3_dest}"
		COMPONENT ipc3-prod
		FILE_PERMISSIONS ${_tplg_file_perms}
		DIRECTORY_PERMISSIONS ${_tplg_dir_perms}
		FILES_MATCHING
		PATTERN "CMakeFiles" EXCLUDE
		PATTERN "*.tplg"
	)
	install(
		DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/topology2/production/"
		DESTINATION "${_ipc4_dest}"
		COMPONENT ipc4-prod
		FILE_PERMISSIONS ${_tplg_file_perms}
		DIRECTORY_PERMISSIONS ${_tplg_dir_perms}
		FILES_MATCHING
		PATTERN "CMakeFiles" EXCLUDE
		PATTERN "ipc3" EXCLUDE
		PATTERN "*.tplg"
	)
	# Create sof-ace-tplg -> sof-ipc4-tplg symlink in build dir and install it
	execute_process(
		COMMAND "${CMAKE_COMMAND}" -E create_symlink "${_ipc4_dir_name}" "${CMAKE_CURRENT_BINARY_DIR}/${_ace_link_name}"
	)
	install(
		FILES "${CMAKE_CURRENT_BINARY_DIR}/${_ace_link_name}"
		DESTINATION "${_install_base}"
		COMPONENT ipc4-prod
	)

	if(BUILD_DEV_TOPOLOGIES)
		install(
			DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/topology2/development/"
			DESTINATION "${_install_base}/sof-ipc4-tplg-dev${SOF_TPLG_VERSION_SUFFIX}"
			COMPONENT dev
			EXCLUDE_FROM_ALL
			FILE_PERMISSIONS ${_tplg_file_perms}
			DIRECTORY_PERMISSIONS ${_tplg_dir_perms}
			FILES_MATCHING
			PATTERN "CMakeFiles" EXCLUDE
			PATTERN "*.tplg"
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
	add_test(
		NAME validate_packages
		COMMAND ${Python3_EXECUTABLE} "${PROJECT_SOURCE_DIR}/tools/validate-package.py"
		        --build-dir "${CMAKE_CURRENT_BINARY_DIR}"
		        --abi-header "${SOF_ABI_HEADER}"
		        --expected-version "${SOF_PACKAGE_VERSION}"
		        --install-prefix "${CMAKE_INSTALL_PREFIX}"
		        --vendor-dir "${SOF_TPLG_INSTALL_VENDOR_DIR}"
		        --version-suffix "${SOF_TPLG_VERSION_SUFFIX}"
	)
endif()

# ---------------------------------------------------------------------------
# Packaging Support (cpack / make deb / make rpm / make packages)
# ---------------------------------------------------------------------------
set(CPACK_PACKAGE_NAME "sof-topology")
set(CPACK_PACKAGE_VENDOR "Sound Open Firmware Project")
set(CPACK_PACKAGE_CONTACT "Sound Open Firmware Project <sof-devel@alsa-project.org>")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "SOF ALSA Topology Binaries (IPC3 & IPC4) - ABI ${SOF_ABI_VERSION_STRING}")
set(CPACK_PACKAGE_DESCRIPTION "Sound Open Firmware (SOF) pre-compiled ALSA topology binaries for IPC3 and IPC4 platforms (SOF ABI ${SOF_ABI_VERSION_STRING}).")
set(CPACK_PACKAGE_VERSION "${SOF_PACKAGE_VERSION}")
set(CPACK_PACKAGE_VERSION_MAJOR "${SOF_PKG_VERSION_MAJOR}")
set(CPACK_PACKAGE_VERSION_MINOR "${SOF_PKG_VERSION_MINOR}")
set(CPACK_PACKAGE_VERSION_PATCH "${SOF_PKG_VERSION_PATCH}")
set(CPACK_PACKAGE_RELEASE "1")
set(CPACK_PACKAGING_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")
set(CPACK_RESOURCE_FILE_LICENSE "${PROJECT_SOURCE_DIR}/LICENSE")

# Debian (.deb) package settings
set(CPACK_DEBIAN_PACKAGE_NAME "sof-topology")
set(CPACK_DEBIAN_PACKAGE_ARCHITECTURE "all")
set(CPACK_DEBIAN_PACKAGE_SECTION "kernel")
set(CPACK_DEBIAN_PACKAGE_PRIORITY "optional")
set(CPACK_DEBIAN_PACKAGE_HOMEPAGE "https://github.com/thesofproject/sof-topologies")
set(CPACK_DEBIAN_PACKAGE_CONTROL_STRICT_PERMISSION TRUE)
set(CPACK_DEBIAN_FILE_NAME "DEB-DEFAULT")

# RPM (.rpm) package settings
set(CPACK_RPM_PACKAGE_NAME "sof-topology")
set(CPACK_RPM_PACKAGE_ARCHITECTURE "noarch")
set(CPACK_RPM_PACKAGE_RELEASE "${CPACK_PACKAGE_RELEASE}")
set(CPACK_RPM_PACKAGE_LICENSE "BSD-3-Clause")
set(CPACK_RPM_PACKAGE_GROUP "System Environment/Kernel")
set(CPACK_RPM_PACKAGE_URL "https://github.com/thesofproject/sof-topologies")
set(CPACK_RPM_PACKAGE_DESCRIPTION "${CPACK_PACKAGE_DESCRIPTION}")
set(CPACK_RPM_DEFAULT_DIR_PERMISSIONS ${_tplg_dir_perms})
set(CPACK_RPM_DEFAULT_FILE_PERMISSIONS ${_tplg_file_perms})
set(CPACK_RPM_PACKAGE_AUTOREQ "no")
set(CPACK_RPM_PACKAGE_AUTOPROV "no")
set(CPACK_RPM_FILE_NAME "RPM-DEFAULT")
list(APPEND CPACK_RPM_EXCLUDE_FROM_AUTO_FILELIST_ADDITION
	"/lib"
	"/lib/firmware"
	"${CMAKE_INSTALL_PREFIX}"
)

set(CPACK_GENERATOR "TGZ;DEB;RPM" CACHE STRING "Default CPack package generators")
include(CPack)

add_custom_target(package-deb
	COMMAND "${CMAKE_CPACK_COMMAND}" -G DEB
	WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}"
	DEPENDS topologies
	COMMENT "Building DEB package with pre-compiled SOF topologies"
)

add_custom_target(package-rpm
	COMMAND "${CMAKE_CPACK_COMMAND}" -G RPM
	WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}"
	DEPENDS topologies
	COMMENT "Building RPM package with pre-compiled SOF topologies"
)

add_custom_target(package-tgz
	COMMAND "${CMAKE_CPACK_COMMAND}" -G TGZ
	WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}"
	DEPENDS topologies
	COMMENT "Building TGZ archive with pre-compiled SOF topologies"
)

add_custom_target(deb DEPENDS package-deb)
add_custom_target(rpm DEPENDS package-rpm)
add_custom_target(packages
	COMMAND "${CMAKE_CPACK_COMMAND}" -G "DEB;RPM;TGZ"
	WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}"
	DEPENDS topologies
	VERBATIM
	COMMENT "Building DEB, RPM, and TGZ packages with pre-compiled SOF topologies"
)
