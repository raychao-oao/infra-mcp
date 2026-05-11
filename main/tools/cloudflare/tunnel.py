"""
Cloudflare Tunnel API management tools.

Provides tools for creating, deleting, and listing Cloudflare Tunnels via API.
Note: This is different from the tunnel registration in the database -
these tools interact directly with Cloudflare's Tunnel API.
"""

from typing import Any, Optional
import secrets
from main.tools.cloudflare.base import get_client, CloudflareAPIError


def validate_create_cloudflare_tunnel_input(arguments: dict) -> dict:
    """Validate input for create_cloudflare_tunnel."""
    errors = []

    if not arguments.get("name"):
        errors.append("name is required (e.g., 'prod-main')")

    if errors:
        return {"valid": False, "errors": errors}

    return {"valid": True}


def validate_delete_cloudflare_tunnel_input(arguments: dict) -> dict:
    """Validate input for delete_cloudflare_tunnel."""
    errors = []

    if not arguments.get("tunnel_id") and not arguments.get("tunnel_name"):
        errors.append("Either tunnel_id or tunnel_name is required")

    if errors:
        return {"valid": False, "errors": errors}

    return {"valid": True}


def validate_list_cloudflare_tunnels_input(arguments: dict) -> dict:
    """Validate input for list_cloudflare_tunnels."""
    # No required parameters
    return {"valid": True}


def validate_get_tunnel_token_input(arguments: dict) -> dict:
    """Validate input for get_tunnel_token."""
    errors = []

    if not arguments.get("tunnel_id") and not arguments.get("tunnel_name"):
        errors.append("Either tunnel_id or tunnel_name is required")

    if errors:
        return {"valid": False, "errors": errors}

    return {"valid": True}


async def create_cloudflare_tunnel(
    name: str,
    config_src: str = "cloudflare",
    **kwargs,
) -> dict:
    """
    Create a Cloudflare Tunnel via API.

    Args:
        name: Tunnel name (e.g., 'prod-main', 'staging-main')
        config_src: Configuration source ('cloudflare' or 'local')

    Returns:
        dict with created tunnel details including credentials
    """
    client = get_client()

    # Generate tunnel secret
    tunnel_secret = secrets.token_hex(32)

    # Create tunnel
    tunnel_data = {
        "name": name,
        "tunnel_secret": tunnel_secret,
        "config_src": config_src,
    }

    data = await client.post(
        f"/accounts/{client.account_id}/cfd_tunnel",
        json_data=tunnel_data,
    )
    tunnel = data.get("result", {})

    return {
        "success": True,
        "message": f"Cloudflare Tunnel created: {name}",
        "tunnel": {
            "id": tunnel.get("id"),
            "name": tunnel.get("name"),
            "status": tunnel.get("status"),
            "created_at": tunnel.get("created_at"),
            "config_src": config_src,
        },
        "credentials": {
            "account_tag": client.account_id,
            "tunnel_id": tunnel.get("id"),
            "tunnel_secret": tunnel_secret,
        },
        "connection_string": f"{tunnel.get('id')}.cfargotunnel.com",
        "install_command": f"cloudflared service install {tunnel.get('token', '')}",
    }


