"""
Cloudflare DNS record management tools.

Provides tools for creating, updating, deleting, and listing DNS records.

For CNAME records pointing to Cloudflare Tunnels, uses cloudflared CLI via SSH
since the API token may not have DNS edit permissions.
"""

import asyncio
from typing import Any, Optional
from main.tools.cloudflare.base import get_client, CloudflareAPIError
from main.config import INFRA_SERVERS, INFRA_DEFAULT_SERVER
from main.utils import validate_hostname, validate_identifier


# Valid DNS record types
VALID_RECORD_TYPES = ["A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA"]

# VPS servers that have cloudflared installed
VPS_SERVERS = INFRA_SERVERS


def validate_create_dns_record_input(arguments: dict) -> dict:
    """Validate input for create_dns_record."""
    errors = []

    # Required fields
    if not arguments.get("domain"):
        errors.append("domain is required (e.g., 'app.your-domain.com')")

    if not arguments.get("record_type"):
        errors.append("record_type is required (e.g., 'CNAME', 'A')")
    elif arguments["record_type"].upper() not in VALID_RECORD_TYPES:
        errors.append(f"record_type must be one of: {', '.join(VALID_RECORD_TYPES)}")

    if not arguments.get("content"):
        errors.append("content is required (e.g., IP address or target domain)")

    if errors:
        return {"valid": False, "errors": errors}

    return {"valid": True}


def validate_update_dns_record_input(arguments: dict) -> dict:
    """Validate input for update_dns_record."""
    errors = []

    # Required fields
    if not arguments.get("domain"):
        errors.append("domain is required (e.g., 'app.your-domain.com')")

    if not arguments.get("record_id") and not arguments.get("record_type"):
        errors.append("Either record_id or record_type is required to identify the record")

    if errors:
        return {"valid": False, "errors": errors}

    return {"valid": True}


def validate_delete_dns_record_input(arguments: dict) -> dict:
    """Validate input for delete_dns_record."""
    errors = []

    # Required: either record_id, or domain + record_type
    if not arguments.get("record_id"):
        if not arguments.get("domain"):
            errors.append("domain is required when record_id is not provided")
        if not arguments.get("record_type"):
            errors.append("record_type is required when record_id is not provided")

    if errors:
        return {"valid": False, "errors": errors}

    return {"valid": True}


def validate_list_dns_records_input(arguments: dict) -> dict:
    """Validate input for list_dns_records."""
    # domain is optional - if not provided, will need zone_id
    # All parameters are optional for listing
    return {"valid": True}


