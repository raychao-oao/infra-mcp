"""
purge_service MCP Tool Implementation
"""

from typing import Optional, Dict, Any, List

from main.db.sqlite_store import SQLiteStore
from main.models.service_deployment import DeploymentStatus
from main.providers.server_snapshot import ServerSnapshot
from main.tools.release_port import release_port
from main.utils import get_service_name, validate_project_path


async def purge_service(
    store: SQLiteStore,
    project: str,
    service: str,
    server: str,
    remove_app_files: bool = False,
    remove_static_files: bool = False,
    remove_data: bool = False,
    remove_logs: bool = False,
    remove_dns_record: bool = False,
    dry_run: bool = False,
    force: bool = False
) -> Dict[str, Any]:
    """
    Completely purge a service and clean up all resources.

    Steps:
    1. Check service exists
    2. Stop service if running (via systemd)
    3. Disable and remove systemd service file
    4. Remove Caddy configuration file
    5. Reload Caddy
    6. Remove DNS record (if requested)
    7. Release port
    8. Optionally delete application files, data, logs
    9. Update status: → purged

    Args:
        store: SQLiteStore instance
        project: Project name
        service: Service name
        server: VPS server name
        remove_app_files: Delete application files (default: False)
        remove_static_files: Delete static files (default: False)
        remove_data: Delete data directory (default: False)
        remove_logs: Delete log files (default: False)
        remove_dns_record: Remove DNS CNAME record (default: False)
        dry_run: Report what would be removed and change nothing (default: False)
        force: Proceed even when another live deployment shares a resource
            (default: False). Only meaningful after reading the reported
            conflicts.

    Returns:
        Dict with success status and cleanup details or error information
    """

    # Get service deployment
    deployment = await store.get_service_deployment(project, service, server)
    if not deployment:
        return {
            "success": False,
            "error": "SERVICE_NOT_FOUND",
            "message": f"Service {project}/{service} not found on {server}"
        }

    # Check status
    if deployment.status.value == "purged":
        return {
            "success": False,
            "error": "ALREADY_PURGED",
            "message": f"Service {project}/{service} is already purged on {server}",
            "deployment_id": deployment.deployment_id
        }

    # Refuse to touch anything another live deployment still depends on.
    #
    # This is not hypothetical. On 2026-07-27 the record for a service that had
    # been superseded months earlier still carried the hostname, port and
    # static_path that by then belonged to its live successor — nobody updates
    # the registry mid-migration. Purging it would have disabled a running
    # service's Caddy site and released a port that was actively serving.
    #
    # It did not blow up at the time only because the Caddy file was derived as
    # {project}-{service}.caddy and no such file existed. That accident stopped
    # being protection the moment the locator was fixed to find files by
    # hostname, which is what the code below now does.
    conflicts = await _find_conflicts(store, deployment)
    if conflicts and not force:
        return {
            "success": False,
            "error": "CONFLICTING_DEPLOYMENTS",
            "message": (
                f"Refusing to purge {project}/{service}: {len(conflicts)} other "
                f"live deployment(s) share resources with it. Purging would "
                f"break them. Retire this record instead, or pass force=true "
                f"if you are certain."
            ),
            "conflicts": conflicts
        }

    steps_completed = []
    cleanup_info = {}

    svc_name = get_service_name(project, service, deployment.systemd_config)

    # Locate the real unit and site files rather than deriving their names.
    # Guessing produced "not found" for services that have both, and — worse —
    # could just as easily have matched a file belonging to something else.
    try:
        snapshot = ServerSnapshot.fetch(server)
        unit_path = snapshot.locate_unit(svc_name, project)
        caddy_files, located_by = snapshot.locate_caddy_configs(
            svc_name, deployment.hostname, deployment.port, deployment.static_path
        )
    except Exception as e:
        return {
            "success": False,
            "error": "SNAPSHOT_FAILED",
            "message": f"Could not read state from {server} to plan the purge: {str(e)}"
        }

    plan = {
        "systemd_unit": unit_path,
        "caddy_files": caddy_files,
        "caddy_located_by": located_by,
        "port_to_release": deployment.port,
        "dns_record": deployment.hostname if remove_dns_record else None,
        "directories": [
            p for p, wanted in (
                (deployment.app_path, remove_app_files),
                (deployment.static_path, remove_static_files),
                (deployment.data_path, remove_data),
                (deployment.log_path, remove_logs),
            ) if wanted and p
        ],
    }

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "project": project,
            "service": service,
            "server": server,
            "plan": plan,
            "conflicts": conflicts,
            "message": (
                f"Dry run: would purge {project}/{service} on {server}. "
                f"Nothing was changed."
            )
        }

    try:
        # Step 1: Stop systemd service if running
        if deployment.service_type.value in ["flask", "nodejs", "flask+static"]:
            if deployment.status.value == "deployed":
                stop_result = await stop_systemd_service(
                    service_name=svc_name,
                    server=server
                )

                if stop_result["success"]:
                    steps_completed.append("systemd_service_stopped")
                else:
                    cleanup_info["systemd_stop_warning"] = stop_result.get("message")

            # Step 2: Disable and remove systemd service file
            if unit_path:
                remove_result = await remove_systemd_service(
                    service_name=unit_path.rsplit("/", 1)[-1].removesuffix(".service"),
                    server=server
                )

                if remove_result["success"]:
                    steps_completed.append("systemd_service_removed")
                    cleanup_info["systemd_service_file"] = remove_result.get("service_file")
                else:
                    cleanup_info["systemd_remove_warning"] = remove_result.get("message")
            else:
                cleanup_info["systemd_note"] = (
                    f"No systemd unit found for {project}/{service}; nothing removed"
                )

        # Step 3: Remove the Caddy site file(s) that actually serve this service
        if caddy_files:
            removed_any = False
            for caddy_file in caddy_files:
                caddy_result = await remove_caddy_config_file(
                    config_file=caddy_file,
                    server=server
                )

                if caddy_result["success"]:
                    removed_any = True
                    steps_completed.append("caddy_config_removed")
                    cleanup_info.setdefault("caddy_config_files", []).append(caddy_file)

            if removed_any:
                # Step 4: Reload Caddy
                reload_result = await reload_caddy_on_server(server)

                if reload_result["success"]:
                    steps_completed.append("caddy_reloaded")
                else:
                    cleanup_info["caddy_reload_warning"] = reload_result.get("message")
        elif deployment.hostname:
            cleanup_info["caddy_note"] = (
                f"No Caddy site found for {deployment.hostname}; nothing removed"
            )

        # Step 5: Remove DNS record (if requested)
        if remove_dns_record and deployment.hostname:
            dns_result = await remove_dns_cname_record(
                hostname=deployment.hostname,
                server=server
            )

            if dns_result["success"]:
                steps_completed.append("dns_record_removed")
                cleanup_info["dns_record"] = deployment.hostname
            else:
                cleanup_info["dns_remove_warning"] = dns_result.get("message")

        # Step 6: Release port. The conflict check above already refused if
        # another live deployment records this port, so reaching here means it
        # is genuinely this service's to give back.
        if deployment.port:
            port_result = await release_port(
                store=store,
                port=deployment.port,
                server=server
            )

            if port_result["success"]:
                steps_completed.append("port_released")
                cleanup_info["port_released"] = deployment.port
            else:
                cleanup_info["port_release_warning"] = port_result.get("message")

        # Step 7: Delete files (if requested)
        files_removed = []

        if remove_app_files and deployment.app_path:
            app_result = await remove_directory(
                path=deployment.app_path,
                server=server,
                project=project,
            )
            if app_result["success"]:
                files_removed.append(deployment.app_path)

        if remove_static_files and deployment.static_path:
            static_result = await remove_directory(
                path=deployment.static_path,
                server=server,
                project=project,
            )
            if static_result["success"]:
                files_removed.append(deployment.static_path)

        if remove_data and deployment.data_path:
            data_result = await remove_directory(
                path=deployment.data_path,
                server=server,
                project=project,
            )
            if data_result["success"]:
                files_removed.append(deployment.data_path)

        if remove_logs and deployment.log_path:
            logs_result = await remove_directory(
                path=deployment.log_path,
                server=server,
                project=project,
            )
            if logs_result["success"]:
                files_removed.append(deployment.log_path)

        if files_removed:
            steps_completed.append("files_removed")
            cleanup_info["files_removed"] = files_removed

        # Step 8: Backup configuration and update status to purged
        backup_config = {
            "deployment_id": deployment.deployment_id,
            "project": deployment.project,
            "service": deployment.service,
            "server": deployment.server,
            "service_type": deployment.service_type.value,
            "port": deployment.port,
            "hostname": deployment.hostname,
            "paths": {
                "app_path": deployment.app_path,
                "static_path": deployment.static_path,
                "data_path": deployment.data_path,
                "log_path": deployment.log_path,
                "config_path": deployment.config_path
            },
            "caddy_rules": deployment.caddy_rules,
            "environment": deployment.environment,
            "systemd_config": deployment.systemd_config,
            "notes": deployment.notes
        }

        # Use what the update returns. Re-reading with get_service_deployment()
        # cannot work here: that query excludes PURGED rows, so it returns None
        # the moment this succeeds — and every purge then died building its own
        # response, reporting PURGE_FAILED for work that had in fact completed.
        purged = await store.update_service_status(
            deployment.deployment_id,
            "purged",
            backup_config=backup_config
        )
        steps_completed.append("status_updated_to_purged")

        if purged is None:
            return {
                "success": False,
                "error": "PURGE_INCOMPLETE",
                "message": (
                    f"Server-side cleanup finished but {deployment.deployment_id} could not "
                    f"be marked purged. The record still describes a service that is gone."
                ),
                "steps_completed": steps_completed,
            }
        deployment = purged

        return {
            "success": True,
            "deployment_id": deployment.deployment_id,
            "project": deployment.project,
            "service": deployment.service,
            "server": deployment.server,
            "status": deployment.status.value,
            "purged_at": deployment.purged_at.isoformat() if deployment.purged_at else None,
            "steps_completed": steps_completed,
            "cleanup_info": cleanup_info,
            "backup_preserved": True,
            "message": f"Service {project}/{service} completely purged from {server}. Configuration backed up in database."
        }

    except Exception as e:
        return {
            "success": False,
            "error": "PURGE_FAILED",
            "message": f"Failed to purge service: {str(e)}",
            "steps_completed": steps_completed,
            "cleanup_info": cleanup_info
        }


