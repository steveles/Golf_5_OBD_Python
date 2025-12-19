"""
Command-line interface for Golf GTI OBD reader.

Provides live display of OBD2 data using rich for nice terminal output.
"""

import argparse
import logging
import sys
import time
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout

from .connection import ELM327Connection, Protocol, AdapterInfo
from .pids import STANDARD_PIDS, VAG_DIDS, COMMON_PIDS, get_pid
from .reader import OBDReader, Reading

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )


def create_connection_panel(adapter_info: Optional[AdapterInfo]) -> Panel:
    """Create panel showing connection info."""
    if adapter_info is None:
        return Panel(
            Text("Not connected", style="red"),
            title="Connection",
            border_style="red",
        )
    
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    
    table.add_row("Adapter", adapter_info.device_id.split('\n')[0])
    table.add_row("Battery", f"{adapter_info.voltage:.1f}V" if adapter_info.voltage else "N/A")
    table.add_row("Protocol", adapter_info.protocol_name or "Unknown")
    
    return Panel(table, title="🔌 Connection", border_style="green")


def create_readings_table(readings: dict[str, Reading], title: str = "Readings") -> Table:
    """Create a table of readings."""
    table = Table(title=title, show_lines=True)
    
    table.add_column("Parameter", style="cyan", width=25)
    table.add_column("Value", style="white", justify="right", width=12)
    table.add_column("Unit", style="dim", width=8)
    table.add_column("Status", width=10)
    
    for name, reading in readings.items():
        if reading.is_valid:
            value_str = f"{reading.value:.1f}" if reading.value is not None else "N/A"
            status = Text("✓ OK", style="green")
        else:
            value_str = "---"
            status = Text(f"✗ {reading.error[:15]}" if reading.error else "✗ Error", style="red")
        
        table.add_row(reading.name, value_str, reading.unit, status)
    
    return table


def create_dashboard(
    adapter_info: Optional[AdapterInfo],
    readings: dict[str, Reading],
    vag_readings: dict[str, Reading],
    refresh_rate: float,
) -> Layout:
    """Create the full dashboard layout."""
    layout = Layout()
    
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    
    # Header
    layout["header"].update(
        Panel(
            Text("🚗 MK5 Golf GTI OBD2 Dashboard", style="bold white", justify="center"),
            border_style="blue",
        )
    )
    
    # Body - split into columns
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )
    
    # Left column - connection + standard PIDs
    left_content = Layout()
    left_content.split_column(
        Layout(create_connection_panel(adapter_info), size=7),
        Layout(create_readings_table(readings, "📊 Standard OBD2")),
    )
    layout["left"].update(left_content)
    
    # Right column - VAG specific + DTC
    right_content = Layout()
    right_content.split_column(
        Layout(create_readings_table(vag_readings, "🔧 VAG-Specific")),
    )
    layout["right"].update(right_content)
    
    # Footer
    layout["footer"].update(
        Panel(
            Text(f"Refresh: {refresh_rate:.1f}s | Press Ctrl+C to exit", justify="center"),
            border_style="dim",
        )
    )
    
    return layout


def run_live_display(reader: OBDReader, adapter_info: AdapterInfo, refresh_rate: float = 1.0):
    """Run live updating dashboard."""
    # PIDs to monitor
    monitor_pids = [0x05, 0x0C, 0x0D, 0x0F, 0x10, 0x11, 0x04, 0x0B]  # Coolant, RPM, Speed, IAT, MAF, TPS, Load, MAP
    
    # VAG DIDs to try
    vag_dids = [0xF486, 0x2028]
    
    readings: dict[str, Reading] = {}
    vag_readings: dict[str, Reading] = {}
    
    with Live(console=console, refresh_per_second=4) as live:
        try:
            while True:
                # Read standard PIDs
                for pid in monitor_pids:
                    reading = reader.read_pid(pid)
                    readings[reading.short_name] = reading
                
                # Read VAG DIDs
                for did in vag_dids:
                    reading = reader.read_vag_did(did)
                    vag_readings[reading.short_name] = reading
                
                # Update display
                dashboard = create_dashboard(adapter_info, readings, vag_readings, refresh_rate)
                live.update(dashboard)
                
                time.sleep(refresh_rate)
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Dashboard stopped by user[/yellow]")


