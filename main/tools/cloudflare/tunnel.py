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


async def _resolve_tunnel_id(
    client,
    tunnel_id: Optional[str],
    tunnel_name: Optional[str],
) -> tuple[str, str]:
    """Resolve tunnel_id and tunnel_name, fetching whichever is missing."""
    if not tunnel_id:
        if not tunnel_name:
            raise CloudflareAPIError("Either tunnel_id or tunnel_name is required")
        data = await client.get(
            f"/accounts/{client.account_id}/cfd_tunnel",
            params={"name": tunnel_name},
        )
        tunnels = data.get("result", [])
        if not tunnels:
            raise CloudflareAPIError(f"Tunnel not found: {tunnel_name}")
        return str(tunnels[0]["id"]), str(tunnels[0]["name"])
    if not tunnel_name:
        data = await client.get(f"/accounts/{client.account_id}/cfd_tunnel/{tunnel_id}")
        tunnel_name = str(data.get("result", {}).get("name") or tunnel_id)
    return tunnel_id, tunnel_name


async def list_public_hostnames(
    tunnel_id: Optional[str] = None,
    tunnel_name: Optional[str] = None,
    **kwargs,
) -> dict:
    """
    List all public hostnames configured for a Cloudflare Tunnel.

    Args:
        tunnel_id: Tunnel ID
        tunnel_name: Tunnel name (if tunnel_id not provided)

    Returns:
        dict with list of ingress rules (hostname → service)
    """
    client = get_client()
    tunnel_id, tunnel_name = await _resolve_tunnel_id(client, tunnel_id, tunnel_name)

    data = await client.get(
        f"/accounts/{client.account_id}/cfd_tunnel/{tunnel_id}/configurations"
    )
    ingress = ((data.get("result") or {}).get("config") or {}).get("ingress") or []
    hostnames = [r for r in ingress if r.get("hostname")]

    return {
        "success": True,
        "tunnel_id": tunnel_id,
        "tunnel_name": tunnel_name,
        "hostnames": hostnames,
        "count": len(hostnames),
    }


def validate_list_public_hostnames_input(arguments: dict) -> dict:
    if not arguments.get("tunnel_id") and not arguments.get("tunnel_name"):
        return {"valid": False, "errors": ["Either tunnel_id or tunnel_name is required"]}
    return {"valid": True}


async def _upsert_tunnel_dns_cname(client, hostname: str, tunnel_id: str) -> dict:
    """Create or update the DNS CNAME for a tunnel hostname (proxied, TTL auto)."""
    # Derive root domain (last two labels) for zone lookup
    parts = hostname.split(".")
    root = ".".join(parts[-2:]) if len(parts) >= 2 else hostname
    zone_id = await client.get_zone_id(root)

    content = f"{tunnel_id}.cfargotunnel.com"
    existing = await client.get(
        f"/zones/{zone_id}/dns_records",
        params={"name": hostname, "type": "CNAME"},
    )
    records = existing.get("result", []) or []

    if records:
        record_id = records[0]["id"]
        await client.put(
            f"/zones/{zone_id}/dns_records/{record_id}",
            json_data={"type": "CNAME", "name": hostname, "content": content, "proxied": True, "ttl": 1},
        )
        return {"action": "updated", "record_id": record_id, "content": content}

    created = await client.post(
        f"/zones/{zone_id}/dns_records",
        json_data={"type": "CNAME", "name": hostname, "content": content, "proxied": True, "ttl": 1},
    )
    return {"action": "created", "record_id": created.get("result", {}).get("id"), "content": content}


async def add_public_hostname(
    hostname: str,
    service: str = "http://localhost:80",
    tunnel_id: Optional[str] = None,
    tunnel_name: Optional[str] = None,
    origin_request: Optional[dict] = None,
    update_dns: bool = True,
    **kwargs,
) -> dict:
    """
    Add a public hostname to a remotely-managed Cloudflare Tunnel.

    Updates both the tunnel's ingress config AND the DNS CNAME record
    (so traffic actually reaches the new tunnel).

    Args:
        hostname: Public hostname (e.g., 'app.your-domain.com')
        service: Backend service URL (default: 'http://localhost:80')
        tunnel_id: Tunnel ID
        tunnel_name: Tunnel name (if tunnel_id not provided)
        origin_request: Optional origin request config overrides
        update_dns: Also create/update DNS CNAME to point at this tunnel (default: True)

    Returns:
        dict confirming both ingress and DNS updates
    """
    client = get_client()
    tunnel_id, tunnel_name = await _resolve_tunnel_id(client, tunnel_id, tunnel_name)

    # Fetch current config
    data = await client.get(
        f"/accounts/{client.account_id}/cfd_tunnel/{tunnel_id}/configurations"
    )
    ingress = ((data.get("result") or {}).get("config") or {}).get("ingress") or []

    # Remove catch-all and any existing entry for this hostname
    rules = [r for r in ingress if r.get("hostname") and r["hostname"] != hostname]
    catch_all = next((r for r in ingress if not r.get("hostname")), {"service": "http_status:404"})

    new_rule: dict[str, Any] = {"hostname": hostname, "service": service}
    if origin_request:
        new_rule["originRequest"] = origin_request

    new_ingress = rules + [new_rule, catch_all]

    await client.put(
        f"/accounts/{client.account_id}/cfd_tunnel/{tunnel_id}/configurations",
        json_data={"config": {"ingress": new_ingress}},
    )

    dns_result = None
    if update_dns:
        dns_result = await _upsert_tunnel_dns_cname(client, hostname, tunnel_id)

    return {
        "success": True,
        "message": f"Public hostname added: {hostname} → {service}",
        "tunnel_id": tunnel_id,
        "tunnel_name": tunnel_name,
        "hostname": hostname,
        "service": service,
        "total_hostnames": len(rules) + 1,
        "dns": dns_result,
    }


