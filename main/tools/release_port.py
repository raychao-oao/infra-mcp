"""
Release Port Tool

Release a port allocation and mark it as available for reuse.
"""

from typing import Any, Tuple
from main.db.base import ResourceStore
from main.config import INFRA_DEFAULT_SERVER


async def validate_release_port_input(params: dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate release_port input parameters.

    Args:
        params: Input parameters

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Required: port
    if "port" not in params:
        return False, "Missing required parameter: port"

    port = params.get("port")

    # Validate port type
    if not isinstance(port, int):
        return False, f"port must be an integer, got {type(port).__name__}"

    # Validate port range
    if not (3000 <= port <= 9999):
        return False, f"port must be between 3000-9999, got {port}"

    # Optional: server (default: INFRA_DEFAULT_SERVER)
    server = params.get("server", INFRA_DEFAULT_SERVER)
    if not isinstance(server, str):
        return False, f"server must be a string, got {type(server).__name__}"

    return True, ""


async def release_port(
    store: ResourceStore,
    port: int,
    server: str = INFRA_DEFAULT_SERVER
) -> dict[str, Any]:
    """
    Release a port allocation.

    Args:
        store: Resource store instance
        port: Port number to release
        server: VPS server name (default: INFRA_DEFAULT_SERVER)

    Returns:
        Result dictionary with success status
    """
    try:
        # Check if port is allocated
        allocation = await store.get_port_allocation(port, server)

        if not allocation:
            return {
                "success": False,
                "error": "PORT_NOT_FOUND",
                "message": f"Port {port} is not allocated on {server}"
            }

        # Check if already released
        if allocation.status == "released":
            return {
                "success": False,
                "error": "ALREADY_RELEASED",
                "message": f"Port {port} on {server} is already released"
            }

        # Release the port
        released = await store.release_port(port, server)

        if not released:
            return {
                "success": False,
                "error": "RELEASE_FAILED",
                "message": f"Failed to release port {port} on {server}"
            }

        return {
            "success": True,
            "data": {
                "port": port,
                "server": server,
                "project": allocation.project,
                "service": allocation.service,
                "allocation_id": allocation.allocation_id,
                "was_status": allocation.status,
                "new_status": "released"
            },
            "message": f"✅ Port {port} released from {allocation.project}/{allocation.service} on {server}"
        }

    except Exception as e:
        return {
            "success": False,
            "error": "INTERNAL_ERROR",
            "message": f"Failed to release port: {str(e)}"
        }