def run_scan(reader: OBDReader):
    """Run PID/DID scan and display results."""
    console.print("\n[cyan]Scanning for supported PIDs...[/cyan]")
    
    # Scan standard PIDs
    supported_pids = reader.scan_supported_pids()
    
    table = Table(title="Supported Standard PIDs")
    table.add_column("PID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Current Value", style="green")
    
    for pid in sorted(supported_pids):
        pid_def = get_pid(pid)
        if pid_def:
            reading = reader.read_pid(pid)
            value_str = reading.format_value() if reading.is_valid else "N/A"
            table.add_row(f"0x{pid:02X}", pid_def.name, value_str)
        else:
            table.add_row(f"0x{pid:02X}", "Unknown", "-")
    
    console.print(table)
    
    # Scan VAG DIDs
    console.print("\n[cyan]Scanning for VAG-specific DIDs...[/cyan]")
    
    # Try to enter extended session for more DIDs
    if reader.enter_extended_session():
        console.print("[green]Extended diagnostic session active[/green]")
    
    vag_table = Table(title="VAG-Specific DIDs")
    vag_table.add_column("DID", style="cyan")
    vag_table.add_column("Name", style="white")
    vag_table.add_column("Value", style="green")
    vag_table.add_column("Status", style="dim")
    
    for did, did_def in VAG_DIDS.items():
        reading = reader.read_vag_did(did)
        if reading.is_valid:
            vag_table.add_row(
                f"0x{did:04X}",
                did_def.name,
                reading.format_value(),
                "[green]✓ Supported[/green]"
            )
        else:
            vag_table.add_row(
                f"0x{did:04X}",
                did_def.name,
                "-",
                f"[red]✗ {reading.error or 'No response'}[/red]"
            )
    
    console.print(vag_table)


def run_single_read(reader: OBDReader, pids: list[int], vag_dids: list[int]):
    """Read specific PIDs/DIDs once and display."""
    results = []
    
    for pid in pids:
        reading = reader.read_pid(pid)
        results.append(reading)
    
    for did in vag_dids:
        reading = reader.read_vag_did(did)
        results.append(reading)
    
    table = Table(title="OBD2 Readings")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", justify="right")
    table.add_column("Unit", style="dim")
    table.add_column("Raw", style="dim")
    
    for reading in results:
        if reading.is_valid:
            table.add_row(
                reading.name,
                f"{reading.value:.2f}",
                reading.unit,
                reading.raw_hex[:20],
            )
        else:
            table.add_row(
                reading.name,
                "[red]Error[/red]",
                reading.unit,
                reading.error or "",
            )
    
    console.print(table)