async def _find_conflicts(store: SQLiteStore, deployment) -> List[Dict[str, Any]]:
    """
    Other live deployments on the same server that share a resource with this one.

    Records drift: a service that has been superseded often still carries the
    hostname, port and paths its successor now uses, because nobody updated the
    registry during the migration. Purging on the strength of such a record
    removes a *live* service's configuration.

    Only non-PURGED records count — a purged sibling cannot be broken further.
    """
    others = await store.list_service_deployments()
    conflicts = []

    for other in others:
        if other.deployment_id == deployment.deployment_id:
            continue
        if other.server != deployment.server:
            continue
        if other.status == DeploymentStatus.PURGED:
            continue

        shared = []
        if deployment.hostname and other.hostname == deployment.hostname:
            shared.append(f"hostname {deployment.hostname}")
        if deployment.port and other.port == deployment.port:
            shared.append(f"port {deployment.port}")
        if deployment.app_path and other.app_path == deployment.app_path:
            shared.append(f"app_path {deployment.app_path}")
        if deployment.static_path and other.static_path == deployment.static_path:
            shared.append(f"static_path {deployment.static_path}")

        if shared:
            conflicts.append({
                "project": other.project,
                "service": other.service,
                "status": other.status.value,
                "shares": shared,
            })

    return conflicts


