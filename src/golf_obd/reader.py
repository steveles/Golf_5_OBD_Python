"""
OBD2 Reader - Reads and decodes standard and VAG-specific parameters.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .connection import ELM327Connection
from .pids import (
    STANDARD_PIDS,
    VAG_DIDS,
    PIDDefinition,
    VAGDIDDefinition,
    get_pid,
    get_vag_did,
)

logger = logging.getLogger(__name__)


@dataclass
class Reading:
    """A single sensor reading."""
    
    name: str
    short_name: str
    value: Optional[float]
    unit: str
    raw_hex: str
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if reading is valid."""
        return self.value is not None and self.error is None
    
    def format_value(self, precision: int = 1) -> str:
        """Format value with unit."""
        if self.value is None:
            return "N/A"
        if self.unit:
            return f"{self.value:.{precision}f} {self.unit}"
        return f"{self.value:.{precision}f}"


@dataclass 
class ScanResult:
    """Result of scanning for supported PIDs."""
    
    supported_pids: list[int] = field(default_factory=list)
    unsupported_pids: list[int] = field(default_factory=list)
    supported_vag_dids: list[int] = field(default_factory=list)
    unsupported_vag_dids: list[int] = field(default_factory=list)


class OBDReader:
    """
    Reads OBD2 data from vehicle via ELM327 adapter.
    
    Supports both standard OBD2 PIDs and VAG-specific DIDs.
    """
    
    # CAN IDs for VAG vehicles
    ECU_REQUEST_ID = 0x7E0   # Engine ECU request
    ECU_RESPONSE_ID = 0x7E8  # Engine ECU response
    
    def __init__(self, connection: ELM327Connection):
        """
        Initialize OBD reader.
        
        Args:
            connection: ELM327 connection instance
        """
        self.connection = connection
        self._supported_pids: set[int] = set()
        self._supported_dids: set[int] = set()
    
    def _parse_hex_response(self, response: str) -> list[int]:
        """
        Parse hex response string into list of bytes.
        
        Args:
            response: Hex string response from adapter
            
        Returns:
            List of integer byte values
        """
        # Remove all non-hex characters
        clean = re.sub(r'[^0-9A-Fa-f]', '', response)
        
        # Convert pairs of hex digits to bytes
        bytes_list = []
        for i in range(0, len(clean), 2):
            if i + 1 < len(clean):
                bytes_list.append(int(clean[i:i+2], 16))
        
        return bytes_list
    
    def _extract_data_bytes(self, response: str, expected_header: int) -> Optional[list[int]]:
        """
        Extract data bytes from OBD response.
        
        Standard OBD2 response format (with headers on):
        7E8 04 41 0C 1A F8  (for RPM query 010C)
        
        Where:
        - 7E8 = Response CAN ID
        - 04 = Number of data bytes following
        - 41 = Service 01 response (01 + 0x40)
        - 0C = PID
        - 1A F8 = Data bytes
        
        Args:
            response: Raw hex response
            expected_header: Expected response byte (e.g., 0x41 for service 0x01)
            
        Returns:
            List of data bytes, or None if parsing fails
        """
        if not response:
            return None
        
        # Handle multi-line responses (take first valid line)
        for line in response.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            bytes_list = self._parse_hex_response(line)
            
            if len(bytes_list) < 4:
                continue
            
            # Check for response header
            # Bytes: [CAN_ID_H, CAN_ID_L, Length, Response_Type, PID/DID, Data...]
            # Or:    [Length, Response_Type, PID/DID, Data...]
            
            # Find the response header byte
            for i, b in enumerate(bytes_list):
                if b == expected_header:
                    # Found response header, data starts after PID/DID
                    if expected_header == 0x62:  # UDS response - 2 byte DID
                        return bytes_list[i+3:] if len(bytes_list) > i+3 else []
                    else:  # Standard OBD2 - 1 byte PID
                        return bytes_list[i+2:] if len(bytes_list) > i+2 else []
        
        return None
    
    def read_pid(self, pid: int) -> Reading:
        """
        Read a standard OBD2 PID.
        
        Args:
            pid: PID number (0x00-0xFF)
            
        Returns:
            Reading object with decoded value
        """
        pid_def = get_pid(pid)
        
        if pid_def is None:
            # Unknown PID - still try to read it
            pid_def = PIDDefinition(
                pid=pid,
                name=f"Unknown PID 0x{pid:02X}",
                short_name=f"0x{pid:02X}",
                unit="",
                category=None,
            )
        
        command = pid_def.get_command()
        response = self.connection.send_obd_command(command)
        
        if response is None:
            return Reading(
                name=pid_def.name,
                short_name=pid_def.short_name,
                value=None,
                unit=pid_def.unit,
                raw_hex="",
                error="No response from ECU",
            )
        
        # Extract data bytes (response header for service 0x01 is 0x41)
        data_bytes = self._extract_data_bytes(response, 0x41)
        
        if data_bytes is None or len(data_bytes) < pid_def.bytes_returned:
            return Reading(
                name=pid_def.name,
                short_name=pid_def.short_name,
                value=None,
                unit=pid_def.unit,
                raw_hex=response,
                error="Invalid response format",
            )
        
        # Decode value
        value = pid_def.decode(data_bytes)
        
        return Reading(
            name=pid_def.name,
            short_name=pid_def.short_name,
            value=value,
            unit=pid_def.unit,
            raw_hex=response,
        )
    
    def read_vag_did(self, did: int) -> Reading:
        """
        Read a VAG-specific DID using UDS service 0x22.
        
        Args:
            did: Data Identifier (e.g., 0xF486 for oil temp)
            
        Returns:
            Reading object with decoded value
        """
        did_def = get_vag_did(did)
        
        if did_def is None:
            did_def = VAGDIDDefinition(
                did=did,
                name=f"Unknown DID 0x{did:04X}",
                short_name=f"0x{did:04X}",
                unit="",
                category=None,
            )
        
        command = did_def.get_command()
        response = self.connection.send_obd_command(command, timeout=0.5)
        
        if response is None:
            return Reading(
                name=did_def.name,
                short_name=did_def.short_name,
                value=None,
                unit=did_def.unit,
                raw_hex="",
                error="No response from ECU",
            )
        
        # Check for negative response
        if "7F22" in response:
            error_code = "Unknown error"
            if "7F2231" in response:
                error_code = "Request out of range"
            elif "7F2214" in response:
                error_code = "Response too long"
            elif "7F2233" in response:
                error_code = "Security access denied"
            elif "7F2212" in response:
                error_code = "Sub-function not supported"
            
            return Reading(
                name=did_def.name,
                short_name=did_def.short_name,
                value=None,
                unit=did_def.unit,
                raw_hex=response,
                error=error_code,
            )
        
        # Extract data bytes (response header for service 0x22 is 0x62)
        data_bytes = self._extract_data_bytes(response, 0x62)
        
        if data_bytes is None or len(data_bytes) < 1:
            return Reading(
                name=did_def.name,
                short_name=did_def.short_name,
                value=None,
                unit=did_def.unit,
                raw_hex=response,
                error="Invalid response format",
            )
        
        # Decode value
        value = did_def.decode(data_bytes)
        
        return Reading(
            name=did_def.name,
            short_name=did_def.short_name,
            value=value,
            unit=did_def.unit,
            raw_hex=response,
        )
    
    def read_multiple_pids(self, pids: list[int]) -> dict[int, Reading]:
        """
        Read multiple standard PIDs.
        
        Args:
            pids: List of PID numbers to read
            
        Returns:
            Dictionary mapping PID number to Reading
        """
        results = {}
        for pid in pids:
            results[pid] = self.read_pid(pid)
        return results
    
    def scan_supported_pids(self) -> list[int]:
        """
        Scan for supported PIDs using PID 0x00, 0x20, 0x40, etc.
        
        Returns:
            List of supported PID numbers
        """
        supported = []
        
        # PIDs 0x00, 0x20, 0x40, 0x60, 0x80, 0xA0, 0xC0 report which PIDs are supported
        scan_pids = [0x00, 0x20, 0x40, 0x60, 0x80, 0xA0, 0xC0]
        
        for scan_pid in scan_pids:
            response = self.connection.send_obd_command(f"01{scan_pid:02X}")
            
            if response is None:
                continue
            
            data_bytes = self._extract_data_bytes(response, 0x41)
            
            if data_bytes is None or len(data_bytes) < 4:
                continue
            
            # Each bit in the 4 bytes indicates if a PID is supported
            # Bit 7 of byte 0 = PID scan_pid+1
            # Bit 0 of byte 3 = PID scan_pid+32
            for byte_idx, byte_val in enumerate(data_bytes[:4]):
                for bit_idx in range(8):
                    if byte_val & (1 << (7 - bit_idx)):
                        pid_num = scan_pid + (byte_idx * 8) + bit_idx + 1
                        supported.append(pid_num)
            
            # If bit 0 of byte 3 is not set, no more PIDs to scan
            if not (data_bytes[3] & 0x01):
                break
        
        self._supported_pids = set(supported)
        logger.info(f"Found {len(supported)} supported PIDs")
        
        return supported
    
    def scan_vag_dids(self, dids: Optional[list[int]] = None) -> list[int]:
        """
        Scan for supported VAG DIDs.
        
        Args:
            dids: List of DIDs to test, or None to test known DIDs
            
        Returns:
            List of DIDs that responded
        """
        if dids is None:
            dids = list(VAG_DIDS.keys())
        
        supported = []
        
        for did in dids:
            reading = self.read_vag_did(did)
            if reading.is_valid:
                supported.append(did)
                logger.info(f"Found supported DID 0x{did:04X}: {reading.format_value()}")
        
        self._supported_dids = set(supported)
        
        return supported
    
    def find_oil_temperature(self) -> Optional[Reading]:
        """
        Attempt to find and read oil temperature from various sources.
        
        Tries standard OBD2 PID first, then VAG-specific DIDs.
        
        Returns:
            Reading with oil temperature, or None if not found
        """
        # First try standard OBD2 PID 0x5C (oil temp)
        reading = self.read_pid(0x5C)
        if reading.is_valid:
            logger.info(f"Oil temp found via standard PID 0x5C: {reading.format_value()}")
            return reading
        
        # Try VAG-specific DIDs
        vag_oil_dids = [0xF486, 0xF40E, 0x2028, 0x1040]
        
        for did in vag_oil_dids:
            reading = self.read_vag_did(did)
            if reading.is_valid:
                logger.info(f"Oil temp found via VAG DID 0x{did:04X}: {reading.format_value()}")
                return reading
        
        # Try entering extended diagnostic session and retry
        logger.info("Trying extended diagnostic session...")
        response = self.connection.send_obd_command("1003", timeout=0.5)
        
        if response and "50" in response:
            logger.info("Extended session active, retrying...")
            for did in vag_oil_dids:
                reading = self.read_vag_did(did)
                if reading.is_valid:
                    logger.info(f"Oil temp found in extended session via 0x{did:04X}")
                    return reading
        
        logger.warning("Could not find oil temperature reading")
        return None
    
    def enter_extended_session(self) -> bool:
        """
        Enter UDS extended diagnostic session.
        
        Some DIDs are only available in extended session.
        
        Returns:
            True if session change successful
        """
        response = self.connection.send_obd_command("1003", timeout=0.5)
        return response is not None and "50" in response
    
    def read_dtcs(self) -> list[str]:
        """
        Read Diagnostic Trouble Codes (DTCs).
        
        Returns:
            List of DTC codes (e.g., ['P0300', 'P0171'])
        """
        response = self.connection.send_obd_command("03", timeout=1.0)
        
        if response is None:
            return []
        
        data_bytes = self._parse_hex_response(response)
        
        # Find response header (0x43 = response to service 0x03)
        try:
            start_idx = data_bytes.index(0x43) + 1
        except ValueError:
            return []
        
        # Number of DTCs
        dtc_count = data_bytes[start_idx] if start_idx < len(data_bytes) else 0
        
        if dtc_count == 0:
            return []
        
        dtcs = []
        idx = start_idx + 1
        
        # Each DTC is 2 bytes
        while idx + 1 < len(data_bytes) and len(dtcs) < dtc_count:
            byte1, byte2 = data_bytes[idx], data_bytes[idx + 1]
            
            # Skip padding (00 00)
            if byte1 == 0 and byte2 == 0:
                idx += 2
                continue
            
            # Decode DTC
            # First 2 bits determine type: 00=P, 01=C, 10=B, 11=U
            dtc_type = ['P', 'C', 'B', 'U'][(byte1 >> 6) & 0x03]
            dtc_code = f"{dtc_type}{((byte1 & 0x3F) << 8) | byte2:04X}"
            dtcs.append(dtc_code)
            
            idx += 2
        
        return dtcs
