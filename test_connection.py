#!/usr/bin/env python3
"""
Quick test script for OBDLink MX+ connection.

This is a standalone script - no installation required.
Just run: python test_connection.py --port /dev/rfcomm0

Requirements: pip install pyserial rich
"""

import argparse
import re
import serial
import sys
import time
from dataclasses import dataclass
from typing import Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Note: Install 'rich' for better output: pip install rich")


# =============================================================================
# Configuration
# =============================================================================

# Standard OBD2 PIDs to test
TEST_PIDS = {
    0x05: ("Coolant Temp", "°C", lambda d: d[0] - 40),
    0x0C: ("Engine RPM", "rpm", lambda d: ((d[0] * 256) + d[1]) / 4),
    0x0D: ("Vehicle Speed", "km/h", lambda d: d[0]),
    0x0F: ("Intake Air Temp", "°C", lambda d: d[0] - 40),
    0x10: ("MAF Rate", "g/s", lambda d: ((d[0] * 256) + d[1]) / 100),
    0x11: ("Throttle Pos", "%", lambda d: d[0] * 100 / 255),
    0x04: ("Engine Load", "%", lambda d: d[0] * 100 / 255),
    0x0B: ("Intake Pressure", "kPa", lambda d: d[0]),
    0x42: ("Control Voltage", "V", lambda d: ((d[0] * 256) + d[1]) / 1000),
    0x5C: ("Oil Temp (std)", "°C", lambda d: d[0] - 40),
}

# VAG-specific DIDs to try for oil temperature
VAG_OIL_TEMP_DIDS = {
    0xF486: ("Oil Temp (Block 134)", "°C", lambda d: d[0] - 40),
    0xF40E: ("Oil Temp (Alt 1)", "°C", lambda d: d[0] - 40),
    0x2028: ("Oil Temp (Alt 2)", "°C", lambda d: d[0] - 40),
    0x1040: ("Oil Temp (Alt 3)", "°C", lambda d: d[0] - 40),
}


# =============================================================================
# Connection Class
# =============================================================================

@dataclass
class Reading:
    name: str
    value: Optional[float]
    unit: str
    raw: str
    error: Optional[str] = None


class OBDLinkTester:
    """Simple OBDLink MX+ connection tester."""
    
    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.serial: Optional[serial.Serial] = None
        
    def connect(self) -> bool:
        """Open serial connection."""
        try:
            print(f"Opening {self.port} at {self.baudrate} baud...")
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1.0,
            )
            time.sleep(0.5)
            print("✓ Serial port opened")
            return True
        except serial.SerialException as e:
            print(f"✗ Failed to open port: {e}")
            return False
    
    def disconnect(self):
        """Close serial connection."""
        if self.serial:
            self.serial.close()
            print("Disconnected")
    
    def send(self, cmd: str, delay: float = 0.3) -> str:
        """Send command and get response."""
        self.serial.reset_input_buffer()
        self.serial.write((cmd + "\r").encode())
        time.sleep(delay)
        
        response = b""
        while self.serial.in_waiting:
            response += self.serial.read(self.serial.in_waiting)
            time.sleep(0.05)
        
        text = response.decode("ascii", errors="ignore")
        text = text.replace("\r", "\n").replace(">", "").strip()
        
        # Remove echo
        lines = text.split("\n")
        if len(lines) > 1 and lines[0].upper() == cmd.upper():
            text = "\n".join(lines[1:]).strip()
        
        return text
    
    def initialize(self) -> bool:
        """Initialize ELM327 adapter."""
        print("\nInitializing adapter...")
        
        # Reset
        resp = self.send("ATZ", delay=1.5)
        if "ELM" in resp or "OBDLink" in resp or "STN" in resp:
            adapter_name = resp.split("\n")[0]
            print(f"✓ Adapter: {adapter_name}")
        else:
            print(f"? Reset response: {resp[:50]}")
        
        # Configure
        commands = [
            ("ATE0", "Echo off"),
            ("ATL0", "Linefeeds off"),
            ("ATS0", "Spaces off"),
            ("ATH1", "Headers on"),
            ("ATSP6", "Protocol: CAN 500k"),
        ]
        
        for cmd, desc in commands:
            resp = self.send(cmd, delay=0.2)
            status = "✓" if "OK" in resp or resp == "" else "?"
            print(f"  {status} {desc}")
        
        # Test ECU connection
        print("\nTesting ECU connection...")
        resp = self.send("0100", delay=0.5)
        
        if "UNABLE TO CONNECT" in resp or "NO DATA" in resp:
            print(f"✗ ECU not responding: {resp}")
            print("  Make sure ignition is ON")
            return False
        
        print(f"✓ ECU responding")
        
        # Get voltage
        voltage = self.send("ATRV", delay=0.2)
        print(f"  Battery: {voltage}")
        
        return True
    
    def _parse_response(self, response: str, expected_header: int) -> Optional[list[int]]:
        """Parse hex response into data bytes."""
        if not response:
            return None
        
        for line in response.split("\n"):
            clean = re.sub(r'[^0-9A-Fa-f]', '', line)
            
            bytes_list = []
            for i in range(0, len(clean), 2):
                if i + 1 < len(clean):
                    bytes_list.append(int(clean[i:i+2], 16))
            
            if len(bytes_list) < 4:
                continue
            
            for i, b in enumerate(bytes_list):
                if b == expected_header:
                    if expected_header == 0x62:  # UDS
                        return bytes_list[i+3:] if len(bytes_list) > i+3 else []
                    else:  # OBD2
                        return bytes_list[i+2:] if len(bytes_list) > i+2 else []
        
        return None
    
    def read_pid(self, pid: int) -> Reading:
        """Read a standard OBD2 PID."""
        info = TEST_PIDS.get(pid, (f"PID 0x{pid:02X}", "", lambda d: d[0]))
        name, unit, formula = info
        
        cmd = f"01{pid:02X}"
        response = self.send(cmd, delay=0.3)
        
        if not response or "NO DATA" in response or "ERROR" in response:
            return Reading(name, None, unit, response, "No response")
        
        data = self._parse_response(response, 0x41)
        if data is None or len(data) == 0:
            return Reading(name, None, unit, response, "Parse error")
        
        try:
            value = formula(data)
            return Reading(name, value, unit, response)
        except (IndexError, ValueError) as e:
            return Reading(name, None, unit, response, str(e))
    
    def read_vag_did(self, did: int) -> Reading:
        """Read a VAG-specific DID."""
        info = VAG_OIL_TEMP_DIDS.get(did, (f"DID 0x{did:04X}", "", lambda d: d[0]))
        name, unit, formula = info
        
        cmd = f"22{did:04X}"
        response = self.send(cmd, delay=0.5)
        
        if not response or "NO DATA" in response:
            return Reading(name, None, unit, response, "No response")
        
        if "7F22" in response:
            return Reading(name, None, unit, response, "Not supported")
        
        data = self._parse_response(response, 0x62)
        if data is None or len(data) == 0:
            return Reading(name, None, unit, response, "Parse error")
        
        try:
            value = formula(data)
            return Reading(name, value, unit, response)
        except (IndexError, ValueError) as e:
            return Reading(name, None, unit, response, str(e))
    
    def enter_extended_session(self) -> bool:
        """Enter extended diagnostic session."""
        response = self.send("1003", delay=0.5)
        return "50" in response


