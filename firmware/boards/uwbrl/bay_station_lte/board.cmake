# SPDX-License-Identifier: Apache-2.0
# Copied from upstream boards/nordic/nrf9151dk/board.cmake (Zephyr main,
# 2026-11-17). The J-Link device name is Nordic's; re-check it against the
# pinned NCS tree.

if(CONFIG_TFM_FLASH_MERGED_BINARY)
  set_property(TARGET runners_yaml_props_target PROPERTY hex_file tfm_merged.hex)
endif()

board_runner_args(jlink "--device=nRF9151_xxCA" "--speed=4000")
include(${ZEPHYR_BASE}/boards/common/nrfutil.board.cmake)
include(${ZEPHYR_BASE}/boards/common/nrfjprog.board.cmake)
include(${ZEPHYR_BASE}/boards/common/jlink.board.cmake)
