"""Shared pytest fixtures for Powerwall Controller tests."""

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.services.automation_service import AutomationRule, AutomationService, RuleOperator
from app.services.monitoring_service import MonitoringService, PowerwallMetrics
from app.services.storage_service import StorageService


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_config_file(temp_dir: Path) -> Path:
    """Create a temporary config file."""
    config_path = temp_dir / "config.yaml"
    config_path.write_text("")
    return config_path


@pytest.fixture
def config(temp_config_file: Path) -> Config:
    """Create a Config instance with temporary file."""
    return Config(str(temp_config_file))


@pytest.fixture
def storage_service(temp_dir: Path) -> StorageService:
    """Create a StorageService with temporary data directory."""
    service = StorageService()
    service.data_dir = temp_dir
    service.metrics_dir = temp_dir / "metrics"
    service.audit_dir = temp_dir / "audit"
    service.initialize()
    return service


@pytest.fixture
def sample_metrics() -> PowerwallMetrics:
    """Create sample PowerwallMetrics for testing."""
    return PowerwallMetrics(
        timestamp=datetime.now(),
        battery_percentage=75.5,
        battery_power=2.5,
        solar_power=5.0,
        home_power=3.5,
        grid_power=-1.5,
        backup_reserve=20.0,
        grid_status="Connected",
        battery_capacity=13.5,
    )


@pytest.fixture
def sample_metrics_list() -> list[PowerwallMetrics]:
    """Create a list of sample metrics for testing."""
    base_time = datetime.now()
    return [
        PowerwallMetrics(
            timestamp=base_time,
            battery_percentage=70.0 + i,
            battery_power=2.0 + i * 0.5,
            solar_power=5.0,
            home_power=3.0 + i * 0.2,
            grid_power=-1.0,
            backup_reserve=20.0,
            grid_status="Connected",
            battery_capacity=13.5,
        )
        for i in range(5)
    ]


@pytest.fixture
def sample_rule() -> AutomationRule:
    """Create a sample automation rule for testing."""
    return AutomationRule(
        id="test-rule-1",
        name="Test Rule",
        operator=RuleOperator.GREATER_THAN,
        threshold=5.0,
        target_reserve=80.0,
        enabled=True,
        order=0,
    )


@pytest.fixture
def automation_service(config: Config) -> AutomationService:
    """Create an AutomationService for testing."""
    with patch("app.services.automation_service.config", config):
        service = AutomationService()
        service._rules = []
        return service


@pytest.fixture
def mock_powerwall():
    """Create a mock pypowerwall.Powerwall instance."""
    mock = MagicMock()
    mock.poll.return_value = {
        "battery_percentage": 75.5,
        "battery_power": 2500,
        "solar_power": 5000,
        "home_power": 3500,
        "grid_power": -1500,
        "grid_status": "Connected",
    }
    mock.level.return_value = 75.5
    mock.power.return_value = {"battery": 2500, "solar": 5000, "home": 3500, "grid": -1500}
    mock.grid.return_value = True
    mock.get_reserve.return_value = 20.0
    mock.set_reserve.return_value = True
    return mock


@pytest.fixture
def test_client():
    """Create a FastAPI test client."""
    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