# =============================================================================
# Output Functions
# =============================================================================

def print_results(readings: list[Reading], title: str = "Results"):
    """Print readings as a table."""
    if RICH_AVAILABLE:
        console = Console()
        table = Table(title=title)
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", justify="right")
        table.add_column("Unit", style="dim")
        table.add_column("Status")
        
        for r in readings:
            if r.value is not None:
                table.add_row(r.name, f"{r.value:.1f}", r.unit, "[green]✓[/green]")
            else:
                table.add_row(r.name, "-", r.unit, f"[red]✗ {r.error}[/red]")
        
        console.print(table)
    else:
        print(f"\n{title}")
        print("-" * 60)
        for r in readings:
            if r.value is not None:
                print(f"  {r.name:25s} {r.value:8.1f} {r.unit:6s} ✓")
            else:
                print(f"  {r.name:25s}     -    {r.unit:6s} ✗ {r.error}")
        print()


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="OBDLink MX+ Connection Test")
    parser.add_argument("-p", "--port", default="/dev/rfcomm0",
                       help="Serial port (default: /dev/rfcomm0)")
    parser.add_argument("-b", "--baudrate", type=int, default=115200,
                       help="Baud rate (default: 115200)")
    parser.add_argument("--oil-temp", action="store_true",
                       help="Focus on finding oil temperature")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  OBDLink MX+ Connection Test - MK5 Golf GTI")
    print("=" * 60)
    
    tester = OBDLinkTester(args.port, args.baudrate)
    
    try:
        if not tester.connect():
            sys.exit(1)
        
        if not tester.initialize():
            sys.exit(1)
        
        # Read standard PIDs
        print("\n" + "=" * 60)
        print("  Reading Standard OBD2 PIDs")
        print("=" * 60)
        
        std_readings = []
        for pid in TEST_PIDS:
            reading = tester.read_pid(pid)
            std_readings.append(reading)
            
            if reading.value is not None:
                print(f"  ✓ {reading.name}: {reading.value:.1f} {reading.unit}")
            else:
                print(f"  ✗ {reading.name}: {reading.error}")
        
        # Try VAG DIDs for oil temperature
        print("\n" + "=" * 60)
        print("  Searching for Oil Temperature (VAG DIDs)")
        print("=" * 60)
        
        found_oil_temp = False
        
        for did in VAG_OIL_TEMP_DIDS:
            reading = tester.read_vag_did(did)
            
            if reading.value is not None:
                print(f"  ✓ FOUND! {reading.name}: {reading.value:.1f} {reading.unit}")
                print(f"    Command: 22{did:04X}")
                found_oil_temp = True
                break
            else:
                print(f"  ✗ {reading.name}: {reading.error}")
        
        if not found_oil_temp:
            print("\n  Trying extended diagnostic session...")
            if tester.enter_extended_session():
                print("  ✓ Extended session active")
                
                for did in VAG_OIL_TEMP_DIDS:
                    reading = tester.read_vag_did(did)
                    
                    if reading.value is not None:
                        print(f"  ✓ FOUND! {reading.name}: {reading.value:.1f} {reading.unit}")
                        print(f"    Command: 1003 (extended session) then 22{did:04X}")
                        found_oil_temp = True
                        break
                    else:
                        print(f"  ✗ {reading.name}: {reading.error}")
        
        if not found_oil_temp:
            print("\n  ⚠ Oil temperature not found via known DIDs")
            print("    Your ECU may use different DIDs or require security access")
        
        # Summary
        print("\n" + "=" * 60)
        print("  Summary")
        print("=" * 60)
        
        working = [r for r in std_readings if r.value is not None]
        print(f"  Standard PIDs working: {len(working)}/{len(std_readings)}")
        print(f"  Oil temperature found: {'Yes' if found_oil_temp else 'No'}")
        
        print("\n  Connection test complete!")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    finally:
        tester.disconnect()


if __name__ == "__main__":
    main()
