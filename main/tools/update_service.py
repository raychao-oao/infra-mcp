"""
update_service MCP Tool Implementation

Correct a deployment record without redeploying anything.

The registry drifts: a service moves directory, gains a hostname, is superseded
by a successor nobody registered. Until now the only way to fix a record was to
open the SQLite file by hand — so in practice records were left wrong, and every
tool that trusts them inherited the error. `upgrade_service` is not this tool: it
changes a service's *type* and rewrites its Caddy config on the box.

This tool touches the database only. It never restarts, redeploys or writes a
file on any server.
"""

from typing import Optional, Dict, Any, List

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore
from main.models.service_deployment import DeploymentStatus, ServiceLayer
from main.utils import validate_project_path, validate_recorded_path, validate_safe_string

# Fields the caller may set, and the subset that may be cleared back to NULL.
# service_type is deliberately absent: changing it without regenerating the
# Caddy config would leave the record and the box disagreeing — that is what
# upgrade_service is for.
#
# layer is updatable but not clearable: it is NOT NULL on the model (default
# STANDARD), and it is how a migration mis-classification gets corrected
# after the fact — there is no "unset" state for it.
UPDATABLE_FIELDS = [
    "port", "hostname", "tunnel_name", "layer",
    "project_root", "deploy_root", "workspace_url", "path_overrides",
    "caddy_rules", "environment", "systemd_config", "notes",
]

# project/service/server identify the record; status has its own timestamps.
CLEARABLE_FIELDS = [
    "port", "hostname", "tunnel_name",
    "project_root", "deploy_root", "workspace_url", "path_overrides",
    "caddy_rules", "environment", "systemd_config", "notes",
]

# project_root/deploy_root are validated against the record's (post-update)
# layer: validate_project_path for STANDARD, validate_recorded_path for
# NONSTANDARD. path_overrides is a dict, not a plain path, so it is validated
# per-value inline rather than through this list.
PATH_FIELDS = ["project_root", "deploy_root"]

VALID_STATUSES = [s.value for s in DeploymentStatus]
VALID_LAYERS = [l.value for l in ServiceLayer]


async def _would_conflict(
    store: SQLiteStore,
    deployment,
    field: str,
    value: Any
) -> List[Dict[str, Any]]:
    """
    Live deployments on the same server that already hold `value` for `field`.

    Pointing a record at a hostname or port another service is using is how a
    registry starts describing the wrong thing — and downstream tools locate
    Caddy sites and units by exactly these values. Purged records are ignored;
    they hold nothing.
    """
    if value is None:
        return []

    holders = []
    for other in await store.list_service_deployments():
        if other.deployment_id == deployment.deployment_id:
            continue
        if other.server != deployment.server:
            continue
        if other.status == DeploymentStatus.PURGED:
            continue
        if getattr(other, field, None) == value:
            holders.append({
                "project": other.project,
                "service": other.service,
                "status": other.status.value,
            })
    return holders


