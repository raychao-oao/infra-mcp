import pytest

from main.tools.deploy_service import deploy_service
from main.tools.record_service import record_service


@pytest.mark.asyncio
async def test_deploy_refuses_nonstandard(store):
    await record_service(store, "example-stack", "caddy", "prod", "docker", port=80)
    r = await deploy_service(store, "example-stack", "caddy", "prod")
    assert r["success"] is False
    assert r["error"] == "NONSTANDARD_LAYER"
