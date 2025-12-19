"""
OBD2 PID definitions for standard and VAG-specific parameters.

Includes formulas for decoding raw values to engineering units.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Union


class PIDCategory(Enum):
    """Categories of PIDs."""
    ENGINE = "engine"
    FUEL = "fuel"
    TEMPERATURE = "temperature"
    PRESSURE = "pressure"
    ELECTRICAL = "electrical"
    EMISSIONS = "emissions"
    SPEED = "speed"
    VAG_SPECIFIC = "vag_specific"


@dataclass
class PIDDefinition:
    """Definition of an OBD2 PID including decode formula."""
    
    pid: int                                    # PID number
    name: str                                   # Human-readable name
    short_name: str                             # Short display name
    unit: str                                   # Unit of measurement
    category: PIDCategory                       # Category for grouping
    service: int = 0x01                         # OBD service (0x01 = current data)
    bytes_returned: int = 1                     # Number of data bytes expected
    min_value: Optional[float] = None           # Minimum possible value
    max_value: Optional[float] = None           # Maximum possible value
    formula: Optional[Callable[[list[int]], float]] = None  # Decode function
    description: str = ""                       # Detailed description
    
    def decode(self, data_bytes: list[int]) -> Optional[float]:
        """
        Decode raw bytes to engineering value.
        
        Args:
            data_bytes: List of raw data bytes from ECU
            
        Returns:
            Decoded value in engineering units, or None if decode fails
        """
        if self.formula is None:
            return float(data_bytes[0]) if data_bytes else None
        
        try:
            return self.formula(data_bytes)
        except (IndexError, ValueError, ZeroDivisionError):
            return None
    
    def get_command(self) -> str:
        """Get the OBD command string for this PID."""
        return f"{self.service:02X}{self.pid:02X}"


# =============================================================================
# Decode formulas
# =============================================================================

def decode_temperature(data: list[int]) -> float:
    """Standard temperature: A - 40 (°C)"""
    return data[0] - 40

def decode_percent(data: list[int]) -> float:
    """Standard percentage: A * 100 / 255"""
    return data[0] * 100 / 255

def decode_percent_centered(data: list[int]) -> float:
    """Centered percentage: (A - 128) * 100 / 128"""
    return (data[0] - 128) * 100 / 128

def decode_rpm(data: list[int]) -> float:
    """Engine RPM: ((A * 256) + B) / 4"""
    return ((data[0] * 256) + data[1]) / 4

def decode_speed(data: list[int]) -> float:
    """Vehicle speed: A (km/h)"""
    return float(data[0])

def decode_timing_advance(data: list[int]) -> float:
    """Timing advance: A / 2 - 64 (degrees before TDC)"""
    return data[0] / 2 - 64

def decode_maf(data: list[int]) -> float:
    """MAF air flow: ((A * 256) + B) / 100 (g/s)"""
    return ((data[0] * 256) + data[1]) / 100

def decode_fuel_pressure(data: list[int]) -> float:
    """Fuel pressure: A * 3 (kPa)"""
    return data[0] * 3

def decode_fuel_rail_pressure(data: list[int]) -> float:
    """Fuel rail pressure: ((A * 256) + B) * 10 (kPa)"""
    return ((data[0] * 256) + data[1]) * 10

def decode_fuel_rail_pressure_diesel(data: list[int]) -> float:
    """Fuel rail pressure (diesel): ((A * 256) + B) * 10 (kPa)"""
    return ((data[0] * 256) + data[1]) * 10

def decode_o2_voltage(data: list[int]) -> float:
    """O2 sensor voltage: A / 200 (V)"""
    return data[0] / 200

def decode_control_module_voltage(data: list[int]) -> float:
    """Control module voltage: ((A * 256) + B) / 1000 (V)"""
    return ((data[0] * 256) + data[1]) / 1000

def decode_catalyst_temp(data: list[int]) -> float:
    """Catalyst temperature: ((A * 256) + B) / 10 - 40 (°C)"""
    return ((data[0] * 256) + data[1]) / 10 - 40

def decode_fuel_rate(data: list[int]) -> float:
    """Engine fuel rate: ((A * 256) + B) / 20 (L/h)"""
    return ((data[0] * 256) + data[1]) / 20

def decode_engine_torque(data: list[int]) -> float:
    """Engine torque: A - 125 (%)"""
    return data[0] - 125

def decode_absolute_load(data: list[int]) -> float:
    """Absolute load: ((A * 256) + B) * 100 / 255 (%)"""
    return ((data[0] * 256) + data[1]) * 100 / 255

def decode_runtime(data: list[int]) -> float:
    """Run time since start: (A * 256) + B (seconds)"""
    return (data[0] * 256) + data[1]

def decode_evap_pressure(data: list[int]) -> float:
    """Evap system vapor pressure: ((A * 256) + B) / 4 - 8192 (Pa)"""
    return ((data[0] * 256) + data[1]) / 4 - 8192

def decode_barometric(data: list[int]) -> float:
    """Barometric pressure: A (kPa)"""
    return float(data[0])


# =============================================================================
# Standard OBD2 PIDs (Service 0x01)
# =============================================================================

STANDARD_PIDS: dict[int, PIDDefinition] = {
    # PIDs 0x00-0x20 - Basic engine data
    0x04: PIDDefinition(
        pid=0x04,
        name="Calculated Engine Load",
        short_name="Load",
        unit="%",
        category=PIDCategory.ENGINE,
        bytes_returned=1,
        min_value=0, max_value=100,
        formula=decode_percent,
        description="Calculated engine load value",
    ),
    0x05: PIDDefinition(
        pid=0x05,
        name="Engine Coolant Temperature",
        short_name="Coolant",
        unit="°C",
        category=PIDCategory.TEMPERATURE,
        bytes_returned=1,
        min_value=-40, max_value=215,
        formula=decode_temperature,
        description="Engine coolant temperature",
    ),
    0x06: PIDDefinition(
        pid=0x06,
        name="Short Term Fuel Trim Bank 1",
        short_name="STFT B1",
        unit="%",
        category=PIDCategory.FUEL,
        bytes_returned=1,
        min_value=-100, max_value=99.2,
        formula=decode_percent_centered,
        description="Short term fuel trim for bank 1",
    ),
    0x07: PIDDefinition(
        pid=0x07,
        name="Long Term Fuel Trim Bank 1",
        short_name="LTFT B1",
        unit="%",
        category=PIDCategory.FUEL,
        bytes_returned=1,
        min_value=-100, max_value=99.2,
        formula=decode_percent_centered,
        description="Long term fuel trim for bank 1",
    ),
    0x0B: PIDDefinition(
        pid=0x0B,
        name="Intake Manifold Pressure",
        short_name="MAP",
        unit="kPa",
        category=PIDCategory.PRESSURE,
        bytes_returned=1,
        min_value=0, max_value=255,
        formula=lambda d: float(d[0]),
        description="Intake manifold absolute pressure",
    ),
    0x0C: PIDDefinition(
        pid=0x0C,
        name="Engine RPM",
        short_name="RPM",
        unit="rpm",
        category=PIDCategory.ENGINE,
        bytes_returned=2,
        min_value=0, max_value=16383.75,
        formula=decode_rpm,
        description="Engine revolutions per minute",
    ),
    0x0D: PIDDefinition(
        pid=0x0D,
        name="Vehicle Speed",
        short_name="Speed",
        unit="km/h",
        category=PIDCategory.SPEED,
        bytes_returned=1,
        min_value=0, max_value=255,
        formula=decode_speed,
        description="Vehicle speed sensor",
    ),
    0x0E: PIDDefinition(
        pid=0x0E,
        name="Timing Advance",
        short_name="Timing",
        unit="°",
        category=PIDCategory.ENGINE,
        bytes_returned=1,
        min_value=-64, max_value=63.5,
        formula=decode_timing_advance,
        description="Timing advance relative to cylinder 1",
    ),
    0x0F: PIDDefinition(
        pid=0x0F,
        name="Intake Air Temperature",
        short_name="IAT",
        unit="°C",
        category=PIDCategory.TEMPERATURE,
        bytes_returned=1,
        min_value=-40, max_value=215,
        formula=decode_temperature,
        description="Intake air temperature",
    ),
    0x10: PIDDefinition(
        pid=0x10,
        name="MAF Air Flow Rate",
        short_name="MAF",
        unit="g/s",
        category=PIDCategory.ENGINE,
        bytes_returned=2,
        min_value=0, max_value=655.35,
        formula=decode_maf,
        description="Mass air flow sensor reading",
    ),
    0x11: PIDDefinition(
        pid=0x11,
        name="Throttle Position",
        short_name="TPS",
        unit="%",
        category=PIDCategory.ENGINE,
        bytes_returned=1,
        min_value=0, max_value=100,
        formula=decode_percent,
        description="Absolute throttle position",
    ),
    
    # PIDs 0x20-0x40 - Fuel system and emissions
    0x23: PIDDefinition(
        pid=0x23,
        name="Fuel Rail Gauge Pressure",
        short_name="FRP",
        unit="kPa",
        category=PIDCategory.FUEL,
        bytes_returned=2,
        min_value=0, max_value=655350,
        formula=decode_fuel_rail_pressure,
        description="Fuel rail gauge pressure (diesel/GDI)",
    ),
    0x2F: PIDDefinition(
        pid=0x2F,
        name="Fuel Tank Level",
        short_name="Fuel",
        unit="%",
        category=PIDCategory.FUEL,
        bytes_returned=1,
        min_value=0, max_value=100,
        formula=decode_percent,
        description="Fuel tank level input",
    ),
    
    # PIDs 0x3C-0x3F - Catalyst temperatures
    0x3C: PIDDefinition(
        pid=0x3C,
        name="Catalyst Temp Bank 1 Sensor 1",
        short_name="Cat B1S1",
        unit="°C",
        category=PIDCategory.EMISSIONS,
        bytes_returned=2,
        min_value=-40, max_value=6513.5,
        formula=decode_catalyst_temp,
        description="Catalyst temperature bank 1, sensor 1",
    ),
    0x3D: PIDDefinition(
        pid=0x3D,
        name="Catalyst Temp Bank 2 Sensor 1",
        short_name="Cat B2S1",
        unit="°C",
        category=PIDCategory.EMISSIONS,
        bytes_returned=2,
        min_value=-40, max_value=6513.5,
        formula=decode_catalyst_temp,
        description="Catalyst temperature bank 2, sensor 1",
    ),
    0x3E: PIDDefinition(
        pid=0x3E,
        name="Catalyst Temp Bank 1 Sensor 2",
        short_name="Cat B1S2",
        unit="°C",
        category=PIDCategory.EMISSIONS,
        bytes_returned=2,
        min_value=-40, max_value=6513.5,
        formula=decode_catalyst_temp,
        description="Catalyst temperature bank 1, sensor 2",
    ),
    0x3F: PIDDefinition(
        pid=0x3F,
        name="Catalyst Temp Bank 2 Sensor 2",
        short_name="Cat B2S2",
        unit="°C",
        category=PIDCategory.EMISSIONS,
        bytes_returned=2,
        min_value=-40, max_value=6513.5,
        formula=decode_catalyst_temp,
        description="Catalyst temperature bank 2, sensor 2",
    ),
    
    # PIDs 0x40-0x60 - Vehicle info
    0x42: PIDDefinition(
        pid=0x42,
        name="Control Module Voltage",
        short_name="Voltage",
        unit="V",
        category=PIDCategory.ELECTRICAL,
        bytes_returned=2,
        min_value=0, max_value=65.535,
        formula=decode_control_module_voltage,
        description="Control module voltage",
    ),
    0x46: PIDDefinition(
        pid=0x46,
        name="Ambient Air Temperature",
        short_name="Ambient",
        unit="°C",
        category=PIDCategory.TEMPERATURE,
        bytes_returned=1,
        min_value=-40, max_value=215,
        formula=decode_temperature,
        description="Ambient air temperature",
    ),
    0x5C: PIDDefinition(
        pid=0x5C,
        name="Engine Oil Temperature",
        short_name="Oil Temp",
        unit="°C",
        category=PIDCategory.TEMPERATURE,
        bytes_returned=1,
        min_value=-40, max_value=210,
        formula=decode_temperature,
        description="Engine oil temperature (if supported)",
    ),
    0x5E: PIDDefinition(
        pid=0x5E,
        name="Engine Fuel Rate",
        short_name="Fuel Rate",
        unit="L/h",
        category=PIDCategory.FUEL,
        bytes_returned=2,
        min_value=0, max_value=3212.75,
        formula=decode_fuel_rate,
        description="Engine fuel rate",
    ),
    
    # PIDs 0x60-0x80 - Torque
    0x62: PIDDefinition(
        pid=0x62,
        name="Actual Engine Torque",
        short_name="Torque %",
        unit="%",
        category=PIDCategory.ENGINE,
        bytes_returned=1,
        min_value=-125, max_value=130,
        formula=decode_engine_torque,
        description="Actual engine percent torque",
    ),
    0x63: PIDDefinition(
        pid=0x63,
        name="Engine Reference Torque",
        short_name="Ref Torque",
        unit="Nm",
        category=PIDCategory.ENGINE,
        bytes_returned=2,
        min_value=0, max_value=65535,
        formula=lambda d: (d[0] * 256) + d[1],
        description="Engine reference torque",
    ),
}


# =============================================================================
# VAG-Specific DIDs (UDS Service 0x22)
# =============================================================================

@dataclass
class VAGDIDDefinition:
    """Definition of a VAG-specific DID."""
    
    did: int                                    # Data Identifier
    name: str                                   # Human-readable name
    short_name: str                             # Short display name
    unit: str                                   # Unit of measurement
    category: PIDCategory                       # Category for grouping
    bytes_returned: int = 2                     # Expected data bytes
    formula: Optional[Callable[[list[int]], float]] = None
    measuring_block: Optional[int] = None       # VCDS measuring block number
    description: str = ""
    
    def decode(self, data_bytes: list[int]) -> Optional[float]:
        """Decode raw bytes to engineering value."""
        if self.formula is None:
            return float(data_bytes[0]) if data_bytes else None
        try:
            return self.formula(data_bytes)
        except (IndexError, ValueError, ZeroDivisionError):
            return None
    
    def get_command(self) -> str:
        """Get the UDS command string for this DID."""
        return f"22{self.did:04X}"


# Known VAG DIDs for MK5 GTI (EA113 2.0T FSI / Bosch MED9.1)
VAG_DIDS: dict[int, VAGDIDDefinition] = {
    # Oil temperature - VCDS Block 134
    0xF486: VAGDIDDefinition(
        did=0xF486,
        name="Engine Oil Temperature",
        short_name="Oil Temp",
        unit="°C",
        category=PIDCategory.TEMPERATURE,
        bytes_returned=1,
        formula=decode_temperature,
        measuring_block=134,
        description="Engine oil temperature (VCDS Block 134, Field 1)",
    ),
    
    # Alternative oil temp locations
    0xF40E: VAGDIDDefinition(
        did=0xF40E,
        name="Oil Temperature (Alt)",
        short_name="Oil Temp",
        unit="°C",
        category=PIDCategory.TEMPERATURE,
        bytes_returned=1,
        formula=decode_temperature,
        description="Alternative oil temperature DID",
    ),
    0x2028: VAGDIDDefinition(
        did=0x2028,
        name="Oil Temperature (2028)",
        short_name="Oil Temp",
        unit="°C",
        category=PIDCategory.TEMPERATURE,
        bytes_returned=1,
        formula=decode_temperature,
        description="Oil temperature via DID 0x2028",
    ),
    
    # ECU identification
    0xF189: VAGDIDDefinition(
        did=0xF189,
        name="ECU Software Version",
        short_name="SW Ver",
        unit="",
        category=PIDCategory.ENGINE,
        bytes_returned=16,
        formula=None,  # ASCII string
        description="ECU software version identifier",
    ),
    0xF190: VAGDIDDefinition(
        did=0xF190,
        name="VIN",
        short_name="VIN",
        unit="",
        category=PIDCategory.ENGINE,
        bytes_returned=17,
        formula=None,  # ASCII string
        description="Vehicle Identification Number",
    ),
    
    # Boost pressure
    0xF406: VAGDIDDefinition(
        did=0xF406,
        name="Boost Pressure Actual",
        short_name="Boost",
        unit="mbar",
        category=PIDCategory.PRESSURE,
        bytes_returned=2,
        formula=lambda d: (d[0] * 256 + d[1]) * 0.1,
        measuring_block=6,
        description="Actual boost pressure",
    ),
    
    # Timing / knock
    0xF41F: VAGDIDDefinition(
        did=0xF41F,
        name="Ignition Timing Cylinder 1",
        short_name="Ign Cyl1",
        unit="°",
        category=PIDCategory.ENGINE,
        bytes_returned=1,
        formula=lambda d: d[0] * 0.75 - 48,
        measuring_block=31,
        description="Ignition timing for cylinder 1",
    ),
}


# Quick lookup for common parameters
COMMON_PIDS = [0x04, 0x05, 0x0B, 0x0C, 0x0D, 0x0F, 0x10, 0x11]  # Load, Coolant, MAP, RPM, Speed, IAT, MAF, TPS
TEMPERATURE_PIDS = [0x05, 0x0F, 0x46, 0x5C]  # Coolant, IAT, Ambient, Oil
VAG_OIL_TEMP_DIDS = [0xF486, 0xF40E, 0x2028]


def get_all_pids() -> dict[int, PIDDefinition]:
    """Get all standard PIDs."""
    return STANDARD_PIDS.copy()


def get_pid(pid: int) -> Optional[PIDDefinition]:
    """Get a PID definition by number."""
    return STANDARD_PIDS.get(pid)


def get_vag_did(did: int) -> Optional[VAGDIDDefinition]:
    """Get a VAG DID definition by number."""
    return VAG_DIDS.get(did)
