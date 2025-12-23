"""Tests for API endpoints."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.monitoring_service import PowerwallMetrics


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestStatusEndpoint:
    """Tests for /api/status endpoint."""

    def test_get_status(self, client):
        """GET /api/status should return system status."""
        with patch("app.api.powerwall_service") as mock_pw:
            mock_pw.is_connected = True

            with patch("app.api.monitoring_service") as mock_mon:
                mock_mon.is_running = True

                with patch("app.api.automation_service") as mock_auto:
                    mock_auto.is_running = False

                    with patch("app.api.config") as mock_config:
                        mock_config.is_configured.return_value = True

                        response = client.get("/api/status")

        assert response.status_code == 200
        data = response.json()
        assert data["powerwall_connected"] is True
        assert data["monitoring_running"] is True
        assert data["automation_running"] is False
        assert data["configured"] is True


class TestConfigEndpoints:
    """Tests for /api/config endpoints."""

    def test_get_config(self, client):
        """GET /api/config should return configuration."""
        with patch("app.api.config") as mock_config:
            mock_config.powerwall_mode = "cloud"
            mock_config.powerwall_host = ""
            mock_config.powerwall_email = "test@example.com"
            mock_config.powerwall_password = "secret"
            mock_config.powerwall_gw_password = ""
            mock_config.powerwall_timezone = "America/Los_Angeles"
            mock_config.server_port = 9090
            mock_config.monitoring_interval = 5
            mock_config.automation_cooldown = 30
            mock_config.automation_average_window = 20

            response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "cloud"
        assert data["email"] == "test@example.com"
        assert data["has_password"] is True
        assert data["has_gw_password"] is False
        assert data["port"] == 9090

    def test_post_config(self, client):
        """POST /api/config should update configuration."""
        with patch("app.api.config") as mock_config:
            mock_config.save = MagicMock()

            with patch("app.api.storage_service") as mock_storage:
                mock_storage.store_audit = AsyncMock()

                response = client.post("/api/config", json={
                    "mode": "local",
                    "host": "192.168.1.100",
                    "email": "test@example.com",
                    "password": "newpassword",
                })

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_config.save.assert_called_once()


class TestConnectionEndpoints:
    """Tests for /api/connection endpoints."""

    def test_test_connection(self, client):
        """POST /api/connection/test should test powerwall connection."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.steps = [
            ("Check Config", True, "Configuration valid"),
            ("Connect", True, "Connected successfully"),
        ]
        mock_result.error = None

        with patch("app.api.powerwall_service") as mock_pw:
            mock_pw.test_connection = AsyncMock(return_value=mock_result)

            with patch("app.api.storage_service") as mock_storage:
                mock_storage.initialize = MagicMock()

                response = client.post("/api/connection/test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["steps"]) == 2

    def test_connect(self, client):
        """POST /api/connection/connect should connect to powerwall."""
        with patch("app.api.powerwall_service") as mock_pw:
            mock_pw.connect = AsyncMock()

            with patch("app.api.storage_service") as mock_storage:
                mock_storage.store_audit = AsyncMock()

                with patch("app.api.config") as mock_config:
                    mock_config.powerwall_host = "192.168.1.100"

                    response = client.post("/api/connection/connect")

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_connect_failure(self, client):
        """POST /api/connection/connect should return error on failure."""
        with patch("app.api.powerwall_service") as mock_pw:
            mock_pw.connect = AsyncMock(side_effect=Exception("Connection failed"))

            response = client.post("/api/connection/connect")

        assert response.status_code == 400
        assert "Connection failed" in response.json()["detail"]

    def test_disconnect(self, client):
        """POST /api/connection/disconnect should disconnect."""
        with patch("app.api.powerwall_service") as mock_pw:
            mock_pw.disconnect = AsyncMock()

            response = client.post("/api/connection/disconnect")

        assert response.status_code == 200
        assert response.json()["success"] is True


class TestMonitoringEndpoints:
    """Tests for /api/monitoring endpoints."""

    def test_get_monitoring_status(self, client):
        """GET /api/monitoring/status should return status."""
        with patch("app.api.monitoring_service") as mock_mon:
            mock_mon.is_running = True
            mock_mon.last_metrics = None

            response = client.get("/api/monitoring/status")

        assert response.status_code == 200
        data = response.json()
        assert data["running"] is True
        assert data["last_metrics"] is None

    def test_start_monitoring(self, client):
        """POST /api/monitoring/start should start monitoring."""
        with patch("app.api.monitoring_service") as mock_mon:
            mock_mon.start = AsyncMock()

            response = client.post("/api/monitoring/start")

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_start_monitoring_failure(self, client):
        """POST /api/monitoring/start should return error on failure."""
        with patch("app.api.monitoring_service") as mock_mon:
            mock_mon.start = AsyncMock(side_effect=Exception("Not configured"))

            response = client.post("/api/monitoring/start")

        assert response.status_code == 400
        assert "Not configured" in response.json()["detail"]

    def test_stop_monitoring(self, client):
        """POST /api/monitoring/stop should stop monitoring."""
        with patch("app.api.monitoring_service") as mock_mon:
            mock_mon.stop = AsyncMock()

            with patch("app.api.automation_service") as mock_auto:
                mock_auto.is_running = False

                response = client.post("/api/monitoring/stop")

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_get_current_metrics(self, client):
        """GET /api/monitoring/current should return current metrics."""
        metrics = PowerwallMetrics(
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

        with patch("app.api.monitoring_service") as mock_mon:
            mock_mon.is_running = True
            mock_mon.last_metrics = metrics

            response = client.get("/api/monitoring/current")

        assert response.status_code == 200
        data = response.json()
        assert data["battery_percentage"] == 75.5
        assert data["solar_power"] == 5.0

    def test_get_current_metrics_not_running(self, client):
        """GET /api/monitoring/current should return error if not running."""
        with patch("app.api.monitoring_service") as mock_mon:
            mock_mon.is_running = False

            response = client.get("/api/monitoring/current")

        assert response.status_code == 400
        assert "not running" in response.json()["detail"]


class TestAutomationEndpoints:
    """Tests for /api/automation endpoints."""

    def test_get_automation_status(self, client):
        """GET /api/automation/status should return status."""
        with patch("app.api.automation_service") as mock_auto:
            mock_auto.is_running = False
            mock_auto.rules = []

            response = client.get("/api/automation/status")

        assert response.status_code == 200
        data = response.json()
        assert data["running"] is False
        assert data["rules_count"] == 0

    def test_get_rules(self, client):
        """GET /api/automation/rules should return rules list."""
        mock_rule = MagicMock()
        mock_rule.to_dict.return_value = {
            "id": "1",
            "name": "Test Rule",
            "operator": ">",
            "threshold": 5.0,
            "target_reserve": 80.0,
            "enabled": True,
            "order": 0,
        }

        with patch("app.api.automation_service") as mock_auto:
            mock_auto.rules = [mock_rule]

            response = client.get("/api/automation/rules")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Rule"

    def test_create_rule(self, client):
        """POST /api/automation/rules should create a new rule."""
        with patch("app.api.automation_service") as mock_auto:
            mock_auto.add_rule = MagicMock()

            with patch("app.api.storage_service") as mock_storage:
                mock_storage.store_audit = AsyncMock()

                response = client.post("/api/automation/rules", json={
                    "name": "New Rule",
                    "operator": ">",
                    "threshold": 5.0,
                    "target_reserve": 80.0,
                    "enabled": True,
                })

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Rule"
        mock_auto.add_rule.assert_called_once()

    def test_update_rule(self, client):
        """PUT /api/automation/rules/{id} should update a rule."""
        mock_rule = MagicMock()
        mock_rule.to_dict.return_value = {
            "id": "1",
            "name": "Updated Rule",
            "operator": ">",
            "threshold": 10.0,
            "target_reserve": 80.0,
            "enabled": True,
            "order": 0,
        }

        with patch("app.api.automation_service") as mock_auto:
            mock_auto.update_rule = MagicMock(return_value=mock_rule)

            with patch("app.api.storage_service") as mock_storage:
                mock_storage.store_audit = AsyncMock()

                response = client.put("/api/automation/rules/1", json={
                    "name": "Updated Rule",
                    "threshold": 10.0,
                })

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Rule"

    def test_update_rule_not_found(self, client):
        """PUT /api/automation/rules/{id} should return 404 if not found."""
        with patch("app.api.automation_service") as mock_auto:
            mock_auto.update_rule = MagicMock(return_value=None)

            response = client.put("/api/automation/rules/nonexistent", json={
                "name": "Updated",
            })

        assert response.status_code == 404

    def test_delete_rule(self, client):
        """DELETE /api/automation/rules/{id} should delete a rule."""
        mock_rule = MagicMock()
        mock_rule.id = "1"
        mock_rule.name = "Test Rule"

        with patch("app.api.automation_service") as mock_auto:
            mock_auto.rules = [mock_rule]
            mock_auto.delete_rule = MagicMock(return_value=True)

            with patch("app.api.storage_service") as mock_storage:
                mock_storage.store_audit = AsyncMock()

                response = client.delete("/api/automation/rules/1")

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_delete_rule_not_found(self, client):
        """DELETE /api/automation/rules/{id} should return 404 if not found."""
        with patch("app.api.automation_service") as mock_auto:
            mock_auto.rules = []
            mock_auto.delete_rule = MagicMock(return_value=False)

            response = client.delete("/api/automation/rules/nonexistent")

        assert response.status_code == 404


class TestBackupReserveEndpoint:
    """Tests for /api/powerwall/backup-reserve endpoint."""

    def test_set_backup_reserve(self, client):
        """POST /api/powerwall/backup-reserve should set reserve."""
        with patch("app.api.powerwall_service") as mock_pw:
            mock_pw.is_connected = True
            mock_pw.get_backup_reserve = AsyncMock(return_value=20.0)
            mock_pw.set_backup_reserve = AsyncMock()

            with patch("app.api.storage_service") as mock_storage:
                mock_storage.store_audit = AsyncMock()

                response = client.post("/api/powerwall/backup-reserve", json={
                    "percentage": 50.0,
                })

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_pw.set_backup_reserve.assert_called_once_with(50.0)
        mock_storage.store_audit.assert_called_once()

    def test_set_backup_reserve_no_change_when_already_at_target(self, client):
        """POST /api/powerwall/backup-reserve should skip if already at target."""
        with patch("app.api.powerwall_service") as mock_pw:
            mock_pw.is_connected = True
            mock_pw.get_backup_reserve = AsyncMock(return_value=50.0)
            mock_pw.set_backup_reserve = AsyncMock()

            with patch("app.api.storage_service") as mock_storage:
                mock_storage.store_audit = AsyncMock()

                response = client.post("/api/powerwall/backup-reserve", json={
                    "percentage": 50.0,
                })

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert "Already at target" in response.json().get("message", "")
        mock_pw.set_backup_reserve.assert_not_called()
        mock_storage.store_audit.assert_not_called()

    def test_set_backup_reserve_not_connected(self, client):
        """POST /api/powerwall/backup-reserve should fail if not connected."""
        with patch("app.api.powerwall_service") as mock_pw:
            mock_pw.is_connected = False

            response = client.post("/api/powerwall/backup-reserve", json={
                "percentage": 50.0,
            })

        assert response.status_code == 400
        assert "Not connected" in response.json()["detail"]


class TestHistoryEndpoints:
    """Tests for /api/history endpoints."""

    def test_get_history_metrics(self, client):
        """GET /api/history/metrics should return historical metrics."""
        with patch("app.api.storage_service") as mock_storage:
            mock_storage.query_metrics = AsyncMock(return_value=[
                {
                    "timestamp": datetime.now(),
                    "battery_percentage": 75.0,
                    "battery_power": 2.0,
                    "solar_power": 5.0,
                    "home_power": 3.0,
                    "grid_power": -1.0,
                    "backup_reserve": 20.0,
                    "grid_status": "Connected",
                    "battery_capacity": 13.5,
                }
            ])

            response = client.get("/api/history/metrics?hours=1")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["battery_percentage"] == 75.0

    def test_get_history_metrics_with_float_hours(self, client):
        """GET /api/history/metrics should accept float hours."""
        with patch("app.api.storage_service") as mock_storage:
            mock_storage.query_metrics = AsyncMock(return_value=[])

            response = client.get("/api/history/metrics?hours=0.0833")

        assert response.status_code == 200

    def test_get_history_events(self, client):
        """GET /api/history/events should return events."""
        with patch("app.api.storage_service") as mock_storage:
            mock_storage.get_events_for_period = AsyncMock(return_value=[
                {
                    "timestamp": datetime.now(),
                    "action": "backup_reserve_changed",
                    "details": "Test event",
                    "old_value": "20%",
                    "new_value": "80%",
                    "triggered_by": "automation",
                }
            ])

            response = client.get("/api/history/events?hours=24")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["action"] == "backup_reserve_changed"


class TestAuditEndpoint:
    """Tests for /api/audit endpoint."""

    def test_get_audit_log(self, client):
        """GET /api/audit should return audit log."""
        with patch("app.api.storage_service") as mock_storage:
            mock_storage.query_audit = AsyncMock(return_value=[
                {
                    "timestamp": datetime.now(),
                    "action": "config_updated",
                    "details": "Configuration changed",
                    "old_value": "",
                    "new_value": "",
                    "triggered_by": "user",
                }
            ])

            response = client.get("/api/audit?days=7")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["action"] == "config_updated"