async def _create_dns_via_cloudflared(
    tunnel_name: str,
    domain: str,
    server: str = INFRA_DEFAULT_SERVER,
) -> dict:
    """
    Create a DNS CNAME record using cloudflared CLI via SSH.

    This is used when the API token doesn't have DNS edit permissions.
    cloudflared uses its own credentials (~/.cloudflared/cert.pem).

    Args:
        tunnel_name: The tunnel name (e.g., 'prod-main')
        domain: The full domain name (e.g., 'app.your-domain.com')
        server: VPS server to run cloudflared on (default: first INFRA_SERVERS)

    Returns:
        dict with creation result
    """
    if server not in VPS_SERVERS:
        raise CloudflareAPIError(f"Unknown server: {server}. Valid: {', '.join(VPS_SERVERS)}")

    # Validate inputs before passing to SSH — prevents injection via nested quoting
    try:
        validate_identifier(tunnel_name, "tunnel_name")
        validate_hostname(domain)
    except ValueError as e:
        raise CloudflareAPIError(str(e))

    # Use execv-style (no shell) so arguments are never interpreted by a shell
    try:
        proc = await asyncio.create_subprocess_exec(
            "ssh", server,
            "cloudflared", "tunnel", "route", "dns", tunnel_name, domain,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode().strip() or stdout.decode().strip()
            raise CloudflareAPIError(f"cloudflared error: {error_msg}")

        return {
            "success": True,
            "message": f"DNS CNAME created via cloudflared: {domain} -> {tunnel_name}",
            "record": {
                "type": "CNAME",
                "name": domain,
                "tunnel_name": tunnel_name,
                "server": server,
            },
            "method": "cloudflared_cli",
        }
    except Exception as e:
        if "cloudflared error" in str(e):
            raise
        raise CloudflareAPIError(f"SSH error: {str(e)}")


async def create_dns_record(
    domain: str,
    record_type: str,
    content: str,
    name: Optional[str] = None,
    ttl: int = 1,  # 1 = auto
    proxied: bool = False,
    priority: Optional[int] = None,
    comment: Optional[str] = None,
    tunnel_name: Optional[str] = None,
    server: Optional[str] = None,
    **kwargs,
) -> dict:
    """
    Create a DNS record in Cloudflare.

    For CNAME records pointing to Cloudflare Tunnels, you can use the
    tunnel_name parameter to create via cloudflared CLI (which has its
    own credentials and doesn't require API token DNS edit permissions).

    Args:
        domain: The full domain name (e.g., 'app.your-domain.com')
        record_type: DNS record type (A, AAAA, CNAME, TXT, MX, etc.)
        content: Record content (IP address, target domain, etc.)
        name: Record name (defaults to domain)
        ttl: Time to live (1 = auto, or seconds like 300, 3600)
        proxied: Whether to proxy through Cloudflare (default: False)
        priority: Priority for MX/SRV records
        comment: Optional comment for the record
        tunnel_name: (Optional) Tunnel name for cloudflared CLI method
        server: (Optional) VPS server to run cloudflared on (default: first INFRA_SERVERS)

    Returns:
        dict with created record details
    """
    # Check if this is a tunnel CNAME that should use cloudflared CLI
    is_tunnel_cname = (
        record_type.upper() == "CNAME" and
        content.endswith(".cfargotunnel.com")
    )

    # If tunnel_name provided OR content is a tunnel CNAME, use cloudflared CLI
    if tunnel_name or (is_tunnel_cname and server):
        # Extract tunnel_name from content if not provided
        if not tunnel_name and is_tunnel_cname:
            # Try to find tunnel name from our database or use tunnel ID
            # For now, require explicit tunnel_name
            raise CloudflareAPIError(
                "tunnel_name is required for creating tunnel CNAME records. "
                "Example: tunnel_name='prod-main'"
            )

        return await _create_dns_via_cloudflared(
            tunnel_name=tunnel_name,
            domain=domain,
            server=server or INFRA_DEFAULT_SERVER,
        )

    # Use Cloudflare API (requires DNS edit permission on the token)
    client = get_client()

    # Get zone ID from domain
    zone_id = await client.get_zone_id(domain)

    # Build record data
    record_data: dict[str, Any] = {
        "type": record_type.upper(),
        "name": name or domain,
        "content": content,
        "ttl": ttl,
        "proxied": proxied if record_type.upper() in ["A", "AAAA", "CNAME"] else False,
    }

    if priority is not None and record_type.upper() in ["MX", "SRV"]:
        record_data["priority"] = priority

    if comment:
        record_data["comment"] = comment

    # Create the record
    data = await client.post(f"/zones/{zone_id}/dns_records", json_data=record_data)
    result = data.get("result", {})

    return {
        "success": True,
        "message": f"DNS record created: {record_type} {domain} -> {content}",
        "record": {
            "id": result.get("id"),
            "type": result.get("type"),
            "name": result.get("name"),
            "content": result.get("content"),
            "ttl": result.get("ttl"),
            "proxied": result.get("proxied"),
            "zone_id": zone_id,
        },
        "method": "cloudflare_api",
    }


async def update_dns_record(
    domain: str,
    record_id: Optional[str] = None,
    record_type: Optional[str] = None,
    content: Optional[str] = None,
    ttl: Optional[int] = None,
    proxied: Optional[bool] = None,
    comment: Optional[str] = None,
    **kwargs,
) -> dict:
    """
    Update an existing DNS record.

    Args:
        domain: The full domain name
        record_id: Record ID (if known)
        record_type: Record type to find (if record_id not provided)
        content: New content value
        ttl: New TTL value
        proxied: New proxied status
        comment: New comment

    Returns:
        dict with updated record details
    """
    client = get_client()
    zone_id = await client.get_zone_id(domain)

    # Find record if record_id not provided
    if not record_id:
        params: dict[str, Any] = {"name": domain}
        if record_type:
            params["type"] = record_type.upper()

        data = await client.get(f"/zones/{zone_id}/dns_records", params=params)
        records = data.get("result", [])

        if not records:
            raise CloudflareAPIError(f"No DNS record found for {domain}")

        record_id = records[0]["id"]
        existing_record = records[0]
    else:
        # Get existing record
        data = await client.get(f"/zones/{zone_id}/dns_records/{record_id}")
        existing_record = data.get("result", {})

    # Build update data (merge with existing)
    update_data: dict[str, Any] = {
        "type": existing_record.get("type"),
        "name": existing_record.get("name"),
        "content": content or existing_record.get("content"),
        "ttl": ttl if ttl is not None else existing_record.get("ttl"),
    }

    if existing_record.get("type") in ["A", "AAAA", "CNAME"]:
        update_data["proxied"] = proxied if proxied is not None else existing_record.get("proxied", False)

    if comment is not None:
        update_data["comment"] = comment

    # Update the record
    data = await client.put(f"/zones/{zone_id}/dns_records/{record_id}", json_data=update_data)
    result = data.get("result", {})

    return {
        "success": True,
        "message": f"DNS record updated: {result.get('type')} {result.get('name')}",
        "record": {
            "id": result.get("id"),
            "type": result.get("type"),
            "name": result.get("name"),
            "content": result.get("content"),
            "ttl": result.get("ttl"),
            "proxied": result.get("proxied"),
        },
    }


async def delete_dns_record(
    record_id: Optional[str] = None,
    domain: Optional[str] = None,
    record_type: Optional[str] = None,
    zone_id: Optional[str] = None,
    **kwargs,
) -> dict:
    """
    Delete a DNS record.

    Args:
        record_id: Record ID to delete
        domain: Domain name (used to find record if record_id not provided)
        record_type: Record type (used with domain to find record)
        zone_id: Zone ID (optional, will be derived from domain)

    Returns:
        dict with deletion confirmation
    """
    client = get_client()

    # Get zone_id if not provided
    if not zone_id and domain:
        zone_id = await client.get_zone_id(domain)
    elif not zone_id:
        raise CloudflareAPIError("Either zone_id or domain is required")

    # Find record if record_id not provided
    if not record_id:
        if not domain or not record_type:
            raise CloudflareAPIError("domain and record_type required when record_id not provided")

        data = await client.get(
            f"/zones/{zone_id}/dns_records",
            params={"name": domain, "type": record_type.upper()},
        )
        records = data.get("result", [])

        if not records:
            raise CloudflareAPIError(f"No {record_type} record found for {domain}")

        record_id = records[0]["id"]
        record_info = records[0]
    else:
        # Get record info before deletion
        data = await client.get(f"/zones/{zone_id}/dns_records/{record_id}")
        record_info = data.get("result", {})

    # Delete the record
    await client.delete(f"/zones/{zone_id}/dns_records/{record_id}")

    return {
        "success": True,
        "message": f"DNS record deleted: {record_info.get('type')} {record_info.get('name')}",
        "deleted_record": {
            "id": record_id,
            "type": record_info.get("type"),
            "name": record_info.get("name"),
            "content": record_info.get("content"),
        },
    }


async def list_dns_records(
    domain: Optional[str] = None,
    zone_id: Optional[str] = None,
    record_type: Optional[str] = None,
    name_contains: Optional[str] = None,
    per_page: int = 100,
    **kwargs,
) -> dict:
    """
    List DNS records for a zone.

    Args:
        domain: Domain to derive zone from (e.g., 'your-domain.com' or 'app.your-domain.com')
        zone_id: Zone ID (optional if domain provided)
        record_type: Filter by record type
        name_contains: Filter records containing this string
        per_page: Number of records per page (max 5000)

    Returns:
        dict with list of DNS records
    """
    client = get_client()

    # Get zone_id
    if not zone_id:
        if domain:
            zone_id = await client.get_zone_id(domain)
        else:
            # List zones to help user
            zones = await client.list_zones()
            zone_list = [{"name": z["name"], "id": z["id"]} for z in zones]
            return {
                "success": True,
                "message": "No domain specified. Available zones:",
                "zones": zone_list,
                "records": [],
            }

    # Build query params
    params: dict[str, Any] = {"per_page": min(per_page, 5000)}
    if record_type:
        params["type"] = record_type.upper()
    if name_contains:
        params["name"] = name_contains

    # Get records
    data = await client.get(f"/zones/{zone_id}/dns_records", params=params)
    records = data.get("result", [])

    # Format output
    formatted_records = []
    for r in records:
        formatted_records.append({
            "id": r.get("id"),
            "type": r.get("type"),
            "name": r.get("name"),
            "content": r.get("content"),
            "ttl": r.get("ttl"),
            "proxied": r.get("proxied"),
            "comment": r.get("comment"),
        })

    return {
        "success": True,
        "message": f"Found {len(formatted_records)} DNS records",
        "zone_id": zone_id,
        "records": formatted_records,
    }
