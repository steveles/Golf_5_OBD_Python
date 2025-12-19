# Golf GTI OBD2 Reader

Python OBD2 data reader for MK5 Golf GTI with support for VAG-specific parameters including oil temperature.

## Features

- 🔌 **Bluetooth connection** to OBDLink MX+ (and other ELM327-compatible adapters)
- 📊 **Standard OBD2 PIDs** - RPM, speed, coolant temp, MAF, etc.
- 🔧 **VAG-specific DIDs** - Oil temperature, boost pressure, and more
- 📺 **Live dashboard** with auto-refresh using Rich terminal UI
- 🔍 **PID/DID scanner** to discover supported parameters
- 🌡️ **Oil temperature finder** - searches multiple sources for oil temp

## Installation

### Prerequisites

1. **Pair your OBDLink MX+ via Bluetooth** (or connect USB adapter)
   
   On Linux:
   ```bash
   # Find the adapter
   bluetoothctl scan on
   # Look for "OBDLink MX+"
   
   # Pair and trust
   bluetoothctl pair XX:XX:XX:XX:XX:XX
   bluetoothctl trust XX:XX:XX:XX:XX:XX
   
   # Bind to serial port
   sudo rfcomm bind 0 XX:XX:XX:XX:XX:XX
   # This creates /dev/rfcomm0
   ```
   
   On macOS:
   - Pair via System Preferences → Bluetooth
   - Device appears as `/dev/tty.OBDLinkMX` or similar
   
   On Windows:
   - Pair via Bluetooth settings
   - Note the COM port assigned (e.g., `COM3`)

2. **Install Python 3.10+**

### Install the package

```bash
# Clone/download the project
cd golf-gti-obd

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows

# Install the package
pip install -e .
```

## Usage

### Quick Start

```bash
# Basic read (shows common parameters once)
golf-obd --port /dev/rfcomm0

# On Windows
golf-obd --port COM3

# On macOS
golf-obd --port /dev/tty.OBDLinkMX
```

### Live Dashboard

```bash
golf-obd --port /dev/rfcomm0 --live

# Faster refresh
golf-obd --port /dev/rfcomm0 --live --refresh 0.5
```

### Find Oil Temperature

```bash
golf-obd --port /dev/rfcomm0 --oil-temp
```

This tries:
1. Standard OBD2 PID 0x5C (oil temperature)
2. VAG DID 0xF486 (VCDS measuring block 134)
3. VAG DID 0xF40E (alternative location)
4. VAG DID 0x2028 (engine sensors)
5. Extended diagnostic session + retries

### Scan for Supported Parameters

```bash
golf-obd --port /dev/rfcomm0 --scan
```

### Read Specific PIDs/DIDs

```bash
# Read specific standard PIDs
golf-obd --port /dev/rfcomm0 --pids 0x05 0x0C 0x0D

# Read VAG-specific DIDs
golf-obd --port /dev/rfcomm0 --vag-dids 0xF486 0xF40E

# Both
golf-obd --port /dev/rfcomm0 --pids 0x05 0x0C --vag-dids 0xF486
```

### Verbose Output

```bash
golf-obd --port /dev/rfcomm0 -v
```

## Using as a Library

```python
from golf_obd.connection import ELM327Connection, Protocol
from golf_obd.reader import OBDReader

# Connect to adapter
with ELM327Connection(port='/dev/rfcomm0', baudrate=115200) as conn:
    # Initialize for CAN 500kbps (MK5 GTI)
    conn.initialize(Protocol.ISO_15765_4_CAN_11BIT_500K)
    
    # Create reader
    reader = OBDReader(conn)
    
    # Read standard PIDs
    coolant = reader.read_pid(0x05)
    print(f"Coolant: {coolant.format_value()}")
    
    rpm = reader.read_pid(0x0C)
    print(f"RPM: {rpm.format_value()}")
    
    # Read VAG-specific DID (oil temperature)
    oil_temp = reader.read_vag_did(0xF486)
    if oil_temp.is_valid:
        print(f"Oil Temp: {oil_temp.format_value()}")
    else:
        print(f"Oil Temp not available: {oil_temp.error}")
    
    # Scan for supported PIDs
    supported = reader.scan_supported_pids()
    print(f"Supported PIDs: {[hex(p) for p in supported]}")
    
    # Read DTCs
    dtcs = reader.read_dtcs()
    print(f"Trouble codes: {dtcs}")
```

## VAG-Specific Notes

### Oil Temperature

On the MK5 GTI (EA113/EA888 2.0T), oil temperature is typically available through:

| Method | Command | Notes |
|--------|---------|-------|
| Standard OBD2 | `0x5C` | May not be supported |
| VCDS Block 134 | `22F486` | Most likely to work |
| Alternative | `22F40E` | Some ECU variants |
| Alternative | `222028` | Some ECU variants |

The tool automatically searches these when you use `--oil-temp`.

### Extended Diagnostic Session

Some parameters require entering an extended diagnostic session first:

```python
reader.enter_extended_session()  # Sends UDS 0x10 0x03
reading = reader.read_vag_did(0xF486)
```

### Known MK5 GTI DIDs

| DID | Measuring Block | Description |
|-----|-----------------|-------------|
| 0xF486 | 134 | Oil temperature |
| 0xF406 | 6 | Boost pressure |
| 0xF41F | 31 | Ignition timing |
| 0xF189 | - | ECU software version |
| 0xF190 | - | VIN |

## Troubleshooting

### "UNABLE TO CONNECT"

- Ensure ignition is ON
- Try different baud rates (115200 for OBDLink, 38400 for cheap ELM327)
- Check Bluetooth pairing
- Try `ATSP0` (auto protocol detection)

### "NO DATA" on VAG DIDs

- The DID may not be supported by your ECU
- Try entering extended session first
- Your ECU may require security access

### Bluetooth Connection Issues (Linux)

```bash
# Check if rfcomm is bound
rfcomm -a

# Re-bind if needed
sudo rfcomm release 0
sudo rfcomm bind 0 XX:XX:XX:XX:XX:XX

# Check permissions
sudo chmod 666 /dev/rfcomm0
```

### Wrong Values

- Check the decode formula - VAG sometimes uses different offsets
- Enable verbose mode (`-v`) to see raw hex responses
- Compare with VCDS or Torque app readings

## Project Structure

```
golf-gti-obd/
├── pyproject.toml          # Project configuration
├── README.md               # This file
└── src/
    └── golf_obd/
        ├── __init__.py     # Package init
        ├── connection.py   # ELM327 serial communication
        ├── pids.py         # PID/DID definitions and decode formulas
        ├── reader.py       # OBD2 data reader
        └── cli.py          # Command-line interface
```

## Contributing

Feel free to add more VAG-specific DIDs or improve the decode formulas! The MK5 GTI community has reverse-engineered many parameters that could be added.

## License

MIT
