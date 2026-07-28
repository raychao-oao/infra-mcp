import pytest

from main.tools.register_service import register_service


@pytest.mark.asyncio
async def test_flask_allocates_roots_no_deploy_root(store):
    r = await register_service(store, "example", "api", "prod", "flask")
    assert r["success"]
    cfg = r["configuration"]
    assert cfg["layer"] == "standard"
    assert cfg["project_root"] == "~/PRJ/example/"
    assert cfg["deploy_root"] is None


@pytest.mark.asyncio
async def test_static_allocates_deploy_root(store):
    r = await register_service(store, "example", "web", "prod", "static")
    assert r["configuration"]["deploy_root"] == "/var/www/example/"


@pytest.mark.asyncio
async def test_no_subpath_fields_in_response(store):
    r = await register_service(store, "example", "api2", "prod", "flask")
    for old in ("app_path", "static_path", "data_path", "config_path", "log_path"):
        assert old not in r["configuration"]


@pytest.mark.asyncio
async def test_duplicate_rejected(store):
    await register_service(store, "example", "api", "prod", "flask")
    r = await register_service(store, "example", "api", "prod", "flask")
    assert r["error"] == "SERVICE_ALREADY_REGISTERED"
