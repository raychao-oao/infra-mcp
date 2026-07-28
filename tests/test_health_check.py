"""
Tests for the /health endpoint's database probe.

Regression coverage for: the probe used to call only
list_port_allocations(), which never touches service_deployments — so a DB
with schema drift in that table (missing/renamed column, e.g. mid-migration)
still reported "healthy" while every deployment query raised "no such
column". Auto-deploy's rollback greps this endpoint for "healthy", so a
false-healthy report meant the rollback never triggered.
"""

import sqlite3

import pytest

import main.server as server
from main.db.sqlite_store import SQLiteStore


@pytest.mark.asyncio
async def test_health_check_healthy_on_good_store(store, monkeypatch):
    monkeypatch.setattr(server, "store", store)
    result = await server.health_check()
    assert result["status"] == "healthy"
    assert result["checks"]["database"] == "ok"


@pytest.mark.asyncio
async def test_health_check_degraded_when_service_deployments_broken(tmp_path, monkeypatch):
    # Build a DB whose port_allocations table is intact (so the old, narrower
    # probe would pass) but whose service_deployments table is broken —
    # simulating schema drift that only shows up on deployment queries.
    db_path = tmp_path / "broken.db"

    broken_store = SQLiteStore(f"sqlite+aiosqlite:///{db_path}")
    await broken_store.initialize()

    # Sabotage service_deployments after initialize() created it normally,
    # so list_port_allocations() still works but list_service_deployments()
    # cannot find its table.
    conn = sqlite3.connect(str(db_path))
    conn.execute("ALTER TABLE service_deployments RENAME TO service_deployments_old")
    conn.commit()
    conn.close()

    monkeypatch.setattr(server, "store", broken_store)
    result = await server.health_check()
    assert result["status"] == "degraded"
    assert result["checks"]["database"] == "error"

    await broken_store.close()


@pytest.mark.asyncio
async def test_health_check_not_initialized_when_store_missing(monkeypatch):
    monkeypatch.setattr(server, "store", None)
    result = await server.health_check()
    assert result["status"] == "degraded"
    assert result["checks"]["database"] == "not_initialized"
