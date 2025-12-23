"""Monitoring service for sampling Powerwall data at regular intervals."""

import asyncio
from collections import deque
from datetime import datetime
from typing import Callable, Optional

from app.config import config
from app.services.powerwall_service import powerwall_service, PowerwallMetrics
from app.services.storage_service import storage_service


class MonitoringService:
    """Service for continuous monitoring of Powerwall metrics."""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._recent_metrics: deque = deque(maxlen=60)  # Keep last 5 minutes at 5s interval
        self._callbacks: list[Callable[[PowerwallMetrics], None]] = []
        self._last_metrics: Optional[PowerwallMetrics] = None
        self._error_count = 0
        self._max_errors = 5

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_metrics(self) -> Optional[PowerwallMetrics]:
        return self._last_metrics

    @property
    def recent_metrics(self) -> list[PowerwallMetrics]:
        return list(self._recent_metrics)

    def add_callback(self, callback: Callable[[PowerwallMetrics], None]) -> None:
        """Add a callback to be called when new metrics are collected."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[PowerwallMetrics], None]) -> None:
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def start(self) -> bool:
        """Start the monitoring loop."""
        if self._running:
            return True

        # Ensure we're connected to the Powerwall
        if not powerwall_service.is_connected:
            try:
                await powerwall_service.connect()
            except Exception as e:
                raise RuntimeError(f"Cannot start monitoring: {str(e)}")

        # Initialize storage
        storage_service.initialize()

        self._running = True
        self._error_count = 0
        self._task = asyncio.create_task(self._monitoring_loop())

        await storage_service.store_audit(
            action="monitoring_started",
            details="Monitoring service started",
            triggered_by="user"
        )

        return True

    async def stop(self) -> None:
        """Stop the monitoring loop."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # Flush any remaining data
        await storage_service.flush_all()

        await storage_service.store_audit(
            action="monitoring_stopped",
            details="Monitoring service stopped",
            triggered_by="user"
        )

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        interval = config.monitoring_interval

        while self._running:
            try:
                start_time = datetime.now()

                # Collect metrics
                metrics = await powerwall_service.get_metrics()
                self._last_metrics = metrics
                self._recent_metrics.append(metrics)
                self._error_count = 0

                # Store metrics
                await storage_service.store_metrics(metrics)

                # Notify callbacks
                for callback in self._callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(metrics)
                        else:
                            callback(metrics)
                    except Exception:
                        pass  # Don't let callback errors stop monitoring

                # Calculate sleep time to maintain interval
                elapsed = (datetime.now() - start_time).total_seconds()
                sleep_time = max(0, interval - elapsed)
                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._error_count += 1
                if self._error_count >= self._max_errors:
                    await storage_service.store_audit(
                        action="monitoring_error",
                        details=f"Monitoring stopped due to repeated errors: {str(e)}",
                        triggered_by="system"
                    )
                    self._running = False
                    break
                await asyncio.sleep(interval)

    def get_average_home_power(self, seconds: int = 20) -> Optional[float]:
        """Get average home power consumption over the last N seconds."""
        if not self._recent_metrics:
            return None

        # Calculate how many samples we need based on interval
        interval = config.monitoring_interval
        samples_needed = max(1, seconds // interval)

        recent = list(self._recent_metrics)[-samples_needed:]
        if not recent:
            return None

        return sum(m.home_power for m in recent) / len(recent)


# Global service instance
monitoring_service = MonitoringService()
