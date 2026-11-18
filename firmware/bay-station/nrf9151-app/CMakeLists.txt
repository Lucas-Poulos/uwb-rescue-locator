# Bay station host application (nRF9151). Target: NCS v3.4.x (LTS).
#   west build -b bay_station_lte/nrf9151/ns firmware/bay-station/nrf9151-app
# Not built yet: no SDK in the environment this was written in.
cmake_minimum_required(VERSION 3.20.0)

# Out-of-tree board + project bindings live in firmware/.
get_filename_component(UWBRL_FW_ROOT ${CMAKE_CURRENT_LIST_DIR}/../.. ABSOLUTE)
list(APPEND BOARD_ROOT ${UWBRL_FW_ROOT})
list(APPEND DTS_ROOT ${UWBRL_FW_ROOT})

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(uwbrl_bay_station_lte)

target_include_directories(app PRIVATE ${UWBRL_FW_ROOT}/common/include src)
target_sources(app PRIVATE
  src/main.c
  src/uwb_array.c
  src/bridge_link.c
  src/lte_gnss.c
  ${UWBRL_FW_ROOT}/common/src/bridge_proto.c
)
target_sources_ifdef(CONFIG_UWBRL_BRINGUP_SHELL app PRIVATE src/bringup_shell.c)
