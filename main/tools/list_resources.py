"""
list_resources MCP Tool Implementation
"""

from typing import Optional, Dict, Any, List
from main.db.sqlite_store import SQLiteStore
from main.config import INFRA_DEFAULT_SERVER
from main.utils import get_service_name, resolve_paths
from main.models.port_allocation import AllocationStatus
from main.models.main_tunnel import MainTunnelStatus
from main.models.service_deployment import DeploymentStatus


# Port range configuration
PORT_MIN = 3000
PORT_MAX = 9999
TOTAL_PORTS = PORT_MAX - PORT_MIN + 1


async def list_resources(
    store: SQLiteStore,
    resource_type: str = "all",
    project: Optional[str] = None,
    server: Optional[str] = None,
    status: Optional[str] = None,
    include_released: bool = False
) -> Dict[str, Any]:
    """
    List infrastructure resource allocations.

    Args:
        store: SQLiteStore instance
        resource_type: Type of resources to list ("all", "ports", "tunnels", "deployments")
        project: Filter by project name (optional)
        server: Filter by VPS server (optional)
        status: Filter by resource status (optional)
        include_released: Include released/deallocated resources (default: False)

    Returns:
        Dict with success status and resource listings
    """

    try:
        resources = {}

        # Fetch ports if requested
        if resource_type in ["all", "ports"]:
            ports = await _fetch_ports(store, project, server, status, include_released)
            resources["ports"] = ports

        # Fetch tunnels if requested
        if resource_type in ["all", "tunnels"]:
            tunnels = await _fetch_tunnels(store, project, server, status, include_released)
            resources["tunnels"] = tunnels

        # Fetch deployments if requested
        if resource_type in ["all", "deployments"]:
            deployments = await _fetch_deployments(store, project, server, status, include_released)
            resources["deployments"] = deployments

        # Generate summary statistics
        summary = await _generate_summary(store, resources, server)

        return {
            "success": True,
            "resources": resources,
            "summary": summary,
            "message": "Resource query completed"
        }

    except Exception as e:
        return {
            "success": False,
            "error": "QUERY_FAILED",
            "message": f"Failed to query resources: {str(e)}"
        }


async def _fetch_ports(
    store: SQLiteStore,
    project: Optional[str],
    server: Optional[str],
    status: Optional[str],
    include_released: bool
) -> List[Dict[str, Any]]:
    """
    Fetch port allocations based on filters.

    Returns:
        List of port allocation dictionaries
    """
    allocations = await store.list_port_allocations(project=project, server=server)

    # Filter by status if specified
    if status and status != "all":
        status_map = {
            "active": [AllocationStatus.IN_USE],
            "inactive": [AllocationStatus.RESERVED, AllocationStatus.ALLOCATED],
            "failed": []  # No failed status for ports
        }
        if status in status_map:
            allowed_statuses = status_map[status]
            allocations = [a for a in allocations if a.status in allowed_statuses]

    # Exclude released allocations unless specifically requested
    if not include_released:
        allocations = [a for a in allocations if a.status != AllocationStatus.RELEASED]

    # Convert to dict format
    ports = []
    for alloc in allocations:
        ports.append({
            "port": alloc.port,
            "project": alloc.project,
            "service": alloc.service,
            "server": alloc.server,
            "allocation_id": alloc.allocation_id,
            "allocated_at": alloc.allocated_at.isoformat(),
            "allocated_by": alloc.allocated_by,
            "status": alloc.status.value,
            "notes": alloc.notes
        })

    # Sort by port number
    ports.sort(key=lambda x: x["port"])

    return ports


async def _fetch_tunnels(
    store: SQLiteStore,
    project: Optional[str],
    server: Optional[str],
    status: Optional[str],
    include_released: bool
) -> List[Dict[str, Any]]:
    """
    Fetch main tunnels based on filters.

    Main tunnels are actual Cloudflare Tunnels (one per VPS).
    Services are routed through Caddy on the main tunnel, not tracked here.

    Returns:
        List of main tunnel dictionaries
    """
    tunnels_data = await store.list_main_tunnels(vps_server=server, status=status)

    # Convert to dict format
    tunnels = []
    for tunnel in tunnels_data:
        tunnel_info = {
            "tunnel_name": tunnel.tunnel_name,
            "cloudflare_tunnel_id": tunnel.cloudflare_tunnel_id,
            "vps_server": tunnel.vps_server,
            "tunnel_target": tunnel.tunnel_target,
            "status": tunnel.status.value,
            "created_at": tunnel.created_at.isoformat() if tunnel.created_at else None,
        }

        # Add optional fields if present
        if tunnel.credentials_file:
            tunnel_info["credentials_file"] = tunnel.credentials_file
        if tunnel.config_file:
            tunnel_info["config_file"] = tunnel.config_file
        if tunnel.systemd_service:
            tunnel_info["systemd_service"] = tunnel.systemd_service
        if tunnel.notes:
            tunnel_info["notes"] = tunnel.notes

        tunnels.append(tunnel_info)

    # Sort by VPS server
    tunnels.sort(key=lambda x: x["vps_server"])

    return tunnels


