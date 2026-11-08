# SPDX-License-Identifier: BSD-3-Clause

# 3.17 required: foreach(<loop_var>... IN ZIP_LISTS <lists>)
cmake_minimum_required(VERSION 3.17)

if(BUILD_DEV_TOPOLOGIES)
	set(_COPY_DEV_CMD sh -c "cp -a development/*.tplg \"${CMAKE_CURRENT_BINARY_DIR}/target/development/\"")
else()
	set(_COPY_DEV_CMD ${CMAKE_COMMAND} -E true)
endif()

add_custom_target(topologies2 ALL
    # Create directory structure to be provided for deployment
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/target/sof-ipc4-tplg
    COMMAND ${CMAKE_COMMAND} -E create_symlink sof-ipc4-tplg ${CMAKE_CURRENT_BINARY_DIR}/target/sof-ace-tplg
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/target/sof-tplg
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/target/development
    # copy the topology files only to target, preserving symbolic links
    COMMAND sh -c "cp -a production/*.tplg \"${CMAKE_CURRENT_BINARY_DIR}/target/sof-ipc4-tplg/\""
    COMMAND sh -c "cp -a production/ipc3/*.tplg \"${CMAKE_CURRENT_BINARY_DIR}/target/sof-tplg/\""
    COMMAND ${_COPY_DEV_CMD}
)

# Check alsatplg version and build topology2 if alsatplg version is
# 1.2.7 or greater, see https://github.com/thesofproject/sof/issues/5323
alsatplg_version(STATUS ALSATPLG_VERSION_NUMBER)

if(NOT STATUS EQUAL 0)
	message(WARNING "alsatplg error: ${STATUS}; topology2 will be skipped")
else()
	if(${ALSATPLG_VERSION_NUMBER} VERSION_LESS "1.2.7")
		message(WARNING "topology2 skipped. Minimum alsatplg version 1.2.7,\
 found ${ALSATPLG_VERSION_NUMBER}.")
	else()
		add_dependencies(topologies topologies2)
	endif()
endif()

# generate ABI for IPC4
add_custom_command(OUTPUT abi.conf
	COMMAND > abi.conf  ${CMAKE_CURRENT_SOURCE_DIR}/get_abi.sh ${SOF_ABI_HEADER} "ipc4"
	DEPENDS ${SOF_ABI_HEADER}
)
add_custom_target(abi_target
	DEPENDS abi.conf
)

# Atom platforms use IPC3 even when the source topology is written using the
# topology2 object model. Keep a separate ABI manifest so IPC3 and IPC4 output
# can be built together without changing the existing production topologies.
add_custom_command(OUTPUT abi-ipc3.conf
	COMMAND > abi-ipc3.conf ${CMAKE_CURRENT_SOURCE_DIR}/get_abi.sh
		${SOF_ABI_HEADER} "ipc3"
	DEPENDS ${SOF_ABI_HEADER}
)
add_custom_target(abi_ipc3_target
	DEPENDS abi-ipc3.conf
)

add_dependencies(topologies2 topology2_prod)
add_subdirectory(production)
if(BUILD_DEV_TOPOLOGIES)
	add_dependencies(topologies2 topology2_dev)
	add_subdirectory(development)
endif()
