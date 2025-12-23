"""Tests for the automation service."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.automation_service import (
    AutomationRule,
    AutomationService,
    RuleOperator,
)
from app.services.monitoring_service import PowerwallMetrics


class TestRuleOperator:
    """Tests for RuleOperator enum."""

    def test_operator_values(self):
        """RuleOperator should have correct string values."""
        assert RuleOperator.GREATER_THAN.value == ">"
        assert RuleOperator.LESS_THAN.value == "<"
        assert RuleOperator.GREATER_EQUAL.value == ">="
        assert RuleOperator.LESS_EQUAL.value == "<="

    def test_operator_from_string(self):
        """RuleOperator should be creatable from string values."""
        assert RuleOperator(">") == RuleOperator.GREATER_THAN
        assert RuleOperator("<") == RuleOperator.LESS_THAN
        assert RuleOperator(">=") == RuleOperator.GREATER_EQUAL
        assert RuleOperator("<=") == RuleOperator.LESS_EQUAL


class TestAutomationRule:
    """Tests for AutomationRule dataclass."""

    def test_evaluate_greater_than(self):
        """Rule with > operator should evaluate correctly."""
        rule = AutomationRule(
            id="1",
            name="Test",
            operator=RuleOperator.GREATER_THAN,
            threshold=5.0,
            target_reserve=80.0,
        )

        assert rule.evaluate(6.0) is True
        assert rule.evaluate(5.0) is False
        assert rule.evaluate(4.0) is False

    def test_evaluate_less_than(self):
        """Rule with < operator should evaluate correctly."""
        rule = AutomationRule(
            id="1",
            name="Test",
            operator=RuleOperator.LESS_THAN,
            threshold=5.0,
            target_reserve=20.0,
        )

        assert rule.evaluate(4.0) is True
        assert rule.evaluate(5.0) is False
        assert rule.evaluate(6.0) is False

    def test_evaluate_greater_equal(self):
        """Rule with >= operator should evaluate correctly."""
        rule = AutomationRule(
            id="1",
            name="Test",
            operator=RuleOperator.GREATER_EQUAL,
            threshold=5.0,
            target_reserve=80.0,
        )

        assert rule.evaluate(6.0) is True
        assert rule.evaluate(5.0) is True
        assert rule.evaluate(4.0) is False

    def test_evaluate_less_equal(self):
        """Rule with <= operator should evaluate correctly."""
        rule = AutomationRule(
            id="1",
            name="Test",
            operator=RuleOperator.LESS_EQUAL,
            threshold=5.0,
            target_reserve=20.0,
        )

        assert rule.evaluate(4.0) is True
        assert rule.evaluate(5.0) is True
        assert rule.evaluate(6.0) is False

    def test_to_dict(self):
        """to_dict should return correct dictionary representation."""
        rule = AutomationRule(
            id="test-id",
            name="Test Rule",
            operator=RuleOperator.GREATER_THAN,
            threshold=5.0,
            target_reserve=80.0,
            enabled=True,
            order=1,
        )

        result = rule.to_dict()

        assert result["id"] == "test-id"
        assert result["name"] == "Test Rule"
        assert result["operator"] == ">"
        assert result["threshold"] == 5.0
        assert result["target_reserve"] == 80.0
        assert result["enabled"] is True
        assert result["order"] == 1

    def test_from_dict(self):
        """from_dict should create rule from dictionary."""
        data = {
            "id": "test-id",
            "name": "Test Rule",
            "operator": ">",
            "threshold": 5.0,
            "target_reserve": 80.0,
            "enabled": False,
            "order": 2,
        }

        rule = AutomationRule.from_dict(data)

        assert rule.id == "test-id"
        assert rule.name == "Test Rule"
        assert rule.operator == RuleOperator.GREATER_THAN
        assert rule.threshold == 5.0
        assert rule.target_reserve == 80.0
        assert rule.enabled is False
        assert rule.order == 2

    def test_from_dict_generates_id_if_missing(self):
        """from_dict should generate UUID if id is missing."""
        data = {
            "name": "Test Rule",
            "operator": ">",
            "threshold": 5.0,
            "target_reserve": 80.0,
        }

        rule = AutomationRule.from_dict(data)

        assert rule.id is not None
        assert len(rule.id) > 0

    def test_from_dict_uses_defaults(self):
        """from_dict should use defaults for optional fields."""
        data = {
            "name": "Test Rule",
            "operator": "<",
            "threshold": 3.0,
            "target_reserve": 20.0,
        }

        rule = AutomationRule.from_dict(data)

        assert rule.enabled is True
        assert rule.order == 0


class TestAutomationService:
    """Tests for AutomationService."""

    def test_initial_state(self):
        """Service should start in stopped state with no rules."""
        service = AutomationService()

        assert service.is_running is False
        assert service.rules == []

    def test_add_rule_assigns_id_if_empty(self):
        """add_rule should assign UUID if rule has empty id."""
        service = AutomationService()
        rule = AutomationRule(
            id="",
            name="Test",
            operator=RuleOperator.GREATER_THAN,
            threshold=5.0,
            target_reserve=80.0,
        )

        with patch.object(service, "save_rules"):
            service.add_rule(rule)

        assert rule.id != ""
        assert len(rule.id) == 36  # UUID length

    def test_add_rule_sets_order(self):
        """add_rule should set order based on existing rules count."""
        service = AutomationService()

        with patch.object(service, "save_rules"):
            rule1 = AutomationRule(
                id="1", name="Rule 1", operator=RuleOperator.GREATER_THAN,
                threshold=5.0, target_reserve=80.0
            )
            service.add_rule(rule1)

            rule2 = AutomationRule(
                id="2", name="Rule 2", operator=RuleOperator.LESS_THAN,
                threshold=3.0, target_reserve=20.0
            )
            service.add_rule(rule2)

        assert rule1.order == 0
        assert rule2.order == 1

    def test_rules_returns_sorted_by_order(self):
        """rules property should return rules sorted by order."""
        service = AutomationService()

        rule1 = AutomationRule(
            id="1", name="Rule 1", operator=RuleOperator.GREATER_THAN,
            threshold=5.0, target_reserve=80.0, order=2
        )
        rule2 = AutomationRule(
            id="2", name="Rule 2", operator=RuleOperator.LESS_THAN,
            threshold=3.0, target_reserve=20.0, order=0
        )
        rule3 = AutomationRule(
            id="3", name="Rule 3", operator=RuleOperator.GREATER_EQUAL,
            threshold=4.0, target_reserve=50.0, order=1
        )

        service._rules = [rule1, rule2, rule3]

        sorted_rules = service.rules

        assert sorted_rules[0].id == "2"
        assert sorted_rules[1].id == "3"
        assert sorted_rules[2].id == "1"

    def test_update_rule_modifies_existing(self):
        """update_rule should modify an existing rule."""
        service = AutomationService()
        rule = AutomationRule(
            id="test-id", name="Original", operator=RuleOperator.GREATER_THAN,
            threshold=5.0, target_reserve=80.0
        )
        service._rules = [rule]

        with patch.object(service, "save_rules"):
            result = service.update_rule("test-id", {
                "name": "Updated",
                "threshold": 10.0,
                "enabled": False,
            })

        assert result is not None
        assert result.name == "Updated"
        assert result.threshold == 10.0
        assert result.enabled is False

    def test_update_rule_returns_none_for_missing(self):
        """update_rule should return None for non-existent rule."""
        service = AutomationService()

        with patch.object(service, "save_rules"):
            result = service.update_rule("nonexistent", {"name": "New"})

        assert result is None

    def test_delete_rule_removes_existing(self):
        """delete_rule should remove an existing rule."""
        service = AutomationService()
        rule = AutomationRule(
            id="test-id", name="Test", operator=RuleOperator.GREATER_THAN,
            threshold=5.0, target_reserve=80.0
        )
        service._rules = [rule]

        with patch.object(service, "save_rules"):
            result = service.delete_rule("test-id")

        assert result is True
        assert len(service._rules) == 0

    def test_delete_rule_returns_false_for_missing(self):
        """delete_rule should return False for non-existent rule."""
        service = AutomationService()

        with patch.object(service, "save_rules"):
            result = service.delete_rule("nonexistent")

        assert result is False

    def test_reorder_rules(self):
        """reorder_rules should update order based on ID list."""
        service = AutomationService()
        rule1 = AutomationRule(
            id="1", name="Rule 1", operator=RuleOperator.GREATER_THAN,
            threshold=5.0, target_reserve=80.0, order=0
        )
        rule2 = AutomationRule(
            id="2", name="Rule 2", operator=RuleOperator.LESS_THAN,
            threshold=3.0, target_reserve=20.0, order=1
        )
        rule3 = AutomationRule(
            id="3", name="Rule 3", operator=RuleOperator.GREATER_EQUAL,
            threshold=4.0, target_reserve=50.0, order=2
        )
        service._rules = [rule1, rule2, rule3]

        with patch.object(service, "save_rules"):
            service.reorder_rules(["3", "1", "2"])

        assert rule1.order == 1
        assert rule2.order == 2
        assert rule3.order == 0


class TestAutomationServiceStartStop:
    """Tests for starting and stopping automation service."""

    @pytest.mark.asyncio
    async def test_start_requires_monitoring(self):
        """start should raise error if monitoring is not running."""
        service = AutomationService()

        with patch("app.services.automation_service.monitoring_service") as mock_monitoring:
            mock_monitoring.is_running = False

            with pytest.raises(RuntimeError, match="Monitoring must be running"):
                await service.start()

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self):
        """start should set is_running to True."""
        service = AutomationService()

        with patch("app.services.automation_service.monitoring_service") as mock_monitoring:
            mock_monitoring.is_running = True
            mock_monitoring.add_callback = MagicMock()

            with patch("app.services.automation_service.storage_service") as mock_storage:
                mock_storage.store_audit = AsyncMock()

                with patch("app.services.automation_service.config") as mock_config:
                    mock_config.automation_rules = []

                    await service.start()

        assert service.is_running is True

    @pytest.mark.asyncio
    async def test_stop_clears_running_flag(self):
        """stop should set is_running to False."""
        service = AutomationService()
        service._running = True

        with patch("app.services.automation_service.monitoring_service") as mock_monitoring:
            mock_monitoring.remove_callback = MagicMock()

            with patch("app.services.automation_service.storage_service") as mock_storage:
                mock_storage.store_audit = AsyncMock()

                await service.stop()

        assert service.is_running is False


class TestAutomationServiceCooldown:
    """Tests for automation cooldown behavior."""

    @pytest.mark.asyncio
    async def test_cooldown_prevents_rapid_actions(self):
        """Cooldown should prevent rapid rule executions."""
        service = AutomationService()
        service._running = True
        service._last_action_time = datetime.now()  # Just executed

        rule = AutomationRule(
            id="1", name="Test", operator=RuleOperator.GREATER_THAN,
            threshold=5.0, target_reserve=80.0
        )
        service._rules = [rule]

        metrics = PowerwallMetrics(
            timestamp=datetime.now(),
            battery_percentage=75.0,
            battery_power=2.0,
            solar_power=5.0,
            home_power=10.0,  # Above threshold
            grid_power=0.0,
            backup_reserve=20.0,  # Different from target
            grid_status="Connected",
            battery_capacity=13.5,
        )

        with patch("app.services.automation_service.config") as mock_config:
            mock_config.automation_cooldown = 30  # 30 second cooldown

            with patch("app.services.automation_service.monitoring_service") as mock_monitoring:
                mock_monitoring.get_average_home_power.return_value = 10.0

                with patch("app.services.automation_service.powerwall_service") as mock_pw:
                    mock_pw.set_backup_reserve = AsyncMock()

                    await service._on_metrics(metrics)

                    # Should not have called set_backup_reserve due to cooldown
                    mock_pw.set_backup_reserve.assert_not_called()

    @pytest.mark.asyncio
    async def test_action_after_cooldown_expires(self):
        """Action should be allowed after cooldown expires."""
        service = AutomationService()
        service._running = True
        service._last_action_time = datetime.now() - timedelta(seconds=60)  # Expired

        rule = AutomationRule(
            id="1", name="Test", operator=RuleOperator.GREATER_THAN,
            threshold=5.0, target_reserve=80.0
        )
        service._rules = [rule]

        metrics = PowerwallMetrics(
            timestamp=datetime.now(),
            battery_percentage=75.0,
            battery_power=2.0,
            solar_power=5.0,
            home_power=10.0,
            grid_power=0.0,
            backup_reserve=20.0,
            grid_status="Connected",
            battery_capacity=13.5,
        )

        with patch("app.services.automation_service.config") as mock_config:
            mock_config.automation_cooldown = 30
            mock_config.automation_average_window = 20

            with patch("app.services.automation_service.monitoring_service") as mock_monitoring:
                mock_monitoring.get_average_home_power.return_value = 10.0

                with patch("app.services.automation_service.powerwall_service") as mock_pw:
                    mock_pw.get_backup_reserve = AsyncMock(return_value=20.0)
                    mock_pw.set_backup_reserve = AsyncMock()

                    with patch("app.services.automation_service.storage_service") as mock_storage:
                        mock_storage.store_audit = AsyncMock()

                        await service._on_metrics(metrics)

                        mock_pw.set_backup_reserve.assert_called_once_with(80.0)


class TestAutomationServiceRuleEvaluation:
    """Tests for rule evaluation logic."""

    @pytest.mark.asyncio
    async def test_first_matching_rule_executes(self):
        """Only the first matching rule should execute."""
        service = AutomationService()
        service._running = True
        service._last_action_time = None

        rule1 = AutomationRule(
            id="1", name="Rule 1", operator=RuleOperator.GREATER_THAN,
            threshold=5.0, target_reserve=80.0, order=0
        )
        rule2 = AutomationRule(
            id="2", name="Rule 2", operator=RuleOperator.GREATER_THAN,
            threshold=3.0, target_reserve=90.0, order=1
        )
        service._rules = [rule1, rule2]

        metrics = PowerwallMetrics(
            timestamp=datetime.now(),
            battery_percentage=75.0,
            battery_power=2.0,
            solar_power=5.0,
            home_power=10.0,
            grid_power=0.0,
            backup_reserve=20.0,
            grid_status="Connected",
            battery_capacity=13.5,
        )

        with patch("app.services.automation_service.config") as mock_config:
            mock_config.automation_cooldown = 30
            mock_config.automation_average_window = 20

            with patch("app.services.automation_service.monitoring_service") as mock_monitoring:
                mock_monitoring.get_average_home_power.return_value = 10.0

                with patch("app.services.automation_service.powerwall_service") as mock_pw:
                    mock_pw.get_backup_reserve = AsyncMock(return_value=20.0)
                    mock_pw.set_backup_reserve = AsyncMock()

                    with patch("app.services.automation_service.storage_service") as mock_storage:
                        mock_storage.store_audit = AsyncMock()

                        await service._on_metrics(metrics)

                        # First rule should have executed (80%), not second (90%)
                        mock_pw.set_backup_reserve.assert_called_once_with(80.0)

    @pytest.mark.asyncio
    async def test_disabled_rules_are_skipped(self):
        """Disabled rules should not be evaluated."""
        service = AutomationService()
        service._running = True
        service._last_action_time = None

        rule1 = AutomationRule(
            id="1", name="Disabled Rule", operator=RuleOperator.GREATER_THAN,
            threshold=5.0, target_reserve=80.0, enabled=False, order=0
        )
        rule2 = AutomationRule(
            id="2", name="Enabled Rule", operator=RuleOperator.GREATER_THAN,
            threshold=3.0, target_reserve=90.0, enabled=True, order=1
        )
        service._rules = [rule1, rule2]

        metrics = PowerwallMetrics(
            timestamp=datetime.now(),
            battery_percentage=75.0,
            battery_power=2.0,
            solar_power=5.0,
            home_power=10.0,
            grid_power=0.0,
            backup_reserve=20.0,
            grid_status="Connected",
            battery_capacity=13.5,
        )

        with patch("app.services.automation_service.config") as mock_config:
            mock_config.automation_cooldown = 30
            mock_config.automation_average_window = 20

            with patch("app.services.automation_service.monitoring_service") as mock_monitoring:
                mock_monitoring.get_average_home_power.return_value = 10.0

                with patch("app.services.automation_service.powerwall_service") as mock_pw:
                    mock_pw.get_backup_reserve = AsyncMock(return_value=20.0)
                    mock_pw.set_backup_reserve = AsyncMock()

                    with patch("app.services.automation_service.storage_service") as mock_storage:
                        mock_storage.store_audit = AsyncMock()

                        await service._on_metrics(metrics)

                        # Second rule should execute (90%), first is disabled
                        mock_pw.set_backup_reserve.assert_called_once_with(90.0)

    @pytest.mark.asyncio
    async def test_no_action_when_already_at_target(self):
        """No action should be taken if already at target reserve."""
        service = AutomationService()
        service._running = True
        service._last_action_time = None

        rule = AutomationRule(
            id="1", name="Test", operator=RuleOperator.GREATER_THAN,
            threshold=5.0, target_reserve=80.0
        )
        service._rules = [rule]

        metrics = PowerwallMetrics(
            timestamp=datetime.now(),
            battery_percentage=75.0,
            battery_power=2.0,
            solar_power=5.0,
            home_power=10.0,
            grid_power=0.0,
            backup_reserve=80.0,  # Already at target
            grid_status="Connected",
            battery_capacity=13.5,
        )

        with patch("app.services.automation_service.config") as mock_config:
            mock_config.automation_cooldown = 30
            mock_config.automation_average_window = 20

            with patch("app.services.automation_service.monitoring_service") as mock_monitoring:
                mock_monitoring.get_average_home_power.return_value = 10.0

                with patch("app.services.automation_service.powerwall_service") as mock_pw:
                    mock_pw.set_backup_reserve = AsyncMock()

                    await service._on_metrics(metrics)

                    mock_pw.set_backup_reserve.assert_not_called()
