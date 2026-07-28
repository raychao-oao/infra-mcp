import pytest

from main.tools.record_service import record_service
from main.utils import validate_recorded_path


@pytest.mark.asyncio
async def test_records_observed_facts_only(store):
    r = await record_service(store, "example-stack", "caddy", "prod", "docker",
                             port=80, project_root="~/example-stack/")
    assert r["success"]
    cfg = r["configuration"]
    assert cfg["layer"] == "nonstandard"
    assert cfg["project_root"] == "~/example-stack/"
    assert cfg["deploy_root"] is None
    assert cfg["workspace_url"] is None


@pytest.mark.asyncio
async def test_no_defaults_invented(store):
    r = await record_service(store, "example-stack", "app", "prod", "flask")
    assert r["configuration"]["project_root"] is None


@pytest.mark.asyncio
async def test_duplicate_rejected(store):
    await record_service(store, "example-stack", "caddy", "prod", "docker")
    r = await record_service(store, "example-stack", "caddy", "prod", "docker")
    assert r["error"] == "SERVICE_ALREADY_REGISTERED"


def test_recorded_path_allows_nonproject_locations():
    assert validate_recorded_path("~/example-stack/", "project_root")


def test_recorded_path_rejects_traversal():
    with pytest.raises(ValueError):
        validate_recorded_path("~/a/../../etc/", "project_root")
