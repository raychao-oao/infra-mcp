"""
Tests for the "other consumers" of the resource model: update_service,
get_service_info, purge_service (directory-removal decision point).

record_service / register_service already have their own test files; this
one is about the tools that read a deployment record back out, or correct
it after the fact.
"""

import pytest

from main.tools.record_service import record_service
from main.tools.register_service import register_service
from main.tools.update_service import update_service
from main.tools.get_service_info import get_service_info


@pytest.mark.asyncio
async def test_update_layer_and_workspace_url(store):
    await record_service(store, "example-stack", "app", "prod", "flask")
    r = await update_service(store, "example-stack", "app", "prod",
                              workspace_url="https://git.example.com/me/project-example")
    assert r["success"]
    info = await get_service_info(store, "example-stack", "app", "prod")
    assert info["workspace_url"].endswith("project-example")


@pytest.mark.asyncio
async def test_update_layer_to_standard_rejects_out_of_scope_stored_root(store):
    # record_service accepts any observed location for NONSTANDARD — this one
    # is deliberately outside every project-scoped root.
    await record_service(store, "weird-project", "app", "prod", "flask",
                          project_root="/opt/weird/app/")
    r = await update_service(store, "weird-project", "app", "prod", layer="standard")
    assert not r["success"]
    assert r["error"] == "INVALID_PATH"

    # And the record must not have been silently promoted anyway.
    info = await get_service_info(store, "weird-project", "app", "prod")
    assert info["layer"] == "nonstandard"


@pytest.mark.asyncio
async def test_update_layer_to_standard_succeeds_with_compliant_root(store):
    await record_service(store, "weird-project", "app", "prod", "flask",
                          project_root="/opt/weird/app/",
                          path_overrides={"data": "/opt/weird/app/data/"})
    # Supplying a compliant project_root and overriding path_overrides in the
    # same call replaces both offending stored values before validation runs.
    r = await update_service(
        store, "weird-project", "app", "prod",
        layer="standard",
        project_root="~/PRJ/weird-project/",
        path_overrides={"data": "~/PRJ/weird-project/data/"},
    )
    assert r["success"]

    info = await get_service_info(store, "weird-project", "app", "prod")
    assert info["layer"] == "standard"
    assert info["project_root"] == "~/PRJ/weird-project/"


@pytest.mark.asyncio
async def test_update_layer_to_standard_with_clear_discards_bad_root(store):
    # Promoting to standard while discarding the offending root via `clear`
    # must succeed: a NULL effective project_root needs no validation, since
    # resolve_paths() derives nothing from a root that isn't there.
    await record_service(store, "weird-project", "app", "prod", "flask",
                          project_root="/opt/weird/app/")
    r = await update_service(store, "weird-project", "app", "prod",
                              layer="standard", clear=["project_root"])
    assert r["success"]

    info = await get_service_info(store, "weird-project", "app", "prod")
    assert info["layer"] == "standard"
    assert info["project_root"] is None


@pytest.mark.asyncio
async def test_update_layer_field_corrects_misclassification(store):
    # register_service allocates STANDARD; correcting to nonstandard is
    # exactly the migration-mis-classification fix this field exists for.
    await register_service(store, "example", "api", "prod", "flask")
    r = await update_service(store, "example", "api", "prod", layer="nonstandard")
    assert r["success"]
    assert r["changed"]["layer"]["to"] == "nonstandard"

    info = await get_service_info(store, "example", "api", "prod")
    assert info["layer"] == "nonstandard"


@pytest.mark.asyncio
async def test_update_layer_rejects_invalid_value(store):
    await register_service(store, "example", "api", "prod", "flask")
    r = await update_service(store, "example", "api", "prod", layer="weird")
    assert not r["success"]
    assert r["error"] == "INVALID_LAYER"


@pytest.mark.asyncio
async def test_info_warns_on_missing_workspace(store):
    await register_service(store, "example", "api", "prod", "flask")
    info = await get_service_info(store, "example", "api", "prod")
    assert info["workspace_url"] is None
    assert info["workspace_url_warning"] == "no source of truth recorded"


@pytest.mark.asyncio
async def test_info_no_warning_when_workspace_recorded(store):
    await register_service(store, "example", "api", "prod", "flask",
                            workspace_url="https://git.example.com/me/project-example")
    info = await get_service_info(store, "example", "api", "prod")
    assert "workspace_url_warning" not in info


@pytest.mark.asyncio
async def test_info_directories_are_derived(store):
    await register_service(store, "example", "api", "prod", "flask")
    info = await get_service_info(store, "example", "api", "prod")
    dirs = info["directories"]
    assert dirs["data"] == "~/PRJ/example/data/"


def test_purge_never_removes_nonstandard_dirs():
    from types import SimpleNamespace
    from main.models.service_deployment import ServiceLayer, ServiceType
    from main.tools.purge_service import _dirs_to_remove
    d = SimpleNamespace(layer=ServiceLayer.NONSTANDARD, service_type=ServiceType.DOCKER,
                        project="example-stack", project_root="~/example-stack/",
                        deploy_root=None, path_overrides=None)
    assert _dirs_to_remove(d, remove_data=True, remove_static=True, remove_app=True) == []


def test_purge_removes_standard_dirs_when_requested():
    from types import SimpleNamespace
    from main.models.service_deployment import ServiceLayer, ServiceType
    from main.tools.purge_service import _dirs_to_remove
    d = SimpleNamespace(layer=ServiceLayer.STANDARD, service_type=ServiceType.FLASK,
                        project="example", project_root="~/PRJ/example/",
                        deploy_root=None, path_overrides=None)
    result = _dirs_to_remove(d, remove_data=True, remove_app=True)
    labels = {entry["label"] for entry in result}
    assert labels == {"data_path", "app_path"}


def test_purge_dirs_to_remove_respects_flags():
    from types import SimpleNamespace
    from main.models.service_deployment import ServiceLayer, ServiceType
    from main.tools.purge_service import _dirs_to_remove
    d = SimpleNamespace(layer=ServiceLayer.STANDARD, service_type=ServiceType.FLASK,
                        project="example", project_root="~/PRJ/example/",
                        deploy_root=None, path_overrides=None)
    assert _dirs_to_remove(d) == []
