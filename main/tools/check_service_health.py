"""
check_service_health MCP Tool Implementation

Check health status of services and system resources.
"""

import subprocess
import re
from typing import Optional, Dict, Any

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore
from main.models.service_deployment import ServiceType
from main.providers.ssh_provider import run_command
from main.utils import get_service_name


async def check_service_health(
    store: SQLiteStore,
    server: str,
    project: Optional[str] = None,
    service: Optional[str] = None,
    include_system_stats: bool = False
) -> Dict[str, Any]:
    """
    Check service health status and optionally system statistics.

    Args:
        store: SQLiteStore instance
        server: VPS server name
        project: Optional project name (if checking specific service)
        service: Optional service name (if checking specific service)
        include_system_stats: Whether to include system resource statistics

    Returns:
        Dict with health status information
    """

    # Validate server
    valid_servers = INFRA_SERVERS
    if server not in valid_servers:
        return {
            "success": False,
            "error": "INVALID_SERVER",
            "message": f"Invalid server name. Must be one of: {', '.join(valid_servers)}"
        }

    result = {
        "success": True,
        "server": server
    }

    try:
        # Check specific service if provided
        if project and service:
            service_health = await _check_specific_service(store, server, project, service)
            result["service_health"] = service_health

        # Check core infrastructure
        infra_health = await _check_infrastructure(server)
        result["infrastructure"] = infra_health

        # Get system stats if requested
        if include_system_stats:
            system_stats = await _get_system_stats(server)
            result["system_stats"] = system_stats

        # Determine overall health
        all_healthy = True
        if "service_health" in result:
            all_healthy = all_healthy and result["service_health"]["healthy"]
        all_healthy = all_healthy and infra_health["caddy"]["healthy"] and infra_health["tunnel"]["healthy"]

        result["overall_health"] = "healthy" if all_healthy else "unhealthy"
        result["message"] = f"Health check completed for {server}"

        return result

    except Exception as e:
        return {
            "success": False,
            "error": "HEALTH_CHECK_FAILED",
            "message": f"Failed to check health: {str(e)}"
        }


async def _check_specific_service(
    store: SQLiteStore,
    server: str,
    project: str,
    service: str
) -> Dict[str, Any]:
    """Check health of a specific service."""

    # Get deployment
    deployment = await store.get_service_deployment(project, service, server)
    if not deployment:
        return {
            "healthy": False,
            "error": "SERVICE_NOT_FOUND",
            "message": f"Service {project}/{service} not found"
        }

    service_type = deployment.service_type

    if service_type == ServiceType.DOCKER:
        # Check Docker container status
        cmd = f"cd ~/PRJ/{project} && docker compose ps --format json"
    else:
        # Check systemd service status
        service_name = get_service_name(project, service, deployment.systemd_config)
        cmd = f"systemctl is-active {service_name}"

    try:
        result = run_command(server, cmd, timeout=10)

        if service_type == ServiceType.DOCKER:
            # Docker: check if containers are running
            healthy = "running" in result.stdout.lower()
        else:
            # Systemd: check if service is active
            healthy = "active" in result.stdout

        return {
            "healthy": healthy,
            "project": project,
            "service": service,
            "service_type": service_type.value,
            "status": result.stdout.strip(),
            "message": f"Service is {'healthy' if healthy else 'unhealthy'}"
        }

    except subprocess.TimeoutExpired:
        return {
            "healthy": False,
            "error": "CHECK_TIMEOUT",
            "message": "Health check timed out"
        }


async def _check_infrastructure(server: str) -> Dict[str, Any]:
    """Check core infrastructure components (Caddy, Tunnel)."""

    infra = {}

    # Check Caddy
    try:
        caddy_result = run_command(server, "systemctl is-active caddy", timeout=10)
        caddy_healthy = "active" in caddy_result.stdout

        infra["caddy"] = {
            "healthy": caddy_healthy,
            "status": caddy_result.stdout.strip()
        }
    except Exception:
        infra["caddy"] = {
            "healthy": False,
            "error": "CHECK_FAILED"
        }

    # Check Tunnel
    try:
        tunnel_result = run_command(
            server,
            "systemctl list-units | grep cloudflared | awk '{print $1}'",
            timeout=10
        )

        if tunnel_result.stdout.strip():
            tunnel_service = tunnel_result.stdout.strip()
            status_result = run_command(
                server, f"systemctl is-active {tunnel_service}", timeout=10
            )
            tunnel_healthy = "active" in status_result.stdout

            infra["tunnel"] = {
                "healthy": tunnel_healthy,
                "service_name": tunnel_service,
                "status": status_result.stdout.strip()
            }
        else:
            infra["tunnel"] = {
                "healthy": False,
                "error": "SERVICE_NOT_FOUND"
            }
    except Exception:
        infra["tunnel"] = {
            "healthy": False,
            "error": "CHECK_FAILED"
        }

    return infra


async def _get_system_stats(server: str) -> Dict[str, Any]:
    """Get system resource statistics."""

    stats = {}

    # Get CPU, Memory, Disk usage
    try:
        result = run_command(server, "free -m && df -h / && uptime", timeout=10)

        if result.returncode != 0:
            return {
                "error": "STATS_UNAVAILABLE",
                "message": "Failed to get system stats"
            }

        output = result.stdout

        # Parse memory info
        mem_lines = [l for l in output.split('\n') if 'Mem:' in l]
        if mem_lines:
            mem_parts = mem_lines[0].split()
            if len(mem_parts) >= 3:
                total_mem = int(mem_parts[1])
                used_mem = int(mem_parts[2])
                stats["memory"] = {
                    "total_mb": total_mem,
                    "used_mb": used_mem,
                    "usage_percent": round((used_mem / total_mem) * 100, 1) if total_mem > 0 else 0
                }

        # Parse disk info
        disk_lines = [l for l in output.split('\n') if l.startswith('/dev/')]
        if disk_lines:
            disk_parts = disk_lines[0].split()
            if len(disk_parts) >= 5:
                stats["disk"] = {
                    "total": disk_parts[1],
                    "used": disk_parts[2],
                    "available": disk_parts[3],
                    "usage_percent": disk_parts[4]
                }

        # Parse uptime
        uptime_lines = [l for l in output.split('\n') if 'load average' in l]
        if uptime_lines:
            stats["uptime"] = uptime_lines[0].strip()

        return stats

    except subprocess.TimeoutExpired:
        return {
            "error": "STATS_TIMEOUT",
            "message": "Timeout getting system stats"
        }


async def validate_check_service_health_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for check_service_health tool.

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

    if "project" in data:
        if not isinstance(data["project"], str):
            return False, "Field 'project' must be a string"

    if "service" in data:
        if not isinstance(data["service"], str):
            return False, "Field 'service' must be a string"

    # If project is provided, service must also be provided
    if ("project" in data) != ("service" in data):
        return False, "Both 'project' and 'service' must be provided together"

    if "include_system_stats" in data:
        if not isinstance(data["include_system_stats"], bool):
            return False, "Field 'include_system_stats' must be a boolean"

    return True, None