async def _fetch_deployments(
    store: SQLiteStore,
    project: Optional[str],
    server: Optional[str],
    status: Optional[str],
    include_released: bool
) -> List[Dict[str, Any]]:
    """
    Fetch service deployments based on filters.

    Returns:
        List of deployment dictionaries with connection and directory info
    """
    deployments_data = await store.list_service_deployments(
        project=project,
        server=server,
        include_purged=include_released
    )

    # Filter by status if specified
    if status and status != "all":
        status_map = {
            "active": [DeploymentStatus.DEPLOYED],
            "inactive": [DeploymentStatus.REGISTERED, DeploymentStatus.STOPPED, DeploymentStatus.ARCHIVED],
            "failed": []  # No failed status for deployments currently
        }
        if status in status_map:
            allowed_statuses = status_map[status]
            deployments_data = [d for d in deployments_data if d.status in allowed_statuses]

    # Convert to dict format with connection and directory info
    deployments = []
    for dep in deployments_data:
        service_type = dep.service_type.value

        # Build connection info
        connection = {}
        if dep.hostname:
            connection["url"] = f"https://{dep.hostname}"
        if dep.port:
            connection["port"] = dep.port

        # Build directory structure summary — derived from roots, not stored.
        dep_paths = resolve_paths(dep)
        directories = {
            "static": dep_paths["static"],
            "app": dep_paths["app"] if service_type != "static" else None,
        }

        deployment_info = {
            "deployment_id": dep.deployment_id,
            "project": dep.project,
            "service": dep.service,
            "server": dep.server,
            "service_type": service_type,
            "status": dep.status.value,
            "connection": connection,
            "directories": directories,
            "registered_at": dep.registered_at.isoformat() if dep.registered_at else None,
            "deployed_at": dep.deployed_at.isoformat() if dep.deployed_at else None,
        }

        # Add systemd service name for non-static services
        if service_type in ["flask", "nodejs", "flask+static"]:
            deployment_info["systemd_service"] = get_service_name(dep.project, dep.service, dep.systemd_config)

        deployments.append(deployment_info)

    # Sort by project, then service
    deployments.sort(key=lambda x: (x["project"], x["service"]))

    return deployments


async def _generate_summary(
    store: SQLiteStore,
    resources: Dict[str, List],
    server_filter: Optional[str]
) -> Dict[str, Any]:
    """
    Generate summary statistics for resources.

    Returns:
        Summary dictionary with statistics
    """
    summary = {}

    # Port statistics
    if "ports" in resources:
        ports = resources["ports"]
        total_allocated = len(ports)
        ports_in_use = len([p for p in ports if p["status"] == "in-use"])
        ports_available = TOTAL_PORTS - total_allocated

        summary.update({
            "total_ports_allocated": total_allocated,
            "ports_in_use": ports_in_use,
            "ports_available": ports_available
        })

    # Tunnel statistics
    if "tunnels" in resources:
        tunnels = resources["tunnels"]
        total_tunnels = len(tunnels)
        tunnels_active = len([t for t in tunnels if t["status"] == "active"])

        summary.update({
            "total_tunnels": total_tunnels,
            "tunnels_active": tunnels_active
        })

    # Deployment statistics (placeholder)
    if "deployments" in resources:
        deployments = resources["deployments"]
        total_deployments = len(deployments)
        deployments_running = len([d for d in deployments if d.get("status") == "running"])

        summary.update({
            "total_deployments": total_deployments,
            "deployments_running": deployments_running
        })

    # Server-level statistics
    servers_summary = {}

    # For now, we only have the default server
    if not server_filter or server_filter == INFRA_DEFAULT_SERVER:
        server_ports = [p for p in resources.get("ports", []) if p.get("server") == INFRA_DEFAULT_SERVER]
        server_tunnels = [t for t in resources.get("tunnels", []) if t.get("server") == INFRA_DEFAULT_SERVER]
        server_deployments = [d for d in resources.get("deployments", []) if d.get("server") == INFRA_DEFAULT_SERVER]

        servers_summary[INFRA_DEFAULT_SERVER] = {
            "ports_used": len(server_ports),
            "tunnels": len(server_tunnels),
            "deployments": len(server_deployments),
            "status": "healthy"
        }

    summary["servers"] = servers_summary

    return summary


async def validate_list_resources_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for list_resources tool.

    Args:
        data: Input data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    # All parameters are optional, but validate enum values if provided

    if "resource_type" in data:
        valid_types = ["all", "ports", "tunnels", "deployments"]
        if data["resource_type"] not in valid_types:
            return False, f"Invalid resource_type. Must be one of: {', '.join(valid_types)}"

    if "status" in data and data["status"] is not None:
        valid_statuses = ["all", "active", "inactive", "failed"]
        if data["status"] not in valid_statuses:
            return False, f"Invalid status. Must be one of: {', '.join(valid_statuses)}"

    if "include_released" in data:
        if not isinstance(data["include_released"], bool):
            return False, "Field 'include_released' must be a boolean"

    # Validate project and server are strings if provided
    if "project" in data and data["project"] is not None:
        if not isinstance(data["project"], str):
            return False, "Field 'project' must be a string"

    if "server" in data and data["server"] is not None:
        if not isinstance(data["server"], str):
            return False, "Field 'server' must be a string"

    return True, None
