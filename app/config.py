"""Configuration management for Powerwall Controller."""

import os
from pathlib import Path
from typing import Optional
import yaml

CONFIG_FILE = os.environ.get("POWERWALL_CONFIG", "config.yaml")


class Config:
    """Application configuration loaded from YAML file."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path or CONFIG_FILE)
        self._config = self._load_config()

    def _load_config(self) -> dict:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            return self._default_config()

        with open(self.config_path, "r") as f:
            return yaml.safe_load(f) or self._default_config()

    def _default_config(self) -> dict:
        """Return default configuration."""
        return {
            "server": {
                "port": 9090,
                "host": "0.0.0.0"
            },
            "powerwall": {
                "host": "",
                "email": "",
                "password": ""
            },
            "storage": {
                "data_dir": "./data"
            },
            "monitoring": {
                "interval": 5
            },
            "automation": {
                "cooldown": 30,
                "average_window": 20,
                "rules": []
            }
        }

    def save(self) -> None:
        """Save current configuration to file."""
        with open(self.config_path, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False)

    def reload(self) -> None:
        """Reload configuration from file."""
        self._config = self._load_config()

    @property
    def server_port(self) -> int:
        return self._config.get("server", {}).get("port", 9090)

    @property
    def server_host(self) -> str:
        return self._config.get("server", {}).get("host", "0.0.0.0")

    @property
    def powerwall_mode(self) -> str:
        """Connection mode: local, fleetapi, cloud, or tedapi."""
        return self._config.get("powerwall", {}).get("mode", "local")

    @powerwall_mode.setter
    def powerwall_mode(self, value: str) -> None:
        if "powerwall" not in self._config:
            self._config["powerwall"] = {}
        self._config["powerwall"]["mode"] = value

    @property
    def powerwall_host(self) -> str:
        return self._config.get("powerwall", {}).get("host", "")

    @powerwall_host.setter
    def powerwall_host(self, value: str) -> None:
        if "powerwall" not in self._config:
            self._config["powerwall"] = {}
        self._config["powerwall"]["host"] = value

    @property
    def powerwall_email(self) -> str:
        return self._config.get("powerwall", {}).get("email", "")

    @powerwall_email.setter
    def powerwall_email(self, value: str) -> None:
        if "powerwall" not in self._config:
            self._config["powerwall"] = {}
        self._config["powerwall"]["email"] = value

    @property
    def powerwall_password(self) -> str:
        return self._config.get("powerwall", {}).get("password", "")

    @powerwall_password.setter
    def powerwall_password(self, value: str) -> None:
        if "powerwall" not in self._config:
            self._config["powerwall"] = {}
        self._config["powerwall"]["password"] = value

    @property
    def powerwall_timezone(self) -> str:
        return self._config.get("powerwall", {}).get("timezone", "America/Los_Angeles")

    @powerwall_timezone.setter
    def powerwall_timezone(self, value: str) -> None:
        if "powerwall" not in self._config:
            self._config["powerwall"] = {}
        self._config["powerwall"]["timezone"] = value

    @property
    def powerwall_gw_password(self) -> str:
        """Gateway WiFi password for TEDAPI mode (from QR sticker on Powerwall)."""
        return self._config.get("powerwall", {}).get("gw_password", "")

    @powerwall_gw_password.setter
    def powerwall_gw_password(self, value: str) -> None:
        if "powerwall" not in self._config:
            self._config["powerwall"] = {}
        self._config["powerwall"]["gw_password"] = value

    @property
    def data_dir(self) -> Path:
        return Path(self._config.get("storage", {}).get("data_dir", "./data"))

    @property
    def monitoring_interval(self) -> int:
        return self._config.get("monitoring", {}).get("interval", 5)

    @property
    def automation_cooldown(self) -> int:
        return self._config.get("automation", {}).get("cooldown", 30)

    @property
    def automation_average_window(self) -> int:
        return self._config.get("automation", {}).get("average_window", 20)

    @property
    def automation_rules(self) -> list:
        return self._config.get("automation", {}).get("rules", [])

    @automation_rules.setter
    def automation_rules(self, value: list) -> None:
        if "automation" not in self._config:
            self._config["automation"] = {}
        self._config["automation"]["rules"] = value

    def is_configured(self) -> bool:
        """Check if Powerwall connection is configured based on mode."""
        mode = self.powerwall_mode

        if mode == "local":
            # Local mode needs host, email, and password
            return bool(self.powerwall_host and self.powerwall_email and self.powerwall_password)
        elif mode == "fleetapi" or mode == "cloud":
            # Cloud modes only need email (credentials cached from setup)
            return bool(self.powerwall_email)
        elif mode == "tedapi":
            # TEDAPI needs gateway password
            return bool(self.powerwall_gw_password)
        else:
            # Unknown mode, check basic fields
            return bool(self.powerwall_email)


# Global configuration instance
config = Config()
