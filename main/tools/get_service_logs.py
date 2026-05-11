"""
get_service_logs MCP Tool Implementation

Get logs from various service components (systemd, Docker, Caddy, Tunnel).
"""

import subprocess
from typing import Optional, Dict, Any

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore
from main.models.service_deployment import ServiceType
from main.providers.ssh_provider import run_command
from main.utils import get_service_name, q


async def get_service_logs(
    store: SQLiteStore,
    server: str,
    project: Optional[str] = None,
    service: Optional[str] = None,
    component: str = "service",
    lines: int = 50,
    since: Optional[str] = None,
    follow: bool = False
) -> Dict[str, Any]:
    """
    Get service logs.

    Args:
        store: SQLiteStore instance
        server: VPS server name
        project: Optional project name (required for service component)
        service: Optional service name (required for service component)
        component: Component to get logs from ('service', 'caddy', 'tunnel')
        lines: Number of lines to retrieve (default: 50)
        since: Optional time filter (e.g. '1 hour ago', '2026-02-11 15:00', '30 min ago')
        follow: Whether to follow logs (not supported via MCP)

    Returns:
        Dict with log content
    """

    # Validate server
    valid_servers = INFRA_SERVERS
    if server not in valid_servers:
        return {
            "success": False,
            "error": "INVALID_SERVER",
            "message": f"Invalid server name. Must be one of: {', '.join(valid_servers)}"
        }

    # Validate component
    valid_components = ["service", "caddy", "tunnel"]
    if component not in valid_components:
        return {
            "success": False,
            "error": "INVALID_COMPONENT",
            "message": f"Invalid component. Must be one of: {', '.join(valid_components)}"
        }

    # Validate project/service requirements
    if component == "service":
        if not project or not service:
            return {
                "success": False,
                "error": "MISSING_SERVICE_INFO",
                "message": "project and service are required for 'service' component"
            }

    try:
        if component == "service":
            result = await _get_service_logs(store, server, project, service, lines, since)
        elif component == "caddy":
            result = await _get_caddy_logs(server, lines, since)
        elif component == "tunnel":
            result = await _get_tunnel_logs(server, lines, since)

        return result

    except Exception as e:
        return {
            "success": False,
            "error": "LOG_READ_FAILED",
            "message": f"Failed to read logs: {str(e)}"
        }


async def _get_service_logs(
    store: SQLiteStore,
    server: str,
    project: str,
    service: str,
    lines: int,
    since: Optional[str] = None
) -> Dict[str, Any]:
    """Get logs from a deployed service."""

    # Get deployment to determine service type
    deployment = await store.get_service_deployment(project, service, server)
    if not deployment:
        return {
            "success": False,
            "error": "SERVICE_NOT_FOUND",
            "message": f"Service {project}/{service} not found on {server}"
        }

    service_type = deployment.service_type

    if service_type == ServiceType.DOCKER:
        # Get Docker logs
        cmd = f"cd ~/PRJ/{q(project)} && docker compose logs --tail {int(lines)}"
        if since:
            cmd += f" --since {q(since)}"
    else:
        # Get systemd logs
        service_name = get_service_name(project, service, deployment.systemd_config)
        cmd = f"sudo journalctl -u {q(service_name)} -n {int(lines)} --no-pager"
        if since:
            cmd += f" --since {q(since)}"

    try:
        result = run_command(server, cmd, timeout=30)

        if result.returncode != 0:
            return {
                "success": False,
                "error": "LOG_READ_FAILED",
                "message": f"Failed to read service logs: {result.stderr}",
                "stderr": result.stderr
            }

        log_lines = result.stdout.split('\n')

        return {
            "success": True,
            "server": server,
            "component": "service",
            "project": project,
            "service": service,
            "service_type": service_type.value,
            "lines_requested": lines,
            "lines_returned": len(log_lines),
            "logs": result.stdout,
            "message": f"Retrieved {len(log_lines)} log lines from {project}/{service}"
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "LOG_READ_TIMEOUT",
            "message": "Timeout reading service logs (30s)"
        }