def run_oil_temp_search(reader: OBDReader):
    """Search for oil temperature reading."""
    console.print("\n[cyan]Searching for oil temperature reading...[/cyan]\n")
    
    # Try standard PID first
    console.print("[dim]Trying standard OBD2 PID 0x5C...[/dim]")
    reading = reader.read_pid(0x5C)
    if reading.is_valid:
        console.print(f"[green]✓ Found via PID 0x5C: {reading.format_value()}[/green]")
        return
    else:
        console.print(f"[yellow]  Not supported: {reading.error}[/yellow]")
    
    # Try VAG DIDs
    vag_dids = [
        (0xF486, "VCDS Block 134"),
        (0xF40E, "Alternative DID"),
        (0x2028, "Engine sensors"),
        (0x1040, "Oil temp DID"),
    ]
    
    for did, description in vag_dids:
        console.print(f"[dim]Trying VAG DID 0x{did:04X} ({description})...[/dim]")
        reading = reader.read_vag_did(did)
        if reading.is_valid:
            console.print(f"[green]✓ Found via DID 0x{did:04X}: {reading.format_value()}[/green]")
            console.print(f"\n[cyan]To read this in your code:[/cyan]")
            console.print(f"  reader.read_vag_did(0x{did:04X})")
            return
        else:
            console.print(f"[yellow]  Not supported: {reading.error}[/yellow]")
    
    # Try extended session
    console.print("\n[dim]Trying extended diagnostic session...[/dim]")
    if reader.enter_extended_session():
        console.print("[green]  Extended session active[/green]")
        
        for did, description in vag_dids:
            console.print(f"[dim]Retrying VAG DID 0x{did:04X}...[/dim]")
            reading = reader.read_vag_did(did)
            if reading.is_valid:
                console.print(f"[green]✓ Found in extended session via 0x{did:04X}: {reading.format_value()}[/green]")
                console.print(f"\n[cyan]To read this in your code:[/cyan]")
                console.print(f"  reader.enter_extended_session()")
                console.print(f"  reader.read_vag_did(0x{did:04X})")
                return
    
    console.print("\n[red]Could not find oil temperature reading[/red]")
    console.print("[yellow]Your ECU may require different DIDs or security access.[/yellow]")
    console.print("[yellow]Try running a DID scan with --scan to discover available parameters.[/yellow]")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MK5 Golf GTI OBD2 Reader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Connect and show live dashboard
  golf-obd --port /dev/rfcomm0 --live
  
  # Scan for supported PIDs
  golf-obd --port COM3 --scan
  
  # Search for oil temperature
  golf-obd --port /dev/tty.OBDLinkMX --oil-temp
  
  # Read specific PIDs
  golf-obd --port /dev/rfcomm0 --pids 0x05 0x0C 0x0D
        """,
    )
    
    parser.add_argument(
        "-p", "--port",
        default="/dev/rfcomm0",
        help="Serial port (default: /dev/rfcomm0)",
    )
    parser.add_argument(
        "-b", "--baudrate",
        type=int,
        default=115200,
        help="Baud rate (default: 115200 for OBDLink MX+)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live dashboard with auto-refresh",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan for supported PIDs and DIDs",
    )
    parser.add_argument(
        "--oil-temp",
        action="store_true",
        help="Search for oil temperature reading",
    )
    parser.add_argument(
        "--pids",
        nargs="+",
        type=lambda x: int(x, 0),  # Accepts hex (0x05) or decimal
        help="Specific PIDs to read (e.g., 0x05 0x0C)",
    )
    parser.add_argument(
        "--vag-dids",
        nargs="+",
        type=lambda x: int(x, 0),
        help="Specific VAG DIDs to read (e.g., 0xF486)",
    )
    parser.add_argument(
        "--refresh",
        type=float,
        default=1.0,
        help="Live dashboard refresh rate in seconds (default: 1.0)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    # Header
    console.print(Panel.fit(
        "[bold blue]🚗 MK5 Golf GTI OBD2 Reader[/bold blue]\n"
        "[dim]Standard OBD2 + VAG-specific parameter support[/dim]",
        border_style="blue",
    ))
    
    # Connect to adapter
    console.print(f"\n[cyan]Connecting to {args.port}...[/cyan]")
    
    try:
        with ELM327Connection(port=args.port, baudrate=args.baudrate) as connection:
            if not connection.connected:
                console.print("[red]Failed to open serial port[/red]")
                sys.exit(1)
            
            console.print("[green]Serial connection established[/green]")
            
            # Initialize adapter
            console.print("[cyan]Initializing adapter...[/cyan]")
            if not connection.initialize():
                console.print("[red]Failed to initialize adapter or ECU not responding[/red]")
                console.print("[yellow]Check that ignition is ON[/yellow]")
                sys.exit(1)
            
            # Get adapter info
            adapter_info = connection.get_adapter_info()
            console.print(f"[green]Connected: {adapter_info.device_id.split(chr(10))[0]}[/green]")
            console.print(f"[dim]Battery: {adapter_info.voltage:.1f}V | Protocol: {adapter_info.protocol_name}[/dim]")
            
            # Create reader
            reader = OBDReader(connection)
            
            # Run requested mode
            if args.live:
                run_live_display(reader, adapter_info, args.refresh)
            elif args.scan:
                run_scan(reader)
            elif args.oil_temp:
                run_oil_temp_search(reader)
            elif args.pids or args.vag_dids:
                run_single_read(
                    reader,
                    args.pids or [],
                    args.vag_dids or [],
                )
            else:
                # Default: show basic readings once
                console.print("\n[cyan]Reading basic parameters...[/cyan]\n")
                run_single_read(reader, COMMON_PIDS, [])
                console.print("\n[dim]Use --live for continuous updates, --scan to discover parameters[/dim]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if args.verbose:
            console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
