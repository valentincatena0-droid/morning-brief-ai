"""Schedule gate. GitHub cron is best-effort and UTC-only, so the workflow ticks every 30 minutes and this
decides whether a brief is due. Self-healing: a delayed/skipped tick is caught by the next one."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def day_allowed(local: datetime, brief_cfg: dict) -> bool:
    freq = brief_cfg.get("frequency", "every_day")
    if freq == "every_day":
        return True
    if freq == "weekdays":
        return local.weekday() < 5
    if freq == "custom":
        return DAYS[local.weekday()] in [d.lower()[:3] for d in brief_cfg.get("custom_days", [])]
    return True


def should_run(now: datetime, settings: dict, existing_dates: set[str], grace_hours: float = 6) -> tuple[bool, str]:
    b = settings["brief"]
    tz = ZoneInfo(b["timezone"])
    local = now.astimezone(tz)
    today = local.strftime("%Y-%m-%d")
    if today in existing_dates:
        return False, f"brief for {today} already exists"
    if not day_allowed(local, b):
        return False, f"{local.strftime('%A')} is not a brief day ({b.get('frequency')})"
    hh, mm = (int(x) for x in b["time"].split(":"))
    due = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if local < due:
        return False, f"not yet {b['time']} in {b['timezone']} (local {local.strftime('%H:%M')})"
    if local > due + timedelta(hours=grace_hours):
        return False, f"missed the {b['time']} window by more than {grace_hours}h; skipping stale brief (use --force)"
    return True, f"due since {b['time']} {b['timezone']}"