async def update_service(
    store: SQLiteStore,
    project: str,
    service: str,
    server: str,
    port: Optional[int] = None,
    hostname: Optional[str] = None,
    tunnel_name: Optional[str] = None,
    layer: Optional[str] = None,
    project_root: Optional[str] = None,
    deploy_root: Optional[str] = None,
    workspace_url: Optional[str] = None,
    path_overrides: Optional[Dict] = None,
    caddy_rules: Optional[Dict] = None,
    environment: Optional[Dict] = None,
    systemd_config: Optional[Dict] = None,
    notes: Optional[str] = None,
    status: Optional[str] = None,
    clear: Optional[List[str]] = None,
    force: bool = False
) -> Dict[str, Any]:
    """
    Update a service deployment record.

    Args:
        store: SQLiteStore instance
        project: Project name
        service: Service name
        server: VPS server name
        port..notes: New values; omit a field to leave it alone
        layer: "standard" or "nonstandard" — corrects a migration
            mis-classification. Changes what project_root/deploy_root mean
            (decision vs. observation) and what validator new paths go through.
        status: One of registered/deployed/stopped/archived/purged
        clear: Field names to set back to NULL (omitting a field does NOT clear it)
        force: Proceed even if another live deployment already holds the same
               hostname or port

    Returns:
        Dict with the fields that changed, old value → new value
    """
    if server not in INFRA_SERVERS:
        return {
            "success": False,
            "error": "INVALID_SERVER",
            "message": f"Server '{server}' must be one of {INFRA_SERVERS}"
        }

    deployment = await store.get_service_deployment(project, service, server)
    if not deployment:
        return {
            "success": False,
            "error": "SERVICE_NOT_FOUND",
            "message": f"No deployment record for {project}/{service} on {server}"
        }

    if deployment.status == DeploymentStatus.PURGED:
        return {
            "success": False,
            "error": "SERVICE_PURGED",
            "message": (
                f"{project}/{service} on {server} is purged. Editing a purged record "
                f"revives a description of something that no longer exists — register "
                f"the current service instead."
            )
        }

    if layer is not None and layer not in VALID_LAYERS:
        return {
            "success": False,
            "error": "INVALID_LAYER",
            "message": f"Layer '{layer}' must be one of {VALID_LAYERS}"
        }

    updates = {
        "port": port, "hostname": hostname, "tunnel_name": tunnel_name,
        "layer": layer,
        "project_root": project_root, "deploy_root": deploy_root,
        "workspace_url": workspace_url, "path_overrides": path_overrides,
        "caddy_rules": caddy_rules, "environment": environment,
        "systemd_config": systemd_config, "notes": notes,
    }
    updates = {k: v for k, v in updates.items() if v is not None}

    # Paths are validated against the layer the record will have *after* this
    # update — a caller correcting layer=nonstandard in the same call is
    # exactly the case where the old layer's validator would be wrong.
    target_layer = ServiceLayer(layer) if layer is not None else deployment.layer

    if path_overrides is not None:
        allowed_keys = {"app", "static", "data", "config", "log"}
        for key in path_overrides:
            if key not in allowed_keys:
                return {
                    "success": False,
                    "error": "INVALID_PATH_OVERRIDE_KEY",
                    "message": f"Invalid path_overrides key '{key}': must be one of {sorted(allowed_keys)}"
                }

    if target_layer == ServiceLayer.STANDARD:
        # Promoting to (or staying) standard means project_root/deploy_root/
        # path_overrides are decisions this server derives paths from — they
        # must be project-scoped. Validate the *effective* post-update value
        # (this call's, or else what is already stored), not just values this
        # call happens to be setting: a bare layer="standard" flip with no
        # path arguments still changes what the stored NONSTANDARD-observed
        # roots mean, and deploy_service only guards on layer, not on
        # whether the roots were ever checked against this validator.
        effective_project_root = project_root if project_root is not None else deployment.project_root
        effective_deploy_root = deploy_root if deploy_root is not None else deployment.deploy_root
        effective_overrides = path_overrides if path_overrides is not None else (deployment.path_overrides or {})

        for field, value in (("project_root", effective_project_root), ("deploy_root", effective_deploy_root)):
            if value is None:
                continue
            try:
                validate_project_path(value, project, field)
            except ValueError as e:
                return {"success": False, "error": "INVALID_PATH", "message": str(e)}

        for key, value in effective_overrides.items():
            try:
                validate_project_path(value, project, f"path_overrides.{key}")
            except ValueError as e:
                return {"success": False, "error": "INVALID_PATH", "message": str(e)}
    else:
        # Staying/moving to nonstandard: only values this call is actually
        # setting need checking — the looser recorded-path validator, since
        # an observation can live anywhere.
        for field in PATH_FIELDS:
            value = updates.get(field)
            if value is None:
                continue
            try:
                validate_recorded_path(value, field)
            except ValueError as e:
                return {"success": False, "error": "INVALID_PATH", "message": str(e)}

        if path_overrides is not None:
            for key, value in path_overrides.items():
                try:
                    validate_recorded_path(value, f"path_overrides.{key}")
                except ValueError as e:
                    return {"success": False, "error": "INVALID_PATH", "message": str(e)}

    if workspace_url is not None:
        try:
            validate_safe_string(workspace_url, "workspace_url")
        except ValueError as e:
            return {"success": False, "error": "INVALID_WORKSPACE_URL", "message": str(e)}

    clear = clear or []
    for field in clear:
        if field not in CLEARABLE_FIELDS:
            return {
                "success": False,
                "error": "INVALID_CLEAR_FIELD",
                "message": f"Cannot clear '{field}'. Clearable: {CLEARABLE_FIELDS}"
            }
        if field in updates:
            return {
                "success": False,
                "error": "CONTRADICTORY_UPDATE",
                "message": f"Field '{field}' is both given a value and listed in clear"
            }

    if status is not None and status not in VALID_STATUSES:
        return {
            "success": False,
            "error": "INVALID_STATUS",
            "message": f"Status '{status}' must be one of {VALID_STATUSES}"
        }

    if not updates and not clear and status is None:
        return {
            "success": False,
            "error": "NOTHING_TO_UPDATE",
            "message": "No fields given. Pass at least one field, `clear`, or `status`."
        }

    # A record pointing at another service's hostname or port is exactly the
    # drift that made purge_service dangerous. Refuse unless told otherwise.
    if not force:
        for field in ("hostname", "port"):
            if field in updates:
                holders = await _would_conflict(store, deployment, field, updates[field])
                if holders:
                    return {
                        "success": False,
                        "error": "RESOURCE_IN_USE",
                        "message": (
                            f"{field} {updates[field]} on {server} is already held by "
                            + ", ".join(f"{h['project']}/{h['service']} ({h['status']})" for h in holders)
                            + ". Pass force=true if the record really should say this."
                        ),
                        "holders": holders,
                    }

    before = {f: getattr(deployment, f) for f in UPDATABLE_FIELDS}
    before["status"] = deployment.status.value
    before["layer"] = before["layer"].value if before["layer"] is not None else None

    try:
        if updates or clear:
            updated = await store.update_service_deployment(
                deployment_id=deployment.deployment_id,
                clear=clear or None,
                **updates
            )
            if not updated:
                return {
                    "success": False,
                    "error": "UPDATE_FAILED",
                    "message": f"Deployment {deployment.deployment_id} vanished mid-update"
                }
            deployment = updated

        if status is not None:
            updated = await store.update_service_status(
                deployment_id=deployment.deployment_id,
                status=status
            )
            if updated:
                deployment = updated

    except Exception as e:
        return {
            "success": False,
            "error": "UPDATE_FAILED",
            "message": f"Failed to update record: {str(e)}"
        }

    after = {f: getattr(deployment, f) for f in UPDATABLE_FIELDS}
    after["status"] = deployment.status.value
    after["layer"] = after["layer"].value if after["layer"] is not None else None

    changed = {
        f: {"from": before[f], "to": after[f]}
        for f in after
        if before[f] != after[f]
    }

    return {
        "success": True,
        "deployment_id": deployment.deployment_id,
        "project": deployment.project,
        "service": deployment.service,
        "server": deployment.server,
        "changed": changed,
        "message": (
            f"Updated {project}/{service} on {server}: "
            + (", ".join(changed) if changed else "no field actually differed")
        ),
        "note": "Record only — nothing was restarted, redeployed or written on the server."
    }