async def stop_systemd_service(
    service_name: str,
    server: str
) -> Dict[str, Any]:
    """
    Stop systemd service on VPS server.

    Args:
        service_name: Systemd service name
        server: VPS server name

    Returns:
        Dict with success status
    """

    from main.providers.ssh_provider import async_run_command
    from main.utils import q

    try:
        result = await async_run_command(server, f"sudo systemctl stop {q(service_name)}")
        if not result["success"]:
            return {
                "success": False,
                "error": "STOP_FAILED",
                "message": f"Failed to stop {service_name}: {result.get('stderr', result.get('message'))}",
            }
        return {
            "success": True,
            "service_name": service_name,
            "message": f"Service {service_name} stopped on {server}",
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to stop service: {str(e)}"
        }


async def remove_systemd_service(
    service_name: str,
    server: str
) -> Dict[str, Any]:
    """
    Disable and remove systemd service file from VPS server.

    Args:
        service_name: Systemd service name
        server: VPS server name

    Returns:
        Dict with success status
    """

    from main.providers.ssh_provider import async_run_command
    from main.utils import q

    try:
        service_file = f"/etc/systemd/system/{service_name}.service"
        cmd = (
            f"sudo systemctl disable {q(service_name)} ; "
            f"sudo rm -f {q(service_file)} && "
            f"sudo systemctl daemon-reload"
        )
        result = await async_run_command(server, cmd)
        if not result["success"]:
            return {
                "success": False,
                "error": "REMOVE_FAILED",
                "message": f"Failed to remove {service_name}: {result.get('stderr', result.get('message'))}",
            }
        return {
            "success": True,
            "service_name": service_name,
            "service_file": service_file,
            "message": f"Systemd service {service_name} disabled and removed from {server}",
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to remove systemd service: {str(e)}"
        }


