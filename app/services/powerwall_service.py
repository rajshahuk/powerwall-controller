"""Powerwall service for communicating with Tesla Powerwall using pypowerwall."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import pypowerwall

from app.config import config


# Connection mode constants
MODE_LOCAL = "local"       # Direct LAN access for PW2/PW+
MODE_FLEETAPI = "fleetapi" # Official Tesla Fleet API
MODE_CLOUD = "cloud"       # Unofficial Tesla Owners API
MODE_TEDAPI = "tedapi"     # Local TEDAPI for PW3


@dataclass
class PowerwallMetrics:
    """Metrics collected from the Powerwall."""
    timestamp: datetime
    battery_percentage: float
    battery_power: float  # kW (positive = discharging, negative = charging)
    solar_power: float  # kW
    home_power: float  # kW (load consumption)
    grid_power: float  # kW (positive = importing, negative = exporting)
    backup_reserve: float  # percentage
    grid_status: str
    battery_capacity: float  # kWh


@dataclass
class ConnectionTestResult:
    """Result of a connectivity test."""
    success: bool
    steps: list  # List of (step_name, success, message) tuples
    error: Optional[str] = None


class PowerwallService:
    """Service for interacting with Tesla Powerwall via pypowerwall."""

    def __init__(self):
        self._powerwall: Optional[pypowerwall.Powerwall] = None
        self._connected = False
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _create_powerwall(self) -> pypowerwall.Powerwall:
        """Create a pypowerwall instance based on configuration."""
        mode = config.powerwall_mode
        host = config.powerwall_host
        email = config.powerwall_email
        password = config.powerwall_password
        timezone = config.powerwall_timezone
        gw_pwd = config.powerwall_gw_password

        if mode == MODE_LOCAL:
            # Mode 1: Local access to PW2/PW+ via LAN
            return pypowerwall.Powerwall(
                host=host,
                password=password,
                email=email,
                timezone=timezone
            )

        elif mode == MODE_FLEETAPI:
            # Mode 2: Official Tesla Fleet API (cloud)
            return pypowerwall.Powerwall(
                host="",
                password="",
                email=email,
                timezone=timezone,
                fleetapi=True,
                auto_select=True
            )

        elif mode == MODE_CLOUD:
            # Mode 3: Unofficial Tesla Owners API (cloud)
            return pypowerwall.Powerwall(
                host="",
                password="",
                email=email,
                timezone=timezone,
                cloudmode=True,
                auto_select=True
            )

        elif mode == MODE_TEDAPI:
            # Mode 4: TEDAPI local access for PW3
            return pypowerwall.Powerwall(
                host=host or "192.168.91.1",
                password="",
                email="",
                timezone=timezone,
                gw_pwd=gw_pwd,
                auto_select=True
            )

        else:
            # Default to local mode
            return pypowerwall.Powerwall(
                host=host,
                password=password,
                email=email,
                timezone=timezone,
                auto_select=True
            )

    async def connect(self) -> bool:
        """Connect to the Powerwall."""
        async with self._lock:
            try:
                self._powerwall = await asyncio.to_thread(self._create_powerwall)
                # Test the connection by getting battery level (scale=True to match Tesla app)
                level = await asyncio.to_thread(self._powerwall.level, scale=True)
                if level is not None:
                    self._connected = True
                    return True
                else:
                    raise Exception("Could not retrieve battery level")
            except Exception as e:
                self._connected = False
                self._powerwall = None
                raise Exception(f"Failed to connect: {str(e)}")

    async def disconnect(self) -> None:
        """Disconnect from the Powerwall."""
        async with self._lock:
            self._powerwall = None
            self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test connectivity to the Powerwall with detailed diagnostics."""
        steps = []
        mode = config.powerwall_mode

        # Step 1: Validate configuration based on mode
        mode_names = {
            MODE_LOCAL: "Local (PW2/PW+)",
            MODE_FLEETAPI: "FleetAPI (Cloud)",
            MODE_CLOUD: "Cloud Mode",
            MODE_TEDAPI: "TEDAPI (PW3 Local)"
        }
        mode_display = mode_names.get(mode, mode)

        if mode == MODE_LOCAL:
            if not config.powerwall_host:
                steps.append(("Check configuration", False, "Local mode requires Powerwall host IP"))
                return ConnectionTestResult(success=False, steps=steps, error="Host not configured")
            if not config.powerwall_email or not config.powerwall_password:
                steps.append(("Check configuration", False, "Local mode requires email and password"))
                return ConnectionTestResult(success=False, steps=steps, error="Credentials not configured")
            steps.append(("Check configuration", True, f"Mode: {mode_display}, Host: {config.powerwall_host}"))

        elif mode == MODE_FLEETAPI:
            if not config.powerwall_email:
                steps.append(("Check configuration", False, "FleetAPI mode requires Tesla email"))
                return ConnectionTestResult(success=False, steps=steps, error="Email not configured")
            steps.append(("Check configuration", True, f"Mode: {mode_display}, Email: {config.powerwall_email}"))

        elif mode == MODE_CLOUD:
            if not config.powerwall_email:
                steps.append(("Check configuration", False, "Cloud mode requires Tesla email"))
                return ConnectionTestResult(success=False, steps=steps, error="Email not configured")
            steps.append(("Check configuration", True, f"Mode: {mode_display}, Email: {config.powerwall_email}"))

        elif mode == MODE_TEDAPI:
            if not config.powerwall_gw_password:
                steps.append(("Check configuration", False, "TEDAPI mode requires Gateway WiFi password"))
                return ConnectionTestResult(success=False, steps=steps, error="Gateway password not configured")
            host = config.powerwall_host or "192.168.91.1"
            steps.append(("Check configuration", True, f"Mode: {mode_display}, Host: {host}"))

        else:
            steps.append(("Check configuration", False, f"Unknown mode: {mode}"))
            return ConnectionTestResult(success=False, steps=steps, error="Unknown mode")

        # Step 2: Try to create Powerwall instance
        try:
            pw = await asyncio.to_thread(self._create_powerwall)
            steps.append(("Create connection", True, f"Powerwall instance created ({mode_display})"))
        except Exception as e:
            steps.append(("Create connection", False, f"Failed: {str(e)}"))
            return ConnectionTestResult(success=False, steps=steps, error=str(e))

        # Step 3: Try to get battery level (scale=True to match Tesla app)
        try:
            level = await asyncio.to_thread(pw.level, scale=True)
            if level is not None:
                steps.append(("Get battery level", True, f"Current charge: {level:.1f}%"))
            else:
                steps.append(("Get battery level", False, "Battery level returned None"))
                return ConnectionTestResult(success=False, steps=steps, error="Could not read battery level")
        except Exception as e:
            steps.append(("Get battery level", False, f"Failed: {str(e)}"))
            return ConnectionTestResult(success=False, steps=steps, error=str(e))

        # Step 4: Try to get power readings
        try:
            solar = await asyncio.to_thread(pw.solar)
            grid = await asyncio.to_thread(pw.grid)
            home = await asyncio.to_thread(pw.home)
            battery = await asyncio.to_thread(pw.battery)
            steps.append(("Get power readings", True,
                f"Solar: {float(solar or 0)/1000:.2f}kW, Home: {float(home or 0)/1000:.2f}kW"))
        except Exception as e:
            steps.append(("Get power readings", False, f"Failed: {str(e)}"))

        # Step 5: Check grid status
        try:
            grid_status = await asyncio.to_thread(pw.grid_status)
            steps.append(("Get grid status", True, f"Grid: {grid_status}"))
        except Exception as e:
            steps.append(("Get grid status", False, f"Failed: {str(e)}"))

        all_success = all(step[1] for step in steps)
        return ConnectionTestResult(success=all_success, steps=steps)

    async def get_metrics(self) -> PowerwallMetrics:
        """Get current metrics from the Powerwall."""
        if not self._connected or not self._powerwall:
            raise Exception("Not connected to Powerwall")

        try:
            pw = self._powerwall

            # Get all data (scale=True to match Tesla app's 5% reserve calculation)
            level = await asyncio.to_thread(pw.level, scale=True)
            solar = await asyncio.to_thread(pw.solar)
            grid = await asyncio.to_thread(pw.grid)
            home = await asyncio.to_thread(pw.home)
            battery = await asyncio.to_thread(pw.battery)
            grid_status = await asyncio.to_thread(pw.grid_status)

            # Convert W to kW
            solar_kw = float(solar or 0) / 1000.0
            grid_kw = float(grid or 0) / 1000.0
            home_kw = float(home or 0) / 1000.0
            battery_kw = float(battery or 0) / 1000.0

            # Get backup reserve using pypowerwall's method (scale=True for Tesla app value)
            backup_reserve = 20.0  # Default
            try:
                reserve = await asyncio.to_thread(pw.get_reserve, scale=True)
                if reserve is not None:
                    backup_reserve = float(reserve)
            except Exception:
                pass

            # Try to get battery capacity
            capacity = 13.5  # Default PW3 capacity
            try:
                system = await asyncio.to_thread(lambda: pw.poll('/api/system_status/soe'))
                if system and 'percentage' in system:
                    pass
            except Exception:
                pass

            return PowerwallMetrics(
                timestamp=datetime.now(),
                battery_percentage=float(level or 0),
                battery_power=battery_kw,
                solar_power=solar_kw,
                home_power=home_kw,
                grid_power=grid_kw,
                backup_reserve=backup_reserve,
                grid_status=str(grid_status) if grid_status else "Unknown",
                battery_capacity=capacity
            )
        except Exception as e:
            self._connected = False
            raise Exception(f"Failed to get metrics: {str(e)}")

    async def set_backup_reserve(self, percentage: float) -> bool:
        """Set the backup reserve percentage."""
        if not self._connected or not self._powerwall:
            raise Exception("Not connected to Powerwall")

        percentage = max(0, min(100, percentage))

        try:
            result = await asyncio.to_thread(
                self._powerwall.set_reserve,
                percentage
            )
            return True
        except Exception as e:
            raise Exception(f"Failed to set backup reserve: {str(e)}")

    async def get_backup_reserve(self) -> float:
        """Get the current backup reserve percentage (scaled to match Tesla app)."""
        if not self._connected or not self._powerwall:
            raise Exception("Not connected to Powerwall")

        try:
            # force=True to bypass any caching
            reserve = await asyncio.to_thread(self._powerwall.get_reserve, scale=True, force=True)
            if reserve is not None:
                return float(reserve)
            return 20.0
        except Exception as e:
            raise Exception(f"Failed to get backup reserve: {str(e)}")


# Global service instance
powerwall_service = PowerwallService()
