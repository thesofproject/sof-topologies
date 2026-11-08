# SPDX-License-Identifier: BSD-3-Clause
#
# ALSA Topology Compiler (alsatplg) discovery and build macros for sof-topology.

# Locate alsatplg in priority order:
# 1. -DALSATPLG_CMD=/path/to/alsatplg
# 2. $ENV{ALSATPLG_CMD} or $ENV{ALSATPLG}
# 3. Local workspace build (${SOF_WORKSPACE}/tools/bin/alsatplg or ../tools/bin/alsatplg)
# 4. System PATH via find_program()
if(NOT ALSATPLG_CMD)
	if(DEFINED ENV{ALSATPLG_CMD} AND EXISTS "$ENV{ALSATPLG_CMD}")
		set(ALSATPLG_CMD "$ENV{ALSATPLG_CMD}")
	elseif(DEFINED ENV{ALSATPLG} AND EXISTS "$ENV{ALSATPLG}")
		set(ALSATPLG_CMD "$ENV{ALSATPLG}")
	else()
		set(_alsa_candidates "")
		if(DEFINED ENV{SOF_WORKSPACE})
			list(APPEND _alsa_candidates "$ENV{SOF_WORKSPACE}/tools/bin/alsatplg")
		endif()
		list(APPEND _alsa_candidates
			"${PROJECT_SOURCE_DIR}/../tools/bin/alsatplg"
			"${CMAKE_CURRENT_LIST_DIR}/../../tools/bin/alsatplg"
		)
		if(DEFINED SOF_ROOT_SOURCE_DIRECTORY)
			list(APPEND _alsa_candidates "${SOF_ROOT_SOURCE_DIRECTORY}/../tools/bin/alsatplg")
		endif()
		foreach(_cand IN LISTS _alsa_candidates)
			if(EXISTS "${_cand}")
				get_filename_component(ALSATPLG_CMD "${_cand}" ABSOLUTE)
				break()
			endif()
		endforeach()
		if(NOT ALSATPLG_CMD)
			find_program(ALSATPLG_CMD NAMES alsatplg)
		endif()
	endif()
endif()

if(NOT ALSATPLG_CMD)
	set(ALSATPLG_CMD "alsatplg")
endif()

get_filename_component(_alsatplg_bin_dir "${ALSATPLG_CMD}" DIRECTORY)
if(_alsatplg_bin_dir AND EXISTS "${_alsatplg_bin_dir}/../lib")
	get_filename_component(SOF_ALSA_LIB_DIR "${_alsatplg_bin_dir}/../lib" ABSOLUTE)
else()
	set(SOF_ALSA_LIB_DIR "")
endif()

# With the Ninja generator, USES_TERMINAL forces the single-job "console"
# pool, serializing every topology build regardless of -j. Enable this
# option to force that serialized, easier to debug behavior back on.
option(TPLG_SEQUENTIAL_BUILD "Build topologies one at a time (for debugging)" OFF)
if(TPLG_SEQUENTIAL_BUILD)
	set(TPLG_USES_TERMINAL USES_TERMINAL)
else()
	set(TPLG_USES_TERMINAL "")
endif()

function(alsatplg_version OUT_STATUS OUT_VERSION)
	if(SOF_ALSA_LIB_DIR)
		execute_process(
			COMMAND ${CMAKE_COMMAND} -E env "LD_LIBRARY_PATH=${SOF_ALSA_LIB_DIR}:$ENV{LD_LIBRARY_PATH}" ${ALSATPLG_CMD} --version
			RESULT_VARIABLE status
			OUTPUT_VARIABLE stdout
			OUTPUT_STRIP_TRAILING_WHITESPACE
		)
	else()
		execute_process(
			COMMAND ${ALSATPLG_CMD} --version
			RESULT_VARIABLE status
			OUTPUT_VARIABLE stdout
			OUTPUT_STRIP_TRAILING_WHITESPACE
		)
	endif()
	message(DEBUG "${ALSATPLG_CMD} --version: status=${status}, output=${stdout}")

	set(${OUT_STATUS} "${status}" PARENT_SCOPE)

	if(NOT status EQUAL 0)
		message(WARNING "${ALSATPLG_CMD} --version returned status: ${status},\n${stdout}")
		return()
	endif()

	string(REPLACE "\n" ";" ALSA_VERSION_LIST "${stdout}")
	list(GET ALSA_VERSION_LIST 0 ALSATPLG_VERSION)
	string(REGEX MATCH "[0-9]\\.[0-9]\\.*[0-9]*" ALSATPLG_VERSION_NUMBER "${ALSATPLG_VERSION}")

	set(${OUT_VERSION} "${ALSATPLG_VERSION_NUMBER}" PARENT_SCOPE)
endfunction()

macro(add_alsatplg_command)
	add_custom_command(
		MAIN_DEPENDENCY ${ARGV0}
		OUTPUT ${ARGV1}
		COMMAND LD_LIBRARY_PATH=${SOF_ALSA_LIB_DIR}
		        ${ALSATPLG_CMD} \$\${VERBOSE:+-v 1} -c ${ARGV0} -o ${ARGV1}
		${TPLG_USES_TERMINAL}
	)
endmacro()

macro(add_alsatplg2_command conf_header conf_target input_name output_name include_path)
	if (${ARGC} GREATER 5)
		set (defines ${ARGV5})
	else()
		set (defines "")
	endif()

	add_custom_command(
		MAIN_DEPENDENCY ${input_name}.conf
		DEPENDS ${conf_header} ${conf_target}
		OUTPUT ${output_name}.tplg

		COMMAND cat ${conf_header} ${input_name}.conf > ${output_name}.conf

		# -p to pre-process Topology2.0 conf file
		COMMAND LD_LIBRARY_PATH=${SOF_ALSA_LIB_DIR}
		        ALSA_TOPOLOGY_PLUGIN_DIR=${SOF_ALSA_LIB_DIR}/alsa-topology
		        ALSA_CONFIG_DIR=${SOF_TOPOLOGY2_SOURCE_DIR}
		        ${ALSATPLG_CMD} \$\${VERBOSE:+-v 1}
		        -I ${include_path} -D "'${defines}'" -p -c ${output_name}.conf -o ${output_name}.tplg
		${TPLG_USES_TERMINAL}
	)
endmacro()
