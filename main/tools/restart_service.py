"""
restart_service MCP Tool Implementation

Restart a deployed service (systemd service, Docker container, or Caddy).
"""

import subprocess
from typing import Optional, Dict, Any

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore
from main.models.service_deployment import ServiceType
from main.providers.ssh_provider import run_command
from main.utils import get_service_name


async def restart_service(
    store: SQLiteStore,
    project: str,
    service: str,
    server: str,
    component: str = "service"
) -> Dict[str, Any]:
    """
    Restart a deployed service component.

    Args:
        store: SQLiteStore instance
        project: Project name
        service: Service name
        server: VPS server name
        component: Component to restart ('service', 'caddy', 'tunnel')

    Returns:
        Dict with restart result
    """

    # Validate component
    valid_components = ["service", "caddy", "tunnel"]
    if component not in valid_components:
        return {
            "success": False,
            "error": "INVALID_COMPONENT",
            "message": f"Invalid component. Must be one of: {', '.join(valid_components)}"
        }

    # Get deployment
    deployment = await store.get_service_deployment(project, service, server)
    if not deployment:
        return {
            "success": False,
            "error": "SERVICE_NOT_FOUND",
            "message": f"Service {project}/{service} not found on {server}"
        }

    try:
        if component == "service":
            svc_name = get_service_name(project, service, deployment.systemd_config)
            result = await _restart_main_service(server, project, service, deployment.service_type, svc_name)
        elif component == "caddy":
            result = await _restart_caddy(server)
        elif component == "tunnel":
            result = await _restart_tunnel(server)

        return result

    except Exception as e:
        return {
            "success": False,
            "error": "RESTART_FAILED",
            "message": f"Failed to restart {component}: {str(e)}"
        }


async def _restart_main_service(
    server: str,
    project: str,
    service: str,
    service_type: ServiceType,
    service_name: str = None
) -> Dict[str, Any]:
    """Restart the main service (systemd or Docker)."""

    if not service_name:
        service_name = f"{project}-{service}"

    if service_type == ServiceType.DOCKER:

        try:
            result = run_command(
                server, f"cd ~/PRJ/{project} && docker compose restart", timeout=60
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": "DOCKER_RESTART_FAILED",
                    "message": f"Failed to restart Docker containers: {result.stderr}",
                    "details": result.stderr
                }

            return {
                "success": True,
                "component": "service",
                "service_type": "docker",
                "message": f"✅ Successfully restarted Docker containers for {project}/{service}",
                "output": result.stdout
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "RESTART_TIMEOUT",
                "message": "Docker restart command timed out (60s)"
            }

    else:
        # Restart systemd service
        try:
            result = run_command(
                server,
                f"sudo systemctl restart {service_name} && sudo systemctl status {service_name} --no-pager -l",
                timeout=30
            )

            # systemctl restart returns 0 even if service fails to start
            # Check status in output
            if "active (running)" in result.stdout:
                return {
                    "success": True,
                    "component": "service",
                    "service_type": "systemd",
                    "service_name": service_name,
                    "message": f"✅ Successfully restarted systemd service {service_name}",
                    "status": result.stdout.split('\n')[2:7]  # Get relevant status lines
                }
            else:
                return {
                    "success": False,
                    "error": "SERVICE_NOT_RUNNING",
                    "message": f"Service {service_name} restarted but not running",
                    "details": result.stdout
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "RESTART_TIMEOUT",
                "message": "Systemd restart command timed out (30s)"
            }


async def _restart_caddy(server: str) -> Dict[str, Any]:
    """Restart Caddy web server."""

    try:
        result = run_command(
            server,
            "sudo systemctl restart caddy && sudo systemctl status caddy --no-pager -l | head -10",
            timeout=30
        )

        if "active (running)" in result.stdout:
            return {
                "success": True,
                "component": "caddy",
                "message": "✅ Successfully restarted Caddy web server",
                "status": result.stdout.split('\n')[2:7]
            }
        else:
            return {
                "success": False,
                "error": "CADDY_NOT_RUNNING",
                "message": "Caddy restarted but not running",
                "details": result.stdout
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "RESTART_TIMEOUT",
            "message": "Caddy restart command timed out (30s)"
        }


async def _restart_tunnel(server: str) -> Dict[str, Any]:
    """Restart Cloudflare Tunnel."""

    # Find tunnel service name
    try:
        result = run_command(
            server,
            "systemctl list-units | grep cloudflared | awk '{print $1}'",
            timeout=10
        )

        if result.returncode != 0 or not result.stdout.strip():
            return {
                "success": False,
                "error": "TUNNEL_SERVICE_NOT_FOUND",
                "message": "Cloudflare Tunnel service not found"
            }

        tunnel_service = result.stdout.strip()

        # Restart tunnel
        restart_result = run_command(
            server,
            f"sudo systemctl restart {tunnel_service} && sudo systemctl status {tunnel_service} --no-pager -l | head -10",
            timeout=30
        )

        if "active (running)" in restart_result.stdout:
            return {
                "success": True,
                "component": "tunnel",
                "service_name": tunnel_service,
                "message": f"✅ Successfully restarted Cloudflare Tunnel ({tunnel_service})",
                "status": restart_result.stdout.split('\n')[2:7]
            }
        else:
            return {
                "success": False,
                "error": "TUNNEL_NOT_RUNNING",
                "message": f"Tunnel {tunnel_service} restarted but not running",
                "details": restart_result.stdout
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "RESTART_TIMEOUT",
            "message": "Tunnel restart command timed out"
        }


async def validate_restart_service_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for restart_service tool.

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

    valid_servers = INFRA_SERVERS
    if data["server"] not in valid_servers:
        return False, f"Invalid server. Must be one of: {', '.join(valid_servers)}"

    if "component" in data:
        if not isinstance(data["component"], str):
            return False, "Field 'component' must be a string"

        valid_components = ["service", "caddy", "tunnel"]
        if data["component"] not in valid_components:
            return False, f"Invalid component. Must be one of: {', '.join(valid_components)}"

    return True, None
