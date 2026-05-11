"""
register_main_tunnel MCP Tool Implementation

Register an actual Cloudflare Tunnel (one per VPS).
This is for tracking purposes - the tunnel should already be created
via cloudflared CLI.
"""

from datetime import datetime
from typing import Optional, Dict, Any

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore


# Valid VPS servers
VPS_SERVERS = INFRA_SERVERS


async def register_main_tunnel(
    store: SQLiteStore,
    tunnel_name: str,
    cloudflare_tunnel_id: str,
    vps_server: str,
    tunnel_target: Optional[str] = None,
    credentials_file: Optional[str] = None,
    config_file: Optional[str] = None,
    systemd_service: Optional[str] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Register a main tunnel (actual Cloudflare Tunnel).

    Each VPS should have exactly one main tunnel.
    This is for tracking purposes - the tunnel should already exist.

    Args:
        store: SQLiteStore instance
        tunnel_name: Tunnel name (e.g., "prod-main")
        cloudflare_tunnel_id: Cloudflare Tunnel UUID
        vps_server: VPS server name (configured via INFRA_SERVERS)
        tunnel_target: Tunnel target domain (optional)
        credentials_file: Path to credentials file (optional)
        config_file: Path to config file (optional)
        systemd_service: Systemd service name (optional)
        notes: Optional notes

    Returns:
        Dict with success status and tunnel details
    """

    # Validate VPS server
    if vps_server not in VPS_SERVERS:
        return {
            "success": False,
            "error": "INVALID_VPS_SERVER",
            "message": f"VPS server must be one of: {VPS_SERVERS}"
        }

    # Check if VPS already has a main tunnel
    existing = await store.get_main_tunnel_by_vps(vps_server)
    if existing:
        return {
            "success": False,
            "error": "VPS_ALREADY_HAS_TUNNEL",
            "message": f"VPS {vps_server} already has main tunnel: {existing.tunnel_name}",
            "existing_tunnel": existing.to_dict()
        }

    # Check if tunnel name already exists
    existing_name = await store.get_main_tunnel(tunnel_name)
    if existing_name:
        return {
            "success": False,
            "error": "TUNNEL_NAME_EXISTS",
            "message": f"Tunnel name '{tunnel_name}' already exists"
        }

    # Generate tunnel target if not provided
    if not tunnel_target:
        tunnel_target = f"{cloudflare_tunnel_id}.cfargotunnel.com"

    # Generate default paths if not provided
    if not credentials_file:
        credentials_file = f"~/.cloudflared/{cloudflare_tunnel_id}.json"
    if not config_file:
        config_file = "~/.cloudflared/config.yml"

    try:
        tunnel = await store.register_main_tunnel(
            tunnel_name=tunnel_name,
            cloudflare_tunnel_id=cloudflare_tunnel_id,
            vps_server=vps_server,
            tunnel_target=tunnel_target,
            credentials_file=credentials_file,
            config_file=config_file,
            systemd_service=systemd_service,
            notes=notes
        )

        return {
            "success": True,
            "tunnel_name": tunnel.tunnel_name,
            "cloudflare_tunnel_id": tunnel.cloudflare_tunnel_id,
            "vps_server": tunnel.vps_server,
            "tunnel_target": tunnel.tunnel_target,
            "credentials_file": tunnel.credentials_file,
            "config_file": tunnel.config_file,
            "systemd_service": tunnel.systemd_service,
            "status": tunnel.status.value,
            "created_at": tunnel.created_at.isoformat(),
            "message": f"Main tunnel '{tunnel_name}' registered for {vps_server}"
        }

    except Exception as e:
        return {
            "success": False,
            "error": "REGISTRATION_FAILED",
            "message": f"Failed to register main tunnel: {str(e)}"
        }


async def validate_register_main_tunnel_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Validate input parameters."""
    required_fields = ["tunnel_name", "cloudflare_tunnel_id", "vps_server"]
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
        if not isinstance(data[field], str):
            return False, f"Field '{field}' must be a string"

    # Validate VPS server
    if data["vps_server"] not in VPS_SERVERS:
        return False, f"VPS server must be one of: {VPS_SERVERS}"

    return True, None
