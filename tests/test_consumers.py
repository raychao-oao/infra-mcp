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


def test_purge_log_dir_retained_when_project_has_siblings():
    # /var/log/{project}/ is shared by every service of the project — must
    # not be deleted while another (non-purged) service of the same project
    # still exists, or its logs go with it.
    from types import SimpleNamespace
    from main.models.service_deployment import ServiceLayer, ServiceType
    from main.tools.purge_service import _dirs_to_remove
    d = SimpleNamespace(layer=ServiceLayer.STANDARD, service_type=ServiceType.FLASK,
                        project="example", project_root="~/PRJ/example/",
                        deploy_root=None, path_overrides=None)
    result = _dirs_to_remove(d, remove_logs=True, log_dir_has_siblings=True)
    assert result == []


def test_purge_log_dir_removed_when_no_siblings():
    from types import SimpleNamespace
    from main.models.service_deployment import ServiceLayer, ServiceType
    from main.tools.purge_service import _dirs_to_remove
    d = SimpleNamespace(layer=ServiceLayer.STANDARD, service_type=ServiceType.FLASK,
                        project="example", project_root="~/PRJ/example/",
                        deploy_root=None, path_overrides=None)
    result = _dirs_to_remove(d, remove_logs=True, log_dir_has_siblings=False)
    labels = {entry["label"] for entry in result}
    assert labels == {"log_path"}


def test_purge_log_override_removed_even_with_siblings():
    # An explicitly recorded path_overrides["log"] is service-specific
    # (someone pointed this one service somewhere else on purpose), so it
    # is removable regardless of siblings sharing the convention directory.
    from types import SimpleNamespace
    from main.models.service_deployment import ServiceLayer, ServiceType
    from main.tools.purge_service import _dirs_to_remove
    d = SimpleNamespace(layer=ServiceLayer.STANDARD, service_type=ServiceType.FLASK,
                        project="example", project_root="~/PRJ/example/",
                        deploy_root=None, path_overrides={"log": "~/PRJ/example/own-logs/"})
    result = _dirs_to_remove(d, remove_logs=True, log_dir_has_siblings=True)
    labels = {entry["label"] for entry in result}
    assert labels == {"log_path"}
    assert result[0]["path"] == "~/PRJ/example/own-logs/"


@pytest.mark.asyncio
async def test_log_dir_has_siblings_true_with_another_live_service(store):
    # This is what purge_service actually calls to decide log_dir_has_siblings
    # — exercised directly (rather than through purge_service end-to-end)
    # because purge_service also needs live SSH access to the target server
    # to build its plan, which is out of scope for a unit test.
    from main.tools.purge_service import _log_dir_has_siblings

    await register_service(store, "example", "api", "prod", "flask")
    await register_service(store, "example", "worker", "prod", "flask")
    d = await store.get_service_deployment("example", "api", "prod")

    assert await _log_dir_has_siblings(store, d) is True


@pytest.mark.asyncio
async def test_log_dir_has_siblings_false_when_alone(store):
    from main.tools.purge_service import _log_dir_has_siblings

    await register_service(store, "solo-project", "api", "prod", "flask")
    d = await store.get_service_deployment("solo-project", "api", "prod")

    assert await _log_dir_has_siblings(store, d) is False


@pytest.mark.asyncio
async def test_log_dir_has_siblings_ignores_purged_siblings(store):
    # A purged sibling no longer has logs of its own to protect.
    from main.tools.purge_service import _log_dir_has_siblings

    await register_service(store, "example", "api", "prod", "flask")
    sibling = await register_service(store, "example", "worker", "prod", "flask")
    await store.update_service_status(sibling["deployment_id"], "purged")
    d = await store.get_service_deployment("example", "api", "prod")

    assert await _log_dir_has_siblings(store, d) is False


@pytest.mark.asyncio
async def test_log_dir_has_siblings_ignores_other_projects(store):
    from main.tools.purge_service import _log_dir_has_siblings

    await register_service(store, "example", "api", "prod", "flask")
    await register_service(store, "other-project", "worker", "prod", "flask")
    d = await store.get_service_deployment("example", "api", "prod")

    assert await _log_dir_has_siblings(store, d) is False


@pytest.mark.asyncio
async def test_info_null_layer_does_not_crash(store, tmp_path):
    # Simulates a row created by the real migration path
    # (scripts/migrate_resource_model.py phase "add"), which adds `layer`
    # as a plain nullable TEXT column and only backfills it afterward — a
    # row can be read with layer IS NULL between those two steps. The ORM
    # metadata used by the `store` fixture declares layer NOT NULL, so this
    # state is built with raw sqlite3 against a schema that matches
    # production mid-migration instead.
    import sqlite3
    from main.db.sqlite_store import SQLiteStore

    db_path = tmp_path / "null_layer.db"
    ddl = """
    CREATE TABLE service_deployments (
        deployment_id VARCHAR NOT NULL,
        project VARCHAR NOT NULL,
        service VARCHAR NOT NULL,
        server VARCHAR NOT NULL,
        service_type VARCHAR(12) NOT NULL,
        port INTEGER,
        hostname VARCHAR,
        tunnel_name VARCHAR,
        layer VARCHAR(11),
        project_root VARCHAR,
        deploy_root VARCHAR,
        workspace_url VARCHAR,
        path_overrides JSON,
        caddy_rules JSON,
        environment JSON,
        systemd_config JSON,
        status VARCHAR(10) NOT NULL,
        registered_at DATETIME NOT NULL,
        registered_by VARCHAR NOT NULL,
        deployed_at DATETIME,
        stopped_at DATETIME,
        archived_at DATETIME,
        purged_at DATETIME,
        notes TEXT,
        backup_config JSON,
        PRIMARY KEY (deployment_id)
    );
    """
    conn = sqlite3.connect(str(db_path))
    conn.executescript(ddl)
    conn.execute(
        "INSERT INTO service_deployments (deployment_id, project, service, server, "
        "service_type, layer, status, registered_at, registered_by) VALUES "
        "('d1', 'midmig', 'api', 'prod', 'FLASK', NULL, 'REGISTERED', "
        "'2026-01-01T00:00:00', 'mcp-server')"
    )
    conn.commit()
    conn.close()

    migrated_store = SQLiteStore(f"sqlite+aiosqlite:///{db_path}")
    try:
        info = await get_service_info(migrated_store, "midmig", "api", "prod")
        assert info["success"]
        assert info["layer"] is None
    finally:
        await migrated_store.close()
