"""FastAPI API routes for Powerwall Controller."""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import config
from app.services.powerwall_service import powerwall_service
from app.services.storage_service import storage_service
from app.services.monitoring_service import monitoring_service
from app.services.automation_service import automation_service, AutomationRule, RuleOperator

router = APIRouter(prefix="/api")


# Pydantic models for request/response
class ConfigUpdate(BaseModel):
    mode: Optional[str] = None
    host: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    timezone: Optional[str] = None
    gw_password: Optional[str] = None


class RuleCreate(BaseModel):
    name: str
    operator: str
    threshold: float
    target_reserve: float
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    operator: Optional[str] = None
    threshold: Optional[float] = None
    target_reserve: Optional[float] = None
    enabled: Optional[bool] = None


class RuleReorder(BaseModel):
    rule_ids: list[str]


class BackupReserveSet(BaseModel):
    percentage: float


# Status endpoints
@router.get("/status")
async def get_status():
    """Get overall system status."""
    return {
        "powerwall_connected": powerwall_service.is_connected,
        "monitoring_running": monitoring_service.is_running,
        "automation_running": automation_service.is_running,
        "configured": config.is_configured(),
    }


# Configuration endpoints
@router.get("/config")
async def get_config():
    """Get current configuration (excluding password)."""
    return {
        "mode": config.powerwall_mode,
        "host": config.powerwall_host,
        "email": config.powerwall_email,
        "has_password": bool(config.powerwall_password),
        "has_gw_password": bool(config.powerwall_gw_password),
        "timezone": config.powerwall_timezone,
        "port": config.server_port,
        "monitoring_interval": config.monitoring_interval,
        "automation_cooldown": config.automation_cooldown,
        "automation_average_window": config.automation_average_window,
    }


@router.post("/config")
async def update_config(update: ConfigUpdate):
    """Update Powerwall configuration."""
    if update.mode is not None:
        config.powerwall_mode = update.mode
    if update.host is not None:
        config.powerwall_host = update.host
    if update.email is not None:
        config.powerwall_email = update.email
    if update.password is not None:
        config.powerwall_password = update.password
    if update.timezone is not None:
        config.powerwall_timezone = update.timezone
    if update.gw_password is not None:
        config.powerwall_gw_password = update.gw_password

    config.save()

    await storage_service.store_audit(
        action="config_updated",
        details="Powerwall configuration updated",
        triggered_by="user"
    )

    return {"success": True}


# Connection endpoints
@router.post("/connection/test")
async def test_connection():
    """Test connection to Powerwall with diagnostics."""
    storage_service.initialize()
    result = await powerwall_service.test_connection()
    return {
        "success": result.success,
        "steps": [
            {"name": step[0], "success": step[1], "message": step[2]}
            for step in result.steps
        ],
        "error": result.error,
    }


@router.post("/connection/connect")
async def connect():
    """Connect to the Powerwall."""
    try:
        await powerwall_service.connect()
        await storage_service.store_audit(
            action="powerwall_connected",
            details=f"Connected to Powerwall at {config.powerwall_host}",
            triggered_by="user"
        )
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/connection/disconnect")
async def disconnect():
    """Disconnect from the Powerwall."""
    await powerwall_service.disconnect()
    return {"success": True}


# Monitoring endpoints
@router.get("/monitoring/status")
async def get_monitoring_status():
    """Get monitoring status and last metrics."""
    return {
        "running": monitoring_service.is_running,
        "last_metrics": _metrics_to_dict(monitoring_service.last_metrics) if monitoring_service.last_metrics else None,
    }


@router.post("/monitoring/start")
async def start_monitoring():
    """Start monitoring."""
    try:
        await monitoring_service.start()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/monitoring/stop")
async def stop_monitoring():
    """Stop monitoring."""
    # Stop automation first if running
    if automation_service.is_running:
        await automation_service.stop()
    await monitoring_service.stop()
    return {"success": True}


@router.get("/monitoring/current")
async def get_current_metrics():
    """Get current metrics."""
    if not monitoring_service.is_running:
        raise HTTPException(status_code=400, detail="Monitoring is not running")

    metrics = monitoring_service.last_metrics
    if not metrics:
        raise HTTPException(status_code=404, detail="No metrics available yet")

    return _metrics_to_dict(metrics)


@router.get("/monitoring/recent")
async def get_recent_metrics(seconds: int = 300):
    """Get recent metrics from memory."""
    metrics = monitoring_service.recent_metrics
    return [_metrics_to_dict(m) for m in metrics]


# Automation endpoints
@router.get("/automation/status")
async def get_automation_status():
    """Get automation status."""
    return {
        "running": automation_service.is_running,
        "rules_count": len(automation_service.rules),
    }


@router.post("/automation/start")
async def start_automation():
    """Start automation."""
    try:
        await automation_service.start()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/automation/stop")
async def stop_automation():
    """Stop automation."""
    await automation_service.stop()
    return {"success": True}


@router.get("/automation/rules")
async def get_rules():
    """Get all automation rules."""
    return [r.to_dict() for r in automation_service.rules]


