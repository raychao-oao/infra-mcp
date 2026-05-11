"""
get_caddy_config MCP Tool Implementation

Get Caddy configuration for a specific service or the main Caddyfile.
"""

import subprocess
from typing import Optional, Dict, Any

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore
from main.providers.ssh_provider import run_command
from main.utils import get_service_name, q


async def get_caddy_config(
    store: SQLiteStore,
    server: str,
    project: Optional[str] = None,
    service: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get Caddy configuration file content.

    Args:
        store: SQLiteStore instance
        server: VPS server name
        project: Optional project name (for service-specific config)
        service: Optional service name (for service-specific config)

    Returns:
        Dict with Caddy configuration content
    """

    # Validate server
    valid_servers = INFRA_SERVERS
    if server not in valid_servers:
        return {
            "success": False,
            "error": "INVALID_SERVER",
            "message": f"Invalid server name. Must be one of: {', '.join(valid_servers)}"
        }

    # Determine config file path
    if project and service:
        deployment = await store.get_service_deployment(project, service, server)
        systemd_config = deployment.systemd_config if deployment else None
        svc_name = get_service_name(project, service, systemd_config)
        config_file = f"/etc/caddy/sites/{svc_name}.caddy"
        config_type = "service"
    else:
        config_file = "/etc/caddy/Caddyfile"
        config_type = "main"

    # Read config file
    try:
        result = run_command(server, f"sudo cat {q(config_file)} 2>/dev/null", timeout=10)

        if result.returncode != 0:
            return {
                "success": False,
                "error": "CONFIG_NOT_FOUND",
                "message": f"Config file not found: {config_file}",
                "config_file": config_file
            }

        # Parse config content
        content = result.stdout
        lines = content.split('\n')

        # Extract key info
        has_bind = "bind 127.0.0.1" in content
        has_https = "https://" in content or "tls" in content

        # Count server blocks
        server_blocks = content.count('{')

        return {
            "success": True,
            "server": server,
            "config_type": config_type,
            "config_file": config_file,
            "content": content,
            "lines": len(lines),
            "server_blocks": server_blocks,
            "has_bind_localhost": has_bind,
            "has_https": has_https,
            "message": f"Retrieved {config_type} Caddy config from {server}"
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "READ_TIMEOUT",
            "message": f"Timeout reading config from {server}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "UNEXPECTED_ERROR",
            "message": f"Failed to read config: {str(e)}"
        }


async def validate_get_caddy_config_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for get_caddy_config tool.

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

    return True, None
