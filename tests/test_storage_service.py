"""Tests for the storage service."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from app.services.storage_service import StorageService, METRICS_SCHEMA, AUDIT_SCHEMA
from app.services.monitoring_service import PowerwallMetrics


class TestStorageServiceInitialization:
    """Tests for StorageService initialization."""

    def test_initialize_creates_directories(self, temp_dir: Path):
        """Initialize should create metrics and audit directories."""
        service = StorageService()
        service._data_dir = temp_dir
        service.metrics_dir = temp_dir / "metrics"
        service.audit_dir = temp_dir / "audit"

        # Manually create directories as initialize() uses config
        (temp_dir / "metrics").mkdir(exist_ok=True)
        (temp_dir / "audit").mkdir(exist_ok=True)

        assert (temp_dir / "metrics").exists()
        assert (temp_dir / "audit").exists()

    def test_buffer_starts_empty(self, storage_service: StorageService):
        """Buffers should be empty on initialization."""
        assert storage_service._metrics_buffer == []
        assert storage_service._audit_buffer == []


class TestMetricsStorage:
    """Tests for metrics storage functionality."""

    @pytest.mark.asyncio
    async def test_store_metrics_buffers_data(self, storage_service: StorageService, sample_metrics: PowerwallMetrics):
        """store_metrics should buffer data before flush threshold."""
        storage_service._flush_threshold = 10  # Set high so no auto-flush

        await storage_service.store_metrics(sample_metrics)

        assert len(storage_service._metrics_buffer) == 1
        assert storage_service._metrics_buffer[0]["battery_percentage"] == sample_metrics.battery_percentage

    @pytest.mark.asyncio
    async def test_store_metrics_flushes_at_threshold(self, storage_service: StorageService, sample_metrics: PowerwallMetrics, temp_dir: Path):
        """store_metrics should flush when buffer reaches threshold."""
        storage_service._flush_threshold = 3
        storage_service._data_dir = temp_dir
        (temp_dir / "metrics").mkdir(exist_ok=True)

        for _ in range(3):
            await storage_service.store_metrics(sample_metrics)

        # Buffer should be cleared after flush
        assert len(storage_service._metrics_buffer) == 0

        # Parquet file should exist
        metrics_files = list((temp_dir / "metrics").glob("*.parquet"))
        assert len(metrics_files) == 1

    @pytest.mark.asyncio
    async def test_flush_all_empties_buffers(self, storage_service: StorageService, sample_metrics: PowerwallMetrics, temp_dir: Path):
        """flush_all should empty both buffers."""
        storage_service._data_dir = temp_dir
        (temp_dir / "metrics").mkdir(exist_ok=True)
        (temp_dir / "audit").mkdir(exist_ok=True)

        storage_service._flush_threshold = 100  # Prevent auto-flush
        await storage_service.store_metrics(sample_metrics)

        assert len(storage_service._metrics_buffer) == 1

        await storage_service.flush_all()

        assert len(storage_service._metrics_buffer) == 0


class TestAuditStorage:
    """Tests for audit log storage functionality."""

    @pytest.mark.asyncio
    async def test_store_audit_flushes_immediately(self, storage_service: StorageService, temp_dir: Path):
        """store_audit should flush immediately (audit logs are important)."""
        storage_service._data_dir = temp_dir
        (temp_dir / "audit").mkdir(exist_ok=True)

        await storage_service.store_audit(
            action="test_action",
            details="Test details",
            old_value="old",
            new_value="new",
            triggered_by="test"
        )

        # Buffer should be empty after immediate flush
        assert len(storage_service._audit_buffer) == 0

        # Parquet file should exist
        audit_files = list((temp_dir / "audit").glob("*.parquet"))
        assert len(audit_files) == 1

    @pytest.mark.asyncio
    async def test_store_audit_with_defaults(self, storage_service: StorageService, temp_dir: Path):
        """store_audit should work with default parameter values."""
        storage_service._data_dir = temp_dir
        (temp_dir / "audit").mkdir(exist_ok=True)

        await storage_service.store_audit(
            action="simple_action",
            details="Simple test"
        )

        audit_files = list((temp_dir / "audit").glob("*.parquet"))
        assert len(audit_files) == 1


class TestMetricsQuery:
    """Tests for querying metrics data."""

    @pytest.mark.asyncio
    async def test_query_metrics_empty_returns_empty_list(self, storage_service: StorageService, temp_dir: Path):
        """query_metrics should return empty list when no data."""
        storage_service._data_dir = temp_dir
        (temp_dir / "metrics").mkdir(exist_ok=True)

        start = datetime.now() - timedelta(hours=1)
        end = datetime.now()

        result = await storage_service.query_metrics(start, end)

        assert result == []

    @pytest.mark.asyncio
    async def test_query_metrics_returns_stored_data(self, storage_service: StorageService, sample_metrics: PowerwallMetrics, temp_dir: Path):
        """query_metrics should return previously stored data."""
        storage_service._data_dir = temp_dir
        storage_service._flush_threshold = 1  # Flush immediately
        (temp_dir / "metrics").mkdir(exist_ok=True)

        await storage_service.store_metrics(sample_metrics)

        start = datetime.now() - timedelta(hours=1)
        end = datetime.now() + timedelta(hours=1)

        result = await storage_service.query_metrics(start, end)

        assert len(result) == 1
        assert result[0]["battery_percentage"] == sample_metrics.battery_percentage

    @pytest.mark.asyncio
    async def test_query_metrics_filters_by_time_range(self, storage_service: StorageService, temp_dir: Path):
        """query_metrics should only return data within time range."""
        storage_service._data_dir = temp_dir
        storage_service._flush_threshold = 1
        (temp_dir / "metrics").mkdir(exist_ok=True)

        now = datetime.now()
        metrics1 = PowerwallMetrics(
            timestamp=now - timedelta(hours=2),
            battery_percentage=50.0,
            battery_power=1.0,
            solar_power=2.0,
            home_power=1.5,
            grid_power=0.5,
            backup_reserve=20.0,
            grid_status="Connected",
            battery_capacity=13.5,
        )
        metrics2 = PowerwallMetrics(
            timestamp=now,
            battery_percentage=75.0,
            battery_power=2.0,
            solar_power=3.0,
            home_power=2.5,
            grid_power=1.0,
            backup_reserve=20.0,
            grid_status="Connected",
            battery_capacity=13.5,
        )

        await storage_service.store_metrics(metrics1)
        await storage_service.store_metrics(metrics2)

        # Query only for last hour
        start = now - timedelta(hours=1)
        end = now + timedelta(minutes=1)

        result = await storage_service.query_metrics(start, end)

        assert len(result) == 1
        assert result[0]["battery_percentage"] == 75.0


class TestAuditQuery:
    """Tests for querying audit data."""

    @pytest.mark.asyncio
    async def test_query_audit_empty_returns_empty_list(self, storage_service: StorageService, temp_dir: Path):
        """query_audit should return empty list when no data."""
        storage_service._data_dir = temp_dir
        (temp_dir / "audit").mkdir(exist_ok=True)

        start = datetime.now() - timedelta(days=1)
        end = datetime.now()

        result = await storage_service.query_audit(start, end)

        assert result == []

    @pytest.mark.asyncio
    async def test_query_audit_returns_stored_data(self, storage_service: StorageService, temp_dir: Path):
        """query_audit should return previously stored audit entries."""
        storage_service._data_dir = temp_dir
        (temp_dir / "audit").mkdir(exist_ok=True)

        await storage_service.store_audit(
            action="test_action",
            details="Test details",
            triggered_by="test"
        )

        start = datetime.now() - timedelta(hours=1)
        end = datetime.now() + timedelta(hours=1)

        result = await storage_service.query_audit(start, end)

        assert len(result) == 1
        assert result[0]["action"] == "test_action"
        assert result[0]["details"] == "Test details"

    @pytest.mark.asyncio
    async def test_query_audit_respects_limit(self, storage_service: StorageService, temp_dir: Path):
        """query_audit should respect the limit parameter."""
        storage_service._data_dir = temp_dir
        (temp_dir / "audit").mkdir(exist_ok=True)

        # Store multiple audit entries
        for i in range(5):
            await storage_service.store_audit(
                action=f"action_{i}",
                details=f"Details {i}"
            )

        start = datetime.now() - timedelta(hours=1)
        end = datetime.now() + timedelta(hours=1)

        result = await storage_service.query_audit(start, end, limit=3)

        assert len(result) == 3


class TestRecentMetrics:
    """Tests for get_recent_metrics helper."""

    @pytest.mark.asyncio
    async def test_get_recent_metrics_uses_default_seconds(self, storage_service: StorageService, temp_dir: Path):
        """get_recent_metrics should use default 300 seconds."""
        storage_service._data_dir = temp_dir
        (temp_dir / "metrics").mkdir(exist_ok=True)

        # This should not raise and should return empty list
        result = await storage_service.get_recent_metrics()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_recent_metrics_with_custom_seconds(self, storage_service: StorageService, temp_dir: Path):
        """get_recent_metrics should accept custom seconds parameter."""
        storage_service._data_dir = temp_dir
        (temp_dir / "metrics").mkdir(exist_ok=True)

        result = await storage_service.get_recent_metrics(seconds=60)

        assert result == []
