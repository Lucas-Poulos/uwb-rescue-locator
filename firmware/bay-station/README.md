# Bay station firmware

Fanstel BT840 (Nordic nRF52840). Drives 4x DW3210 over one SPI bus (four chip
selects), runs the ranging/TDoA exchange, applies the calibration table, and
reports position over BLE to a laptop.

Note **SPIM3 is the only high-speed SPI instance** on the nRF52840 (32 MHz;
the others cap at 8 MHz), so the anchor bus must use it -- and check the
silicon revision against Nordic's erratum on SPIM rates above 8 MHz.

Empty. See `../README.md` for the task list; the first job is restoring
multi-instance support in the DW3000 driver.