def validate_add_public_hostname_input(arguments: dict) -> dict:
    errors = []
    if not arguments.get("hostname"):
        errors.append("hostname is required (e.g., 'app.your-domain.com')")
    if not arguments.get("tunnel_id") and not arguments.get("tunnel_name"):
        errors.append("Either tunnel_id or tunnel_name is required")
    return {"valid": not errors, "errors": errors} if errors else {"valid": True}


async def _delete_tunnel_dns_cname(client, hostname: str, tunnel_id: str) -> dict:
    """Delete DNS CNAME for a tunnel hostname (only if it points to this tunnel)."""
    parts = hostname.split(".")
    root = ".".join(parts[-2:]) if len(parts) >= 2 else hostname
    zone_id = await client.get_zone_id(root)

    existing = await client.get(
        f"/zones/{zone_id}/dns_records",
        params={"name": hostname, "type": "CNAME"},
    )
    records = existing.get("result", []) or []

    expected_content = f"{tunnel_id}.cfargotunnel.com"
    deleted = []
    skipped = []
    for rec in records:
        if rec.get("content") == expected_content:
            await client.delete(f"/zones/{zone_id}/dns_records/{rec['id']}")
            deleted.append(rec["id"])
        else:
            skipped.append({"id": rec["id"], "content": rec.get("content")})
    return {"deleted_count": len(deleted), "skipped_count": len(skipped), "skipped": skipped}


async def remove_public_hostname(
    hostname: str,
    tunnel_id: Optional[str] = None,
    tunnel_name: Optional[str] = None,
    delete_dns: bool = True,
    **kwargs,
) -> dict:
    """
    Remove a public hostname from a remotely-managed Cloudflare Tunnel.

    Removes both the tunnel's ingress entry AND the DNS CNAME record
    (only if the CNAME points to this tunnel, to avoid removing records
    that were moved elsewhere).

    Args:
        hostname: Public hostname to remove
        tunnel_id: Tunnel ID
        tunnel_name: Tunnel name (if tunnel_id not provided)
        delete_dns: Also delete the DNS CNAME if it still points here (default: True)

    Returns:
        dict confirming both ingress and DNS removal
    """
    client = get_client()
    tunnel_id, tunnel_name = await _resolve_tunnel_id(client, tunnel_id, tunnel_name)

    data = await client.get(
        f"/accounts/{client.account_id}/cfd_tunnel/{tunnel_id}/configurations"
    )
    ingress = ((data.get("result") or {}).get("config") or {}).get("ingress") or []

    original_count = len([r for r in ingress if r.get("hostname")])
    rules = [r for r in ingress if r.get("hostname") != hostname]
    removed = original_count - len([r for r in rules if r.get("hostname")])

    if removed == 0 and not delete_dns:
        return {
            "success": False,
            "message": f"Hostname not found in tunnel config: {hostname}",
            "tunnel_id": tunnel_id,
            "tunnel_name": tunnel_name,
        }

    if removed > 0:
        await client.put(
            f"/accounts/{client.account_id}/cfd_tunnel/{tunnel_id}/configurations",
            json_data={"config": {"ingress": rules}},
        )

    dns_result = None
    if delete_dns:
        dns_result = await _delete_tunnel_dns_cname(client, hostname, tunnel_id)

    return {
        "success": True,
        "message": f"Public hostname removed: {hostname}",
        "tunnel_id": tunnel_id,
        "tunnel_name": tunnel_name,
        "hostname": hostname,
        "ingress_removed": removed > 0,
        "remaining_hostnames": len([r for r in rules if r.get("hostname")]),
        "dns": dns_result,
    }


def validate_remove_public_hostname_input(arguments: dict) -> dict:
    errors = []
    if not arguments.get("hostname"):
        errors.append("hostname is required")
    if not arguments.get("tunnel_id") and not arguments.get("tunnel_name"):
        errors.append("Either tunnel_id or tunnel_name is required")
    return {"valid": not errors, "errors": errors} if errors else {"valid": True}


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