async def _get_caddy_logs(server: str, lines: int, since: Optional[str] = None) -> Dict[str, Any]:
    """Get Caddy access logs."""

    if since:
        # When filtering by time, use journalctl (supports --since)
        cmd = f"sudo journalctl -u caddy -n {int(lines)} --no-pager --since {q(since)}"
    else:
        # Try to read Caddy access log, fallback to journalctl
        log_file = "/var/log/caddy/access.log"
        cmd = f"sudo tail -n {int(lines)} {q(log_file)} 2>/dev/null || sudo journalctl -u caddy -n {int(lines)} --no-pager"

    try:
        result = run_command(server, cmd, timeout=30)

        if result.returncode != 0:
            return {
                "success": False,
                "error": "LOG_READ_FAILED",
                "message": f"Failed to read Caddy logs: {result.stderr}",
                "stderr": result.stderr
            }

        log_lines = result.stdout.split('\n')

        return {
            "success": True,
            "server": server,
            "component": "caddy",
            "lines_requested": lines,
            "lines_returned": len(log_lines),
            "logs": result.stdout,
            "message": f"Retrieved {len(log_lines)} Caddy log lines"
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "LOG_READ_TIMEOUT",
            "message": "Timeout reading Caddy logs (30s)"
        }


async def _get_tunnel_logs(server: str, lines: int, since: Optional[str] = None) -> Dict[str, Any]:
    """Get Cloudflare Tunnel logs."""

    # Find tunnel service name - use systemctl list-unit-files to avoid "loaded" status text
    cmd = "systemctl list-unit-files | grep cloudflared | awk '{print $1}' | head -1"

    try:
        result = run_command(server, cmd, timeout=10)

        if result.returncode != 0 or not result.stdout.strip():
            return {
                "success": False,
                "error": "TUNNEL_SERVICE_NOT_FOUND",
                "message": "Cloudflare Tunnel service not found"
            }

        tunnel_service = result.stdout.strip().split('\n')[0].strip()

        # Get tunnel logs
        tunnel_cmd = f"sudo journalctl -u {q(tunnel_service)} -n {int(lines)} --no-pager"
        if since:
            tunnel_cmd += f" --since {q(since)}"
        log_result = run_command(server, tunnel_cmd, timeout=30)

        if log_result.returncode != 0:
            return {
                "success": False,
                "error": "LOG_READ_FAILED",
                "message": f"Failed to read tunnel logs: {log_result.stderr}",
                "stderr": log_result.stderr
            }

        log_lines = log_result.stdout.split('\n')

        return {
            "success": True,
            "server": server,
            "component": "tunnel",
            "service_name": tunnel_service,
            "lines_requested": lines,
            "lines_returned": len(log_lines),
            "logs": log_result.stdout,
            "message": f"Retrieved {len(log_lines)} tunnel log lines"
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "LOG_READ_TIMEOUT",
            "message": "Timeout reading tunnel logs"
        }


async def validate_get_service_logs_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for get_service_logs tool.

    Args:
        data: Input data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    if "server" not in data:
        return False, "Missing required field: server"

    if not isinstance(data["server"], str):
        return False, "Field 'server' must be a string"

    valid_servers = INFRA_SERVERS
    if data["server"] not in valid_servers:
        return False, f"Invalid server. Must be one of: {', '.join(valid_servers)}"

    if "component" in data:
        if not isinstance(data["component"], str):
            return False, "Field 'component' must be a string"

        valid_components = ["service", "caddy", "tunnel"]
        if data["component"] not in valid_components:
            return False, f"Invalid component. Must be one of: {', '.join(valid_components)}"

        # If component is 'service', project and service are required
        if data["component"] == "service":
            if "project" not in data or "service" not in data:
                return False, "Fields 'project' and 'service' are required when component is 'service'"

    if "lines" in data:
        if not isinstance(data["lines"], int):
            return False, "Field 'lines' must be an integer"
        if data["lines"] < 1 or data["lines"] > 1000:
            return False, "Field 'lines' must be between 1 and 1000"

    if "since" in data:
        if not isinstance(data["since"], str):
            return False, "Field 'since' must be a string"
        if len(data["since"]) > 100:
            return False, "Field 'since' is too long (max 100 characters)"

    if "project" in data and not isinstance(data["project"], str):
        return False, "Field 'project' must be a string"

    if "service" in data and not isinstance(data["service"], str):
        return False, "Field 'service' must be a string"

    return True, None
