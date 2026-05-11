"""
list_main_tunnels MCP Tool Implementation

List all registered main tunnels (actual Cloudflare Tunnels).
"""

from typing import Optional, Dict, Any, List

from main.db.sqlite_store import SQLiteStore


async def list_main_tunnels(
    store: SQLiteStore,
    vps_server: Optional[str] = None,
    status: Optional[str] = None
) -> Dict[str, Any]:
    """
    List all main tunnels.

    Args:
        store: SQLiteStore instance
        vps_server: Filter by VPS server (optional)
        status: Filter by status (optional)

    Returns:
        Dict with success status and list of tunnels
    """

    try:
        tunnels = await store.list_main_tunnels(
            vps_server=vps_server,
            status=status
        )

        tunnel_list = []
        for tunnel in tunnels:
            tunnel_list.append({
                "tunnel_name": tunnel.tunnel_name,
                "cloudflare_tunnel_id": tunnel.cloudflare_tunnel_id,
                "vps_server": tunnel.vps_server,
                "tunnel_target": tunnel.tunnel_target,
                "systemd_service": tunnel.systemd_service,
                "status": tunnel.status.value,
                "created_at": tunnel.created_at.isoformat() if tunnel.created_at else None,
            })

        # Sort by VPS server
        tunnel_list.sort(key=lambda x: x["vps_server"])

        return {
            "success": True,
            "count": len(tunnel_list),
            "tunnels": tunnel_list,
            "message": f"Found {len(tunnel_list)} main tunnel(s)"
        }

    except Exception as e:
        return {
            "success": False,
            "error": "QUERY_FAILED",
            "message": f"Failed to list main tunnels: {str(e)}"
        }


async def validate_list_main_tunnels_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Validate input parameters."""
    # All parameters are optional
    if "vps_server" in data and data["vps_server"] is not None:
        if not isinstance(data["vps_server"], str):
            return False, "Field 'vps_server' must be a string"

    if "status" in data and data["status"] is not None:
        if not isinstance(data["status"], str):
            return False, "Field 'status' must be a string"
        valid_statuses = ["active", "inactive", "failed"]
        if data["status"] not in valid_statuses:
            return False, f"Status must be one of: {valid_statuses}"

    return True, None
