"""Tests for configuration management."""

import pytest
from pathlib import Path

from app.config import Config


class TestConfig:
    """Tests for the Config class."""

    def test_default_config_when_file_missing(self, temp_dir: Path):
        """Config should return defaults when file doesn't exist."""
        config = Config(str(temp_dir / "nonexistent.yaml"))

        assert config.server_port == 9090
        assert config.server_host == "0.0.0.0"
        assert config.powerwall_mode == "local"
        assert config.powerwall_host == ""
        assert config.powerwall_email == ""
        assert config.powerwall_password == ""
        assert config.monitoring_interval == 5
        assert config.automation_cooldown == 30
        assert config.automation_average_window == 20

    def test_save_and_reload(self, config: Config):
        """Config should persist changes after save and reload."""
        config.powerwall_host = "192.168.1.100"
        config.powerwall_email = "test@example.com"
        config.powerwall_password = "secret"
        config.powerwall_mode = "local"
        config.save()

        # Create new instance to verify persistence
        reloaded = Config(str(config.config_path))

        assert reloaded.powerwall_host == "192.168.1.100"
        assert reloaded.powerwall_email == "test@example.com"
        assert reloaded.powerwall_password == "secret"
        assert reloaded.powerwall_mode == "local"

    def test_reload_updates_config(self, config: Config, temp_config_file: Path):
        """Config.reload() should pick up external changes."""
        config.powerwall_host = "192.168.1.1"
        config.save()

        # Modify file externally
        temp_config_file.write_text(
            "powerwall:\n  host: 192.168.1.200\n  email: new@example.com\n"
        )

        config.reload()

        assert config.powerwall_host == "192.168.1.200"
        assert config.powerwall_email == "new@example.com"


class TestIsConfigured:
    """Tests for the is_configured method."""

    def test_local_mode_requires_host_email_password(self, config: Config):
        """Local mode requires host, email, and password."""
        config.powerwall_mode = "local"
        config.powerwall_host = ""
        config.powerwall_email = ""
        config.powerwall_password = ""

        assert config.is_configured() is False

        config.powerwall_host = "192.168.1.100"
        assert config.is_configured() is False

        config.powerwall_email = "test@example.com"
        assert config.is_configured() is False

        config.powerwall_password = "secret"
        assert config.is_configured() is True

    def test_fleetapi_mode_requires_email(self, config: Config):
        """FleetAPI mode only requires email."""
        config.powerwall_mode = "fleetapi"
        config.powerwall_email = ""

        assert config.is_configured() is False

        config.powerwall_email = "test@example.com"
        assert config.is_configured() is True

    def test_cloud_mode_requires_email(self, config: Config):
        """Cloud mode only requires email."""
        config.powerwall_mode = "cloud"
        config.powerwall_email = ""

        assert config.is_configured() is False

        config.powerwall_email = "test@example.com"
        assert config.is_configured() is True

    def test_tedapi_mode_requires_gw_password(self, config: Config):
        """TEDAPI mode requires gateway password."""
        config.powerwall_mode = "tedapi"
        config.powerwall_gw_password = ""

        assert config.is_configured() is False

        config.powerwall_gw_password = "ABCDEFGHIJ"
        assert config.is_configured() is True


class TestAutomationRules:
    """Tests for automation rules in config."""

    def test_default_empty_rules(self, config: Config):
        """Default config should have empty rules list."""
        assert config.automation_rules == []

    def test_set_and_get_rules(self, config: Config):
        """Rules can be set and retrieved."""
        rules = [
            {"id": "1", "name": "Rule 1", "threshold": 5.0},
            {"id": "2", "name": "Rule 2", "threshold": 10.0},
        ]
        config.automation_rules = rules
        config.save()

        reloaded = Config(str(config.config_path))
        assert len(reloaded.automation_rules) == 2
        assert reloaded.automation_rules[0]["name"] == "Rule 1"