async def remove_caddy_config_file(
    config_file: str,
    server: str
) -> Dict[str, Any]:
    """
    Remove Caddy configuration file from VPS server.

    Args:
        config_file: Path to Caddy config file
        server: VPS server name

    Returns:
        Dict with success status
    """

    from main.providers.ssh_provider import async_run_command
    from main.utils import q

    try:
        result = await async_run_command(server, f"sudo rm -f {q(config_file)}")
        if not result["success"]:
            return {
                "success": False,
                "error": "REMOVE_FAILED",
                "message": f"Failed to remove {config_file}: {result.get('stderr', result.get('message'))}",
            }
        return {
            "success": True,
            "config_file": config_file,
            "message": f"Caddy config file removed: {config_file}",
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to remove Caddy config: {str(e)}"
        }


async def reload_caddy_on_server(server: str) -> Dict[str, Any]:
    """
    Reload Caddy on VPS server.

    Args:
        server: VPS server name

    Returns:
        Dict with success status
    """

    from main.providers.ssh_provider import async_run_command

    try:
        result = await async_run_command(server, "sudo systemctl reload caddy")
        if not result["success"]:
            return {
                "success": False,
                "error": "RELOAD_FAILED",
                "message": f"Failed to reload Caddy: {result.get('stderr', result.get('message'))}",
            }
        return {
            "success": True,
            "message": f"Caddy reloaded on {server}",
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to reload Caddy: {str(e)}"
        }


async def remove_dns_cname_record(
    hostname: str,
    server: str
) -> Dict[str, Any]:
    """
    Remove public hostname from remotely-managed tunnel and its DNS CNAME.

    Args:
        hostname: Hostname to remove
        server: VPS server name (used to derive tunnel name {server}-main)

    Returns:
        Dict with success status
    """
    from main.tools.cloudflare.tunnel import remove_public_hostname

    try:
        return await remove_public_hostname(
            hostname=hostname,
            tunnel_name=f"{server}-main",
            delete_dns=True,
        )
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to remove public hostname: {str(e)}"
        }


async def remove_directory(
    path: str,
    server: str,
    project: str = "",
) -> Dict[str, Any]:
    """
    Remove directory on VPS server.

    Args:
        path: Directory path to remove
        server: VPS server name
        project: Project name (used to validate path scope)

    Returns:
        Dict with success status
    """

    from main.providers.ssh_provider import async_run_command
    from main.utils import q

    # Validate path is project-scoped before deletion
    try:
        validate_project_path(path, project, "path")
    except ValueError as e:
        return {
            "success": False,
            "error": "INVALID_PATH",
            "message": str(e),
        }

    try:
        result = await async_run_command(server, f"rm -rf {q(path)}")
        if not result["success"]:
            return {
                "success": False,
                "error": "REMOVE_FAILED",
                "message": f"Failed to remove {path}: {result.get('stderr', result.get('message'))}",
            }
        return {
            "success": True,
            "path": path,
            "message": f"Directory removed: {path}",
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to remove directory: {str(e)}"
        }


async def validate_purge_service_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for purge_service tool.

    Args:
        data: Input data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    required_fields = ["project", "service", "server"]
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"

    # Validate types
    if not isinstance(data["project"], str):
        return False, "Field 'project' must be a string"

    if not isinstance(data["service"], str):
        return False, "Field 'service' must be a string"

    if not isinstance(data["server"], str):
        return False, "Field 'server' must be a string"

    # Validate optional boolean fields
    bool_fields = [
        "remove_app_files", "remove_static_files", "remove_data", "remove_logs",
        "remove_dns_record", "dry_run", "force"
    ]
    for field in bool_fields:
        if field in data and data[field] is not None:
            if not isinstance(data[field], bool):
                return False, f"Field '{field}' must be a boolean"

    return True, None
