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
from main.models.service_deployment import DeploymentStatus
from main.utils import validate_project_path

# Fields the caller may set, and the subset that may be cleared back to NULL.
# service_type is deliberately absent: changing it without regenerating the
# Caddy config would leave the record and the box disagreeing — that is what
# upgrade_service is for.
UPDATABLE_FIELDS = [
    "port", "hostname", "tunnel_name",
    "app_path", "static_path", "data_path", "log_path", "config_path",
    "caddy_rules", "environment", "systemd_config", "notes",
]

# project/service/server identify the record; status has its own timestamps.
CLEARABLE_FIELDS = [
    "port", "hostname", "tunnel_name",
    "app_path", "static_path", "data_path", "log_path", "config_path",
    "caddy_rules", "environment", "systemd_config", "notes",
]

PATH_FIELDS = ["app_path", "static_path", "data_path", "log_path", "config_path"]

VALID_STATUSES = [s.value for s in DeploymentStatus]


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
    app_path: Optional[str] = None,
    static_path: Optional[str] = None,
    data_path: Optional[str] = None,
    log_path: Optional[str] = None,
    config_path: Optional[str] = None,
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

    updates = {
        "port": port, "hostname": hostname, "tunnel_name": tunnel_name,
        "app_path": app_path, "static_path": static_path, "data_path": data_path,
        "log_path": log_path, "config_path": config_path,
        "caddy_rules": caddy_rules, "environment": environment,
        "systemd_config": systemd_config, "notes": notes,
    }
    updates = {k: v for k, v in updates.items() if v is not None}

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
    """Validate input parameters for update_service tool."""
    for field in ["project", "service", "server"]:
        if field not in data:
            return False, f"Missing required field: {field}"
        if not isinstance(data[field], str):
            return False, f"Field '{field}' must be a string"

    if "port" in data and data["port"] is not None:
        if not isinstance(data["port"], int):
            return False, "Field 'port' must be an integer"

    string_fields = ["hostname", "tunnel_name", "app_path", "static_path",
                     "data_path", "log_path", "config_path", "notes", "status"]
    for field in string_fields:
        if field in data and data[field] is not None:
            if not isinstance(data[field], str):
                return False, f"Field '{field}' must be a string"

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

    project = data.get("project", "")
    for field in PATH_FIELDS:
        if data.get(field):
            try:
                validate_project_path(data[field], project, field)
            except ValueError as e:
                return False, str(e)

    return True, None
