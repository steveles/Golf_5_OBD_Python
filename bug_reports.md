# Bug Reports

## BT-001: macOS Sequoia Bluetooth Serial Port Issue

**Date:** 2024-12-19
**Status:** Open
**Platform:** macOS 15.6.1 (Sequoia)
**Adapter:** OBDLink MX+ (Bluetooth)

### Summary
Bluetooth serial port stops receiving data after `serial.close()` is called. Subsequent connection attempts open successfully but return no data.

### Reproduction
1. Pair OBDLink MX+ via Bluetooth
2. Run `test_connection.py` - **works** (adapter responds, PIDs read)
3. Script calls `disconnect()` which closes serial port
4. Run script again - port opens but **no data received**
5. Forget device in Bluetooth settings, re-pair
6. Run script - **works again** (first run only)

### Findings
- Serial port opens successfully on all attempts
- Control signals (CTS, DSR, CD) all show True
- Write operations complete without error
- Read operations return empty (`b''`)
- Issue persists across all baud rates (9600, 38400, 115200)
- Both `/dev/tty.*` and `/dev/cu.*` ports affected

### Root Cause
macOS Sequoia (15.x) has a bug in Bluetooth SPP (Serial Port Profile) handling. Closing the serial port corrupts the Bluetooth receive channel state, which doesn't recover until the device is re-paired.

### Workarounds
1. **Don't close the port** - Remove `serial.close()` call; let OS release on process exit
2. **USB connection** - Bypasses Bluetooth entirely
3. **WiFi OBD adapter** - Uses TCP socket instead of serial
4. **Re-pair before each session** - Forget and reconnect Bluetooth device

### Recommended Fix
Modify `disconnect()` to skip `serial.close()` on macOS Bluetooth connections.