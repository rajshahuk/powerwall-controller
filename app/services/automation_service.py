"""Automation service for managing backup reserve rules."""

import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid

from app.config import config
from app.services.powerwall_service import powerwall_service, PowerwallMetrics
from app.services.storage_service import storage_service
from app.services.monitoring_service import monitoring_service


class RuleOperator(str, Enum):
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="


@dataclass
class AutomationRule:
    """A rule for automatically adjusting backup reserve."""
    id: str
    name: str
    operator: RuleOperator
    threshold: float  # kW
    target_reserve: float  # percentage
    enabled: bool = True
    order: int = 0

    def evaluate(self, power_kw: float) -> bool:
        """Check if the rule condition is met."""
        if self.operator == RuleOperator.GREATER_THAN:
            return power_kw > self.threshold
        elif self.operator == RuleOperator.LESS_THAN:
            return power_kw < self.threshold
        elif self.operator == RuleOperator.GREATER_EQUAL:
            return power_kw >= self.threshold
        elif self.operator == RuleOperator.LESS_EQUAL:
            return power_kw <= self.threshold
        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "operator": self.operator.value,
            "threshold": self.threshold,
            "target_reserve": self.target_reserve,
            "enabled": self.enabled,
            "order": self.order,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AutomationRule":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data["name"],
            operator=RuleOperator(data["operator"]),
            threshold=data["threshold"],
            target_reserve=data["target_reserve"],
            enabled=data.get("enabled", True),
            order=data.get("order", 0),
        )


class AutomationService:
    """Service for managing automation rules and executing them."""

    def __init__(self):
        self._running = False
        self._rules: list[AutomationRule] = []
        self._last_action_time: Optional[datetime] = None
        self._current_reserve: Optional[float] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def rules(self) -> list[AutomationRule]:
        return sorted(self._rules, key=lambda r: r.order)

    def load_rules(self) -> None:
        """Load rules from configuration."""
        self._rules = []
        for rule_data in config.automation_rules:
            try:
                self._rules.append(AutomationRule.from_dict(rule_data))
            except Exception:
                continue

    def save_rules(self) -> None:
        """Save rules to configuration."""
        config.automation_rules = [r.to_dict() for r in self._rules]
        config.save()

    def add_rule(self, rule: AutomationRule) -> None:
        """Add a new rule."""
        if not rule.id:
            rule.id = str(uuid.uuid4())
        rule.order = len(self._rules)
        self._rules.append(rule)
        self.save_rules()

    def update_rule(self, rule_id: str, updates: dict) -> Optional[AutomationRule]:
        """Update an existing rule."""
        for rule in self._rules:
            if rule.id == rule_id:
                if "name" in updates:
                    rule.name = updates["name"]
                if "operator" in updates:
                    rule.operator = RuleOperator(updates["operator"])
                if "threshold" in updates:
                    rule.threshold = updates["threshold"]
                if "target_reserve" in updates:
                    rule.target_reserve = updates["target_reserve"]
                if "enabled" in updates:
                    rule.enabled = updates["enabled"]
                if "order" in updates:
                    rule.order = updates["order"]
                self.save_rules()
                return rule
        return None

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule."""
        for i, rule in enumerate(self._rules):
            if rule.id == rule_id:
                self._rules.pop(i)
                self.save_rules()
                return True
        return False

    def reorder_rules(self, rule_ids: list[str]) -> None:
        """Reorder rules based on the provided ID list."""
        rule_map = {r.id: r for r in self._rules}
        for i, rule_id in enumerate(rule_ids):
            if rule_id in rule_map:
                rule_map[rule_id].order = i
        self.save_rules()

    async def start(self) -> bool:
        """Start the automation service."""
        if self._running:
            return True

        if not monitoring_service.is_running:
            raise RuntimeError("Monitoring must be running before starting automation")

        self.load_rules()
        self._running = True

        # Register callback with monitoring service
        monitoring_service.add_callback(self._on_metrics)

        await storage_service.store_audit(
            action="automation_started",
            details="Automation service started",
            triggered_by="user"
        )

        return True

    async def stop(self) -> None:
        """Stop the automation service."""
        if not self._running:
            return

        self._running = False
        monitoring_service.remove_callback(self._on_metrics)

        await storage_service.store_audit(
            action="automation_stopped",
            details="Automation service stopped",
            triggered_by="user"
        )

    async def _on_metrics(self, metrics: PowerwallMetrics) -> None:
        """Callback when new metrics are available."""
        if not self._running:
            return

        # Check cooldown
        if self._last_action_time:
            elapsed = (datetime.now() - self._last_action_time).total_seconds()
            if elapsed < config.automation_cooldown:
                return

        # Get average power over the configured window
        avg_power = monitoring_service.get_average_home_power(config.automation_average_window)
        if avg_power is None:
            return

        # Evaluate rules in order
        for rule in self.rules:
            if not rule.enabled:
                continue

            if rule.evaluate(avg_power):
                # Check if we actually need to change the reserve
                current_reserve = metrics.backup_reserve
                if abs(current_reserve - rule.target_reserve) < 1.0:
                    # Already at or near target, update cooldown timer and skip
                    self._last_action_time = datetime.now()
                    break

                # Execute the rule
                await self._execute_rule(rule, avg_power, current_reserve)
                break  # Only execute first matching rule

    async def _execute_rule(self, rule: AutomationRule, avg_power: float, current_reserve: float) -> None:
        """Execute a rule and change the backup reserve."""
        try:
            # Double-check actual current reserve before making API call
            actual_reserve = await powerwall_service.get_backup_reserve()
            if abs(actual_reserve - rule.target_reserve) < 1.0:
                # Already at target, just update cooldown and skip
                self._last_action_time = datetime.now()
                return

            await powerwall_service.set_backup_reserve(rule.target_reserve)
            self._last_action_time = datetime.now()

            await storage_service.store_audit(
                action="backup_reserve_changed",
                details=f"Rule '{rule.name}' triggered: avg power {avg_power:.2f}kW {rule.operator.value} {rule.threshold}kW",
                old_value=f"{actual_reserve:.1f}%",
                new_value=f"{rule.target_reserve:.1f}%",
                triggered_by="automation"
            )
        except Exception as e:
            await storage_service.store_audit(
                action="automation_error",
                details=f"Failed to execute rule '{rule.name}': {str(e)}",
                triggered_by="automation"
            )


# Global service instance
automation_service = AutomationService()
