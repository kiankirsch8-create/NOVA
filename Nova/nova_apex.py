"""APEX data fetching module — read-only access to Railway APIs."""

import time
from datetime import datetime, timezone
from typing import Optional, Union

import requests

import nova_config as config

_cache = {
    "backtest": {"data": None, "fetched_at": 0},
    "live": {"data": None, "fetched_at": 0},
    "dashboard": {"data": None, "fetched_at": 0},
    "combined": {"data": None, "fetched_at": 0},
}


def _log_error(message: str) -> None:
    try:
        with open(config.ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} [APEX] {message}\n")
    except OSError:
        pass


def _get_json(path: str, timeout: int = 30) -> Optional[Union[dict, str]]:
    url = f"{config.APEX_RAILWAY_URL}{path}"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            return response.text
    except requests.RequestException as exc:
        _log_error(f"GET {path} failed: {exc}")
        return None


def get_backtest_status() -> dict:
    now = time.time()
    if (
        _cache["backtest"]["data"] is not None
        and now - _cache["backtest"]["fetched_at"] < config.BACKTEST_CACHE_SECONDS
    ):
        return _cache["backtest"]["data"]

    raw = _get_json("/api/chrono/active")
    if raw and isinstance(raw, dict):
        data = {
            "current_date": raw.get("current_date"),
            "capital": raw.get("capital"),
            "days_processed": raw.get("days_processed"),
            "win_rate": raw.get("win_rate"),
            "total_trades": raw.get("total_trades"),
            "status": raw.get("status"),
            "active": raw.get("active"),
        }
        _cache["backtest"]["data"] = data
        _cache["backtest"]["fetched_at"] = now
        return data

    if _cache["backtest"]["data"] is not None:
        cached = dict(_cache["backtest"]["data"])
        cached["stale"] = True
        return cached

    return {"error": "unavailable", "stale": True}


def get_live_status() -> dict:
    now = time.time()
    if (
        _cache["live"]["data"] is not None
        and now - _cache["live"]["fetched_at"] < config.LIVE_CACHE_SECONDS
    ):
        return _cache["live"]["data"]

    raw = _get_json("/api/live/status")
    if raw and isinstance(raw, dict):
        open_positions = raw.get("open_positions") or []
        data = {
            "balance": raw.get("balance"),
            "equity": raw.get("equity"),
            "daily_pnl": raw.get("daily_pnl"),
            "open_positions_count": len(open_positions),
            "open_positions": open_positions,
            "period_mode": raw.get("period_mode"),
            "circuit_halt": raw.get("circuit_halt_until"),
            "status": raw.get("status"),
            "dry_run": raw.get("dry_run"),
        }
        _cache["live"]["data"] = data
        _cache["live"]["fetched_at"] = now
        return data

    if _cache["live"]["data"] is not None:
        cached = dict(_cache["live"]["data"])
        cached["stale"] = True
        return cached

    return {"error": "unavailable", "stale": True}


def get_dashboard_summary() -> Union[dict, str]:
    now = time.time()
    if (
        _cache["dashboard"]["data"] is not None
        and now - _cache["dashboard"]["fetched_at"] < config.LIVE_CACHE_SECONDS
    ):
        return _cache["dashboard"]["data"]

    raw = _get_json("/api/dashboard/summary")
    if raw is not None:
        _cache["dashboard"]["data"] = raw
        _cache["dashboard"]["fetched_at"] = now
        return raw

    if _cache["dashboard"]["data"] is not None:
        if isinstance(_cache["dashboard"]["data"], dict):
            return {**_cache["dashboard"]["data"], "stale": True}
        return _cache["dashboard"]["data"]

    return {"error": "unavailable", "stale": True}


def get_apex_status() -> dict:
    """Return combined APEX status from all endpoints."""
    now = time.time()
    if (
        _cache["combined"]["data"] is not None
        and now - _cache["combined"]["fetched_at"] < 30
    ):
        return _cache["combined"]["data"]

    backtest = get_backtest_status()
    live = get_live_status()

    stale = any(
        item.get("stale")
        for item in (backtest, live)
        if isinstance(item, dict)
    )

    combined = {
        "backtest": backtest,
        "live": live,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "stale": stale,
    }

    if not any(
        isinstance(v, dict) and v.get("error") == "unavailable"
        for v in (backtest, live)
    ) or _cache["combined"]["data"] is not None:
        _cache["combined"]["data"] = combined
        _cache["combined"]["fetched_at"] = now

    if _cache["combined"]["data"] is not None and stale:
        return _cache["combined"]["data"]

    return combined


def get_live_logs_text() -> str:
    """Fetch recent live trader log lines."""
    raw = _get_json("/api/live/logs/text")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, dict):
        logs = raw.get("logs") or raw.get("text") or raw.get("tail")
        if isinstance(logs, str) and logs.strip():
            return logs.strip()
        if isinstance(logs, list):
            return "\n".join(str(line) for line in logs[-20:])
    return "Live logs are currently unavailable."


def format_status_for_speech(status: dict) -> str:
    """Abbreviated spoken status format."""
    backtest = status.get("backtest", {})
    live = status.get("live", {})
    dashboard = status.get("dashboard_summary", "")

    if isinstance(dashboard, str) and dashboard.strip():
        return dashboard.strip()

    parts = []
    current_date = backtest.get("current_date", "unknown date")
    capital = backtest.get("capital")
    if capital is not None:
        parts.append(f"Backtest at {current_date}, capital {int(capital)} dollars")
    else:
        parts.append(f"Backtest at {current_date}")

    equity = live.get("equity")
    open_count = live.get("open_positions_count", 0)
    if equity is not None:
        parts.append(f"live equity {int(equity)}")
    parts.append(f"{open_count} open positions")

    if status.get("stale"):
        parts.append("using last known data")

    return ". ".join(parts) + "."
