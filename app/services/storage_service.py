"""Data storage service using Parquet files and DuckDB for queries."""

import asyncio
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional
import pyarrow as pa
import pyarrow.parquet as pq
import duckdb

from app.config import config
from app.services.powerwall_service import PowerwallMetrics


# Schema for metrics data
METRICS_SCHEMA = pa.schema([
    ("timestamp", pa.timestamp("us")),
    ("battery_percentage", pa.float64()),
    ("battery_power", pa.float64()),
    ("solar_power", pa.float64()),
    ("home_power", pa.float64()),
    ("grid_power", pa.float64()),
    ("backup_reserve", pa.float64()),
    ("grid_status", pa.string()),
    ("battery_capacity", pa.float64()),
])

# Schema for audit log
AUDIT_SCHEMA = pa.schema([
    ("timestamp", pa.timestamp("us")),
    ("action", pa.string()),
    ("details", pa.string()),
    ("old_value", pa.string()),
    ("new_value", pa.string()),
    ("triggered_by", pa.string()),
])


class StorageService:
    """Service for storing and querying Powerwall data."""

    def __init__(self):
        self._data_dir: Optional[Path] = None
        self._metrics_buffer: list = []
        self._audit_buffer: list = []
        self._buffer_lock = asyncio.Lock()
        self._flush_threshold = 12  # Flush every ~60 seconds at 5s intervals

    def initialize(self) -> None:
        """Initialize the storage directory."""
        self._data_dir = config.data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        (self._data_dir / "metrics").mkdir(exist_ok=True)
        (self._data_dir / "audit").mkdir(exist_ok=True)

    def _get_metrics_file(self, dt: date) -> Path:
        """Get the parquet file path for a given date."""
        return self._data_dir / "metrics" / f"metrics_{dt.isoformat()}.parquet"

    def _get_audit_file(self, dt: date) -> Path:
        """Get the audit log file path for a given date."""
        return self._data_dir / "audit" / f"audit_{dt.isoformat()}.parquet"

    async def store_metrics(self, metrics: PowerwallMetrics) -> None:
        """Store metrics data, buffering for efficiency."""
        async with self._buffer_lock:
            self._metrics_buffer.append({
                "timestamp": metrics.timestamp,
                "battery_percentage": metrics.battery_percentage,
                "battery_power": metrics.battery_power,
                "solar_power": metrics.solar_power,
                "home_power": metrics.home_power,
                "grid_power": metrics.grid_power,
                "backup_reserve": metrics.backup_reserve,
                "grid_status": metrics.grid_status,
                "battery_capacity": metrics.battery_capacity,
            })

            if len(self._metrics_buffer) >= self._flush_threshold:
                await self._flush_metrics()

    async def _flush_metrics(self) -> None:
        """Flush buffered metrics to parquet files."""
        if not self._metrics_buffer:
            return

        # Group by date
        by_date = {}
        for record in self._metrics_buffer:
            dt = record["timestamp"].date()
            if dt not in by_date:
                by_date[dt] = []
            by_date[dt].append(record)

        self._metrics_buffer = []

        # Write to files
        for dt, records in by_date.items():
            await asyncio.to_thread(self._append_to_parquet, self._get_metrics_file(dt), records, METRICS_SCHEMA)

    def _append_to_parquet(self, file_path: Path, records: list, schema: pa.Schema) -> None:
        """Append records to a parquet file."""
        table = pa.Table.from_pylist(records, schema=schema)

        if file_path.exists():
            existing = pq.read_table(file_path)
            table = pa.concat_tables([existing, table])

        pq.write_table(table, file_path)

    async def store_audit(self, action: str, details: str, old_value: str = "",
                          new_value: str = "", triggered_by: str = "user") -> None:
        """Store an audit log entry."""
        async with self._buffer_lock:
            self._audit_buffer.append({
                "timestamp": datetime.now(),
                "action": action,
                "details": details,
                "old_value": old_value,
                "new_value": new_value,
                "triggered_by": triggered_by,
            })
            # Audit logs are important, flush immediately
            await self._flush_audit()

    async def _flush_audit(self) -> None:
        """Flush buffered audit logs to parquet files."""
        if not self._audit_buffer:
            return

        by_date = {}
        for record in self._audit_buffer:
            dt = record["timestamp"].date()
            if dt not in by_date:
                by_date[dt] = []
            by_date[dt].append(record)

        self._audit_buffer = []

        for dt, records in by_date.items():
            await asyncio.to_thread(self._append_to_parquet, self._get_audit_file(dt), records, AUDIT_SCHEMA)

    async def flush_all(self) -> None:
        """Flush all buffered data."""
        async with self._buffer_lock:
            await self._flush_metrics()
            await self._flush_audit()

    async def query_metrics(self, start: datetime, end: datetime) -> list:
        """Query metrics for a time range."""
        return await asyncio.to_thread(self._query_metrics_sync, start, end)

    def _query_metrics_sync(self, start: datetime, end: datetime) -> list:
        """Synchronous query for metrics."""
        metrics_dir = self._data_dir / "metrics"
        if not metrics_dir.exists():
            return []

        files = list(metrics_dir.glob("metrics_*.parquet"))
        if not files:
            return []

        # Filter files by date range
        start_date = start.date()
        end_date = end.date()

        relevant_files = []
        for f in files:
            try:
                file_date = date.fromisoformat(f.stem.replace("metrics_", ""))
                if start_date <= file_date <= end_date:
                    relevant_files.append(str(f))
            except ValueError:
                continue

        if not relevant_files:
            return []

        # Query using DuckDB
        conn = duckdb.connect(":memory:")
        files_str = "', '".join(relevant_files)
        query = f"""
            SELECT * FROM read_parquet(['{files_str}'])
            WHERE timestamp >= '{start.isoformat()}'
            AND timestamp <= '{end.isoformat()}'
            ORDER BY timestamp
        """
        result = conn.execute(query).fetchall()
        columns = ["timestamp", "battery_percentage", "battery_power", "solar_power",
                   "home_power", "grid_power", "backup_reserve", "grid_status", "battery_capacity"]

        return [dict(zip(columns, row)) for row in result]

    async def query_audit(self, start: datetime, end: datetime, limit: int = 1000) -> list:
        """Query audit logs for a time range."""
        return await asyncio.to_thread(self._query_audit_sync, start, end, limit)

    def _query_audit_sync(self, start: datetime, end: datetime, limit: int) -> list:
        """Synchronous query for audit logs."""
        audit_dir = self._data_dir / "audit"
        if not audit_dir.exists():
            return []

        files = list(audit_dir.glob("audit_*.parquet"))
        if not files:
            return []

        start_date = start.date()
        end_date = end.date()

        relevant_files = []
        for f in files:
            try:
                file_date = date.fromisoformat(f.stem.replace("audit_", ""))
                if start_date <= file_date <= end_date:
                    relevant_files.append(str(f))
            except ValueError:
                continue

        if not relevant_files:
            return []

        conn = duckdb.connect(":memory:")
        files_str = "', '".join(relevant_files)
        query = f"""
            SELECT * FROM read_parquet(['{files_str}'])
            WHERE timestamp >= '{start.isoformat()}'
            AND timestamp <= '{end.isoformat()}'
            ORDER BY timestamp DESC
            LIMIT {limit}
        """
        result = conn.execute(query).fetchall()
        columns = ["timestamp", "action", "details", "old_value", "new_value", "triggered_by"]

        return [dict(zip(columns, row)) for row in result]

    async def get_recent_metrics(self, seconds: int = 300) -> list:
        """Get metrics from the last N seconds."""
        end = datetime.now()
        start = end - timedelta(seconds=seconds)
        return await self.query_metrics(start, end)

    async def get_events_for_period(self, start: datetime, end: datetime) -> list:
        """Get automation events for overlaying on graphs."""
        return await self.query_audit(start, end)


# Global service instance
storage_service = StorageService()