@router.post("/automation/rules")
async def create_rule(rule: RuleCreate):
    """Create a new automation rule."""
    try:
        new_rule = AutomationRule(
            id="",
            name=rule.name,
            operator=RuleOperator(rule.operator),
            threshold=rule.threshold,
            target_reserve=rule.target_reserve,
            enabled=rule.enabled,
        )
        automation_service.add_rule(new_rule)

        await storage_service.store_audit(
            action="rule_created",
            details=f"Created rule '{rule.name}': if usage {rule.operator} {rule.threshold}kW, set reserve to {rule.target_reserve}%",
            triggered_by="user"
        )

        return new_rule.to_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/automation/rules/{rule_id}")
async def update_rule(rule_id: str, update: RuleUpdate):
    """Update an automation rule."""
    updates = {k: v for k, v in update.model_dump().items() if v is not None}
    rule = automation_service.update_rule(rule_id, updates)

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    await storage_service.store_audit(
        action="rule_updated",
        details=f"Updated rule '{rule.name}'",
        triggered_by="user"
    )

    return rule.to_dict()


@router.delete("/automation/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """Delete an automation rule."""
    # Find rule name before deletion for audit
    rule_name = None
    for r in automation_service.rules:
        if r.id == rule_id:
            rule_name = r.name
            break

    if not automation_service.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")

    await storage_service.store_audit(
        action="rule_deleted",
        details=f"Deleted rule '{rule_name}'",
        triggered_by="user"
    )

    return {"success": True}


@router.post("/automation/rules/reorder")
async def reorder_rules(reorder: RuleReorder):
    """Reorder automation rules."""
    automation_service.reorder_rules(reorder.rule_ids)
    return {"success": True}


# Manual control endpoints
@router.post("/powerwall/backup-reserve")
async def set_backup_reserve(data: BackupReserveSet):
    """Manually set backup reserve."""
    if not powerwall_service.is_connected:
        raise HTTPException(status_code=400, detail="Not connected to Powerwall")

    try:
        current = await powerwall_service.get_backup_reserve()

        # Only make changes if the value is actually different
        if abs(current - data.percentage) < 0.5:
            return {"success": True, "message": "Already at target reserve"}

        await powerwall_service.set_backup_reserve(data.percentage)

        await storage_service.store_audit(
            action="backup_reserve_changed",
            details="Manual backup reserve change",
            old_value=f"{current:.1f}%",
            new_value=f"{data.percentage:.1f}%",
            triggered_by="user"
        )

        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# History endpoints
@router.get("/history/metrics")
async def get_history_metrics(
    start: Optional[str] = None,
    end: Optional[str] = None,
    hours: float = 24
):
    """Get historical metrics."""
    if start and end:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    else:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(hours=hours)

    metrics = await storage_service.query_metrics(start_dt, end_dt)
    return [_format_stored_metrics(m) for m in metrics]


@router.get("/history/events")
async def get_history_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    hours: int = 24
):
    """Get historical events for overlay on graphs."""
    if start and end:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    else:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(hours=hours)

    events = await storage_service.get_events_for_period(start_dt, end_dt)
    return [_format_audit_entry(e) for e in events]


# Audit log endpoints
@router.get("/audit")
async def get_audit_log(
    start: Optional[str] = None,
    end: Optional[str] = None,
    days: int = 7,
    limit: int = 1000
):
    """Get audit log entries."""
    if start and end:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    else:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days)

    entries = await storage_service.query_audit(start_dt, end_dt, limit)
    return [_format_audit_entry(e) for e in entries]


# Helper functions
def _metrics_to_dict(metrics) -> dict:
    """Convert PowerwallMetrics to dict."""
    return {
        "timestamp": metrics.timestamp.isoformat(),
        "battery_percentage": metrics.battery_percentage,
        "battery_power": metrics.battery_power,
        "solar_power": metrics.solar_power,
        "home_power": metrics.home_power,
        "grid_power": metrics.grid_power,
        "backup_reserve": metrics.backup_reserve,
        "grid_status": metrics.grid_status,
        "battery_capacity": metrics.battery_capacity,
    }


def _format_stored_metrics(m: dict) -> dict:
    """Format stored metrics dict."""
    return {
        "timestamp": m["timestamp"].isoformat() if hasattr(m["timestamp"], "isoformat") else str(m["timestamp"]),
        "battery_percentage": m["battery_percentage"],
        "battery_power": m["battery_power"],
        "solar_power": m["solar_power"],
        "home_power": m["home_power"],
        "grid_power": m["grid_power"],
        "backup_reserve": m["backup_reserve"],
        "grid_status": m["grid_status"],
        "battery_capacity": m["battery_capacity"],
    }


def _format_audit_entry(e: dict) -> dict:
    """Format audit entry dict."""
    return {
        "timestamp": e["timestamp"].isoformat() if hasattr(e["timestamp"], "isoformat") else str(e["timestamp"]),
        "action": e["action"],
        "details": e["details"],
        "old_value": e["old_value"],
        "new_value": e["new_value"],
        "triggered_by": e["triggered_by"],
    }
