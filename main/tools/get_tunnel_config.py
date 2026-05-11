"""
get_tunnel_config MCP Tool Implementation

Get Cloudflare Tunnel configuration for a VPS server.
"""

import subprocess
from typing import Optional, Dict, Any

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore
from main.providers.ssh_provider import run_command


async def get_tunnel_config(
    store: SQLiteStore,
    server: str
) -> Dict[str, Any]:
    """
    Get Cloudflare Tunnel configuration.

    Args:
        store: SQLiteStore instance
        server: VPS server name

    Returns:
        Dict with tunnel configuration content
    """

    # Validate server
    valid_servers = INFRA_SERVERS
    if server not in valid_servers:
        return {
            "success": False,
            "error": "INVALID_SERVER",
            "message": f"Invalid server name. Must be one of: {', '.join(valid_servers)}"
        }

    # Read tunnel config file
    config_file = "~/.cloudflared/config.yml"

    try:
        result = run_command(server, f"cat {config_file} 2>/dev/null", timeout=10)

        if result.returncode != 0:
            return {
                "success": False,
                "error": "CONFIG_NOT_FOUND",
                "message": f"Tunnel config file not found: {config_file}",
                "server": server
            }

        content = result.stdout

        # Parse YAML content (simple parsing)
        tunnel_id = None
        credentials_file = None
        ingress_rules = []

        in_ingress = False
        for line in content.split('\n'):
            line_stripped = line.strip()

            if line_stripped.startswith('tunnel:'):
                tunnel_id = line_stripped.split(':', 1)[1].strip()
            elif line_stripped.startswith('credentials-file:'):
                credentials_file = line_stripped.split(':', 1)[1].strip()
            elif line_stripped == 'ingress:':
                in_ingress = True
            elif in_ingress and line_stripped.startswith('- '):
                # Parse ingress rule
                ingress_rules.append(line_stripped[2:])

        return {
            "success": True,
            "server": server,
            "config_file": config_file,
            "content": content,
            "tunnel_id": tunnel_id,
            "credentials_file": credentials_file,
            "ingress_rules": ingress_rules,
            "ingress_count": len(ingress_rules),
            "message": f"Retrieved tunnel config from {server}"
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "READ_TIMEOUT",
            "message": f"Timeout reading tunnel config from {server}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "UNEXPECTED_ERROR",
            "message": f"Failed to read tunnel config: {str(e)}"
        }


async def validate_get_tunnel_config_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for get_tunnel_config tool.

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

    return True, None