async def validate_update_service_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for update_service tool.

    Structural checks only. project_root/deploy_root/path_overrides content
    is validated inside update_service() itself, because which validator
    applies (validate_project_path vs. validate_recorded_path) depends on the
    record's layer — the *stored* record, not this input dict — after this
    call's own layer= is applied, if given. This function has no store access.
    """
    for field in ["project", "service", "server"]:
        if field not in data:
            return False, f"Missing required field: {field}"
        if not isinstance(data[field], str):
            return False, f"Field '{field}' must be a string"

    if "port" in data and data["port"] is not None:
        if not isinstance(data["port"], int):
            return False, "Field 'port' must be an integer"

    string_fields = ["hostname", "tunnel_name", "project_root", "deploy_root",
                     "workspace_url", "notes", "status", "layer"]
    for field in string_fields:
        if field in data and data[field] is not None:
            if not isinstance(data[field], str):
                return False, f"Field '{field}' must be a string"

    if "layer" in data and data["layer"] is not None:
        if data["layer"] not in VALID_LAYERS:
            return False, f"Field 'layer' must be one of {VALID_LAYERS}"

    if "path_overrides" in data and data["path_overrides"] is not None:
        overrides = data["path_overrides"]
        if not isinstance(overrides, dict):
            return False, "Field 'path_overrides' must be a dict/object"
        allowed_keys = {"app", "static", "data", "config", "log"}
        for key, value in overrides.items():
            if key not in allowed_keys:
                return False, f"Invalid path_overrides key '{key}': must be one of {sorted(allowed_keys)}"
            if not isinstance(value, str):
                return False, f"path_overrides['{key}'] must be a string"

    dict_fields = ["caddy_rules", "environment", "systemd_config"]
    for field in dict_fields:
        if field in data and data[field] is not None:
            if not isinstance(data[field], dict):
                return False, f"Field '{field}' must be a dict/object"

    if "clear" in data and data["clear"] is not None:
        if not isinstance(data["clear"], list):
            return False, "Field 'clear' must be a list of field names"
        for field in data["clear"]:
            if not isinstance(field, str):
                return False, "Field 'clear' must contain only strings"

    if "force" in data and data["force"] is not None:
        if not isinstance(data["force"], bool):
            return False, "Field 'force' must be a boolean"

    return True, None
