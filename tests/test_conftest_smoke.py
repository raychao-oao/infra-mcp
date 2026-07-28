import pytest


@pytest.mark.asyncio
async def test_store_fixture_initializes(store):
    rows = await store.list_service_deployments()
    assert rows == []
