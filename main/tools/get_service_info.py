"""
get_service_info MCP Tool Implementation

Query detailed information about a deployed service, including:
- Connection URL
- Directory structure
- Port allocation
- Caddy configuration
- Systemd service
- Status
"""

from typing import Optional, Dict, Any

from main.db.sqlite_store import SQLiteStore
from main.providers.ssh_provider import run_command
from main.utils import get_service_name, q


async def get_service_info(
    store: SQLiteStore,
    project: str,
    service: str,
    server: str
) -> Dict[str, Any]:
    """
    Get detailed information about a service deployment.

    Args:
        store: SQLiteStore instance
        project: Project name
        service: Service name
        server: VPS server name

    Returns:
        Dict with service details including connection info and directory structure
    """

    # Get deployment
    deployment = await store.get_service_deployment(project, service, server)
    if not deployment:
        return {
            "success": False,
            "error": "SERVICE_NOT_FOUND",
            "message": f"Service {project}/{service} not found on {server}"
        }

    service_type = deployment.service_type.value
    status = deployment.status.value

    # Build connection info
    connection = {}
    if deployment.hostname:
        connection["url"] = f"https://{deployment.hostname}"
        connection["hostname"] = deployment.hostname

    if deployment.port:
        connection["port"] = deployment.port
        connection["internal_url"] = f"http://localhost:{deployment.port}"

    # Build directory structure
    directories = {
        "static_files": deployment.static_path,
        "symlink": f"~/PRJ/{project}/www/ -> {deployment.static_path}" if deployment.static_path else None,
    }

    if service_type != "static":
        directories["app_code"] = deployment.app_path

    directories["data"] = deployment.data_path
    directories["logs"] = deployment.log_path
    directories["config"] = deployment.config_path

    # Resolve actual service name
    svc_name = get_service_name(project, service, deployment.systemd_config)

    # Build Caddy info
    caddy = {
        "config_file": f"/etc/caddy/sites/{svc_name}.caddy",
    }

    if deployment.caddy_rules:
        caddy["custom_rules"] = deployment.caddy_rules

    # Build systemd info (for non-static services)
    systemd = None
    if service_type in ["flask", "nodejs", "flask+static"]:
        systemd = {
            "service_name": svc_name,
            "service_file": f"/etc/systemd/system/{svc_name}.service",
            "commands": {
                "status": f"sudo systemctl status {svc_name}",
                "start": f"sudo systemctl start {svc_name}",
                "stop": f"sudo systemctl stop {svc_name}",
                "restart": f"sudo systemctl restart {svc_name}",
                "logs": f"sudo journalctl -u {svc_name} -f",
            }
        }

    # Check live runtime status
    live_status = "unknown"
    if service_type in ["flask", "nodejs", "flask+static"]:
        service_name = svc_name
        try:
            result = run_command(server, f"systemctl is-active {q(service_name)}", timeout=5)
            live_status = result.stdout.strip()  # "active", "inactive", "failed", etc.
        except Exception:
            live_status = "check_failed"
    elif service_type == "docker":
        try:
            result = run_command(server, f"cd ~/PRJ/{q(project)} && docker compose ps --format json", timeout=5)
            live_status = "running" if "running" in result.stdout.lower() else "stopped"
        except Exception:
            live_status = "check_failed"
    elif service_type == "static":
        live_status = "static"  # Static sites are always "up" if Caddy is running

    # Build environment info
    environment = deployment.environment if deployment.environment else {}

    return {
        "success": True,
        "deployment_id": deployment.deployment_id,
        "project": project,
        "service": service,
        "server": server,
        "service_type": service_type,
        "status": status,
        "live_status": live_status,
        "connection": connection,
        "directories": directories,
        "caddy": caddy,
        "systemd": systemd,
        "environment": environment,
        "timestamps": {
            "registered_at": deployment.registered_at.isoformat() if deployment.registered_at else None,
            "deployed_at": deployment.deployed_at.isoformat() if deployment.deployed_at else None,
            "stopped_at": deployment.stopped_at.isoformat() if deployment.stopped_at else None,
        },
        "notes": deployment.notes,
        "message": f"Service info retrieved for {project}/{service} on {server}"
    }


async def validate_get_service_info_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for get_service_info tool.

    Args:
        data: Input data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    required_fields = ["project", "service", "server"]
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
        if not isinstance(data[field], str):
            return False, f"Field '{field}' must be a string"

    return True, None
