"""
ELM327/OBDLink adapter connection and communication.

Handles serial communication with ELM327-compatible adapters like OBDLink MX+.
"""

import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import serial

logger = logging.getLogger(__name__)


class Protocol(Enum):
    """OBD2 protocols supported by ELM327."""
    AUTO = "0"
    SAE_J1850_PWM = "1"
    SAE_J1850_VPW = "2"
    ISO_9141_2 = "3"
    ISO_14230_4_KWP_5BAUD = "4"
    ISO_14230_4_KWP_FAST = "5"
    ISO_15765_4_CAN_11BIT_500K = "6"
    ISO_15765_4_CAN_29BIT_500K = "7"
    ISO_15765_4_CAN_11BIT_250K = "8"
    ISO_15765_4_CAN_29BIT_250K = "9"
    SAE_J1939_CAN = "A"
    USER1_CAN = "B"
    USER2_CAN = "C"


@dataclass
class AdapterInfo:
    """Information about the connected adapter."""
    device_id: str
    voltage: Optional[float]
    protocol: Optional[str]
    protocol_name: Optional[str]


class ELM327Connection:
    """
    Manages connection to an ELM327-compatible OBD2 adapter.
    
    Supports OBDLink MX+, standard ELM327, and compatible adapters.
    """
    
    # Common response patterns
    PROMPT = b">"
    OK = "OK"
    ERROR_PATTERNS = [
        "UNABLE TO CONNECT",
        "NO DATA",
        "CAN ERROR",
        "BUS INIT",
        "STOPPED",
        "ERROR",
        "?",
    ]
    
    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 1.0,
    ):
        """
        Initialize ELM327 connection.
        
        Args:
            port: Serial port (e.g., '/dev/rfcomm0', 'COM3', '/dev/tty.OBDLinkMX')
            baudrate: Baud rate (OBDLink MX+ uses 115200, cheap ELM327 often 38400)
            timeout: Read timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None
        self._connected = False
        self._protocol: Optional[Protocol] = None
        
    @property
    def connected(self) -> bool:
        """Check if adapter is connected and responsive."""
        return self._connected and self._serial is not None and self._serial.is_open
    
    def connect(self) -> bool:
        """
        Open serial connection to the adapter.
        
        Returns:
            True if connection successful, False otherwise.
        """
        try:
            logger.info(f"Connecting to {self.port} at {self.baudrate} baud...")
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
            time.sleep(0.5)  # Allow adapter to settle
            self._connected = True
            logger.info("Serial connection established")
            return True
            
        except serial.SerialException as e:
            logger.error(f"Failed to connect: {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """Close serial connection."""
        if self._serial:
            try:
                self._serial.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self._serial = None
                self._connected = False
                logger.info("Disconnected from adapter")
    
    def send_raw(self, command: str, delay: float = 0.1) -> str:
        """
        Send a raw command to the adapter and get response.
        
        Args:
            command: Command string to send
            delay: Delay after sending before reading response
            
        Returns:
            Response string from adapter
        """
        if not self.connected:
            raise RuntimeError("Not connected to adapter")
        
        # Clear any pending data
        self._serial.reset_input_buffer()
        
        # Send command with carriage return
        cmd_bytes = (command + "\r").encode("ascii")
        self._serial.write(cmd_bytes)
        logger.debug(f"TX: {command}")
        
        time.sleep(delay)
        
        # Read response until prompt
        response = self._read_until_prompt()
        logger.debug(f"RX: {response}")
        
        return response
    
    def _read_until_prompt(self, timeout: float = 2.0) -> str:
        """Read from serial until we see the prompt character."""
        response = b""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self._serial.in_waiting:
                chunk = self._serial.read(self._serial.in_waiting)
                response += chunk
                
                # Check for prompt
                if self.PROMPT in response:
                    break
            else:
                time.sleep(0.01)
        
        # Decode and clean up response
        text = response.decode("ascii", errors="ignore")
        text = text.replace("\r", "\n").replace("\n\n", "\n")
        text = text.replace(">", "").strip()
        
        # Remove echo if present (command echoed back)
        lines = text.split("\n")
        if len(lines) > 1:
            text = "\n".join(lines[1:]).strip()
        
        return text
    
    def initialize(self, protocol: Protocol = Protocol.ISO_15765_4_CAN_11BIT_500K) -> bool:
        """
        Initialize the adapter with proper settings.
        
        Args:
            protocol: OBD protocol to use (default: CAN 500kbps for modern VW)
            
        Returns:
            True if initialization successful
        """
        if not self.connected:
            raise RuntimeError("Not connected to adapter")
        
        logger.info("Initializing ELM327 adapter...")
        
        # Reset adapter
        response = self.send_raw("ATZ", delay=1.5)
        if "ELM" not in response and "OBDLink" not in response and "STN" not in response:
            logger.warning(f"Unexpected reset response: {response}")
        else:
            logger.info(f"Adapter identified: {response.split()[0] if response else 'Unknown'}")
        
        # Configuration commands
        init_commands = [
            ("ATE0", "Echo off"),              # Disable command echo
            ("ATL0", "Linefeeds off"),         # Disable linefeeds  
            ("ATS0", "Spaces off"),            # Disable spaces in responses
            ("ATH1", "Headers on"),            # Enable headers (we need CAN IDs)
            ("ATCAF0", "CAN formatting off"),  # Raw CAN data
            ("ATAT1", "Adaptive timing"),      # Auto-adjust timing
            (f"ATSP{protocol.value}", f"Protocol {protocol.name}"),  # Set protocol
        ]
        
        for cmd, description in init_commands:
            response = self.send_raw(cmd, delay=0.1)
            success = self.OK in response or response == ""
            status = "✓" if success else "?"
            logger.info(f"  {status} {description}: {response[:30] if response else 'OK'}")
            
            if not success and "ERROR" in response.upper():
                logger.error(f"Command {cmd} failed: {response}")
                return False
        
        self._protocol = protocol
        
        # Test ECU connection with a simple PID request
        logger.info("Testing ECU connection...")
        response = self.send_raw("0100", delay=0.5)  # Request supported PIDs
        
        if any(err in response.upper() for err in self.ERROR_PATTERNS):
            logger.error(f"ECU not responding: {response}")
            return False
        
        logger.info(f"ECU responding: {response[:50]}...")
        return True
    
    def get_adapter_info(self) -> AdapterInfo:
        """Get information about the connected adapter."""
        # Get device ID
        device_id = self.send_raw("ATI", delay=0.3)
        
        # Get battery voltage
        voltage_str = self.send_raw("ATRV", delay=0.3)
        voltage = None
        match = re.search(r"(\d+\.?\d*)", voltage_str)
        if match:
            voltage = float(match.group(1))
        
        # Get current protocol
        protocol = self.send_raw("ATDP", delay=0.3)
        protocol_num = self.send_raw("ATDPN", delay=0.3)
        
        return AdapterInfo(
            device_id=device_id,
            voltage=voltage,
            protocol=protocol_num,
            protocol_name=protocol,
        )
    
    def set_header(self, can_id: int) -> bool:
        """
        Set the CAN header (transmit address).
        
        Args:
            can_id: CAN ID to use for requests (e.g., 0x7E0 for engine ECU)
        """
        response = self.send_raw(f"ATSH{can_id:03X}", delay=0.1)
        return self.OK in response
    
    def set_receive_filter(self, can_id: int) -> bool:
        """
        Set CAN receive filter to only accept responses from specific ID.
        
        Args:
            can_id: CAN ID to filter for (e.g., 0x7E8 for engine ECU response)
        """
        response = self.send_raw(f"ATCRA{can_id:03X}", delay=0.1)
        return self.OK in response
    
    def send_obd_command(self, command: str, timeout: float = 0.3) -> Optional[str]:
        """
        Send an OBD command and get the response.
        
        Args:
            command: Hex command string (e.g., "0105" for coolant temp)
            timeout: Response timeout
            
        Returns:
            Response hex string or None if error
        """
        response = self.send_raw(command, delay=timeout)
        
        # Check for errors
        if any(err in response.upper() for err in self.ERROR_PATTERNS):
            return None
        
        # Clean response - remove any non-hex characters except newlines
        cleaned = "".join(c for c in response if c in "0123456789ABCDEFabcdef\n")
        
        return cleaned if cleaned else None
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False