async def delete_cloudflare_tunnel(
    tunnel_id: Optional[str] = None,
    tunnel_name: Optional[str] = None,
    force: bool = False,
    **kwargs,
) -> dict:
    """
    Delete a Cloudflare Tunnel.

    Args:
        tunnel_id: Tunnel ID to delete
        tunnel_name: Tunnel name (used to find tunnel if tunnel_id not provided)
        force: Force delete even if tunnel has active connections

    Returns:
        dict with deletion confirmation
    """
    client = get_client()

    # Find tunnel by name if tunnel_id not provided
    if not tunnel_id:
        if not tunnel_name:
            raise CloudflareAPIError("Either tunnel_id or tunnel_name is required")

        data = await client.get(
            f"/accounts/{client.account_id}/cfd_tunnel",
            params={"name": tunnel_name, "is_deleted": False},
        )
        tunnels = data.get("result", [])

        if not tunnels:
            raise CloudflareAPIError(f"Tunnel not found: {tunnel_name}")

        tunnel_id = tunnels[0]["id"]
        tunnel_info = tunnels[0]
    else:
        # Get tunnel info
        data = await client.get(f"/accounts/{client.account_id}/cfd_tunnel/{tunnel_id}")
        tunnel_info = data.get("result", {})

    # Check for active connections
    if not force:
        connections_data = await client.get(
            f"/accounts/{client.account_id}/cfd_tunnel/{tunnel_id}/connections"
        )
        connections = connections_data.get("result", [])
        if connections:
            raise CloudflareAPIError(
                f"Tunnel has {len(connections)} active connection(s). "
                "Use force=True to delete anyway or disconnect first."
            )

    # Delete the tunnel
    await client.delete(f"/accounts/{client.account_id}/cfd_tunnel/{tunnel_id}")

    return {
        "success": True,
        "message": f"Cloudflare Tunnel deleted: {tunnel_info.get('name', tunnel_id)}",
        "deleted_tunnel": {
            "id": tunnel_id,
            "name": tunnel_info.get("name"),
        },
    }


async def list_cloudflare_tunnels(
    include_deleted: bool = False,
    status: Optional[str] = None,
    name_contains: Optional[str] = None,
    **kwargs,
) -> dict:
    """
    List Cloudflare Tunnels.

    Args:
        include_deleted: Include deleted tunnels
        status: Filter by status ('active', 'inactive')
        name_contains: Filter tunnels containing this string in name

    Returns:
        dict with list of tunnels
    """
    client = get_client()

    params = {"is_deleted": include_deleted}
    if name_contains:
        params["name"] = name_contains

    data = await client.get(
        f"/accounts/{client.account_id}/cfd_tunnel",
        params=params,
    )
    tunnels = data.get("result", [])

    # Filter by status if specified
    if status:
        tunnels = [t for t in tunnels if t.get("status") == status]

    # Format output
    formatted_tunnels = []
    for t in tunnels:
        formatted_tunnels.append({
            "id": t.get("id"),
            "name": t.get("name"),
            "status": t.get("status"),
            "created_at": t.get("created_at"),
            "connections_count": len(t.get("connections", [])),
            "cname_target": f"{t.get('id')}.cfargotunnel.com",
        })

    return {
        "success": True,
        "message": f"Found {len(formatted_tunnels)} tunnels",
        "tunnels": formatted_tunnels,
    }


async def get_tunnel_token(
    tunnel_id: Optional[str] = None,
    tunnel_name: Optional[str] = None,
    **kwargs,
) -> dict:
    """
    Get the connection token for a Cloudflare Tunnel.

    This token is used to connect cloudflared to the tunnel.

    Args:
        tunnel_id: Tunnel ID
        tunnel_name: Tunnel name (used to find tunnel if tunnel_id not provided)

    Returns:
        dict with tunnel token and connection info
    """
    client = get_client()

    # Find tunnel by name if tunnel_id not provided
    if not tunnel_id:
        if not tunnel_name:
            raise CloudflareAPIError("Either tunnel_id or tunnel_name is required")

        data = await client.get(
            f"/accounts/{client.account_id}/cfd_tunnel",
            params={"name": tunnel_name, "is_deleted": False},
        )
        tunnels = data.get("result", [])

        if not tunnels:
            raise CloudflareAPIError(f"Tunnel not found: {tunnel_name}")

        tunnel_id = tunnels[0]["id"]
        tunnel_name = tunnels[0]["name"]

    # Get token
    data = await client.get(f"/accounts/{client.account_id}/cfd_tunnel/{tunnel_id}/token")
    token = data.get("result", "")

    return {
        "success": True,
        "message": f"Token retrieved for tunnel: {tunnel_name or tunnel_id}",
        "tunnel_id": tunnel_id,
        "tunnel_name": tunnel_name,
        "token": token,
        "install_command": f"sudo cloudflared service install {token}",
        "run_command": f"cloudflared tunnel run --token {token}",
    }
