# Bay station BLE bridge (BT840 / nRF52840). Target: NCS v3.4.x (LTS).
#   west build -b bay_station_ble/nrf52840 firmware/bay-station/ble-bridge
# Not built yet: no SDK in the environment this was written in.
cmake_minimum_required(VERSION 3.20.0)

get_filename_component(UWBRL_FW_ROOT ${CMAKE_CURRENT_LIST_DIR}/../.. ABSOLUTE)
list(APPEND BOARD_ROOT ${UWBRL_FW_ROOT})
list(APPEND DTS_ROOT ${UWBRL_FW_ROOT})

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(uwbrl_bay_station_ble)

target_include_directories(app PRIVATE ${UWBRL_FW_ROOT}/common/include)
target_sources(app PRIVATE
  src/main.c
  ${UWBRL_FW_ROOT}/common/src/bridge_proto.c
)
