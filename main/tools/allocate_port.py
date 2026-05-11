"""
allocate_port MCP Tool Implementation
"""

from datetime import datetime
from typing import Optional, Dict, Any
import re

from main.db.sqlite_store import SQLiteStore
from main.config import INFRA_DEFAULT_SERVER


# Port range configuration
PORT_MIN = 3000
PORT_MAX = 9999


async def allocate_port(
    store: SQLiteStore,
    project: str,
    service: str,
    preferred_port: Optional[int] = None,
    server: str = INFRA_DEFAULT_SERVER,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Allocate a port for a project service.

    Args:
        store: SQLiteStore instance
        project: Project name (e.g., 'my-app', 'evo-ai-mvp')
        service: Service name within the project (e.g., 'web-server', 'api')
        preferred_port: Preferred port number (optional)
        server: VPS server name (default: INFRA_DEFAULT_SERVER)
        notes: Optional notes about this port allocation

    Returns:
        Dict with success status and allocated port details or error information
    """

    # Validate project name format
    if not re.match(r"^[a-z0-9-]+$", project):
        return {
            "success": False,
            "error": "INVALID_PROJECT_NAME",
            "message": f"Project name '{project}' must contain only lowercase letters, numbers, and hyphens"
        }

    # Validate service name format
    if not re.match(r"^[a-z0-9-]+$", service):
        return {
            "success": False,
            "error": "INVALID_SERVICE_NAME",
            "message": f"Service name '{service}' must contain only lowercase letters, numbers, and hyphens"
        }

    # Determine which port to allocate
    port_to_allocate = None

    if preferred_port:
        # Validate preferred port range
        if preferred_port < PORT_MIN or preferred_port > PORT_MAX:
            return {
                "success": False,
                "error": "PORT_OUT_OF_RANGE",
                "message": f"Port {preferred_port} is out of valid range ({PORT_MIN}-{PORT_MAX})"
            }

        # Check if preferred port is available
        is_available = await store.is_port_available(preferred_port, server)

        if not is_available:
            # Get existing allocation details
            existing_allocation = await store.get_port_allocation(preferred_port, server)

            return {
                "success": False,
                "error": "PORT_ALREADY_ALLOCATED",
                "message": f"Port {preferred_port} is already allocated to {existing_allocation.project}/{existing_allocation.service}",
                "allocated_to": {
                    "project": existing_allocation.project,
                    "service": existing_allocation.service,
                    "allocated_at": existing_allocation.allocated_at.isoformat()
                },
                "suggestion": "Try without specifying preferred_port to get next available port"
            }

        port_to_allocate = preferred_port
    else:
        # Find next available port
        port_to_allocate = await find_next_available_port(store, server)

        if port_to_allocate is None:
            return {
                "success": False,
                "error": "NO_PORTS_AVAILABLE",
                "message": f"No available ports in range ({PORT_MIN}-{PORT_MAX}) on server {server}"
            }

    # Generate allocation ID with timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    allocation_id = f"alloc_{timestamp}_{port_to_allocate:04d}"

    # Allocate the port
    try:
        allocation = await store.allocate_port(
            allocation_id=allocation_id,
            port=port_to_allocate,
            project=project,
            service=service,
            server=server,
            notes=notes
        )

        return {
            "success": True,
            "allocated_port": allocation.port,
            "allocation_id": allocation.allocation_id,
            "project": allocation.project,
            "service": allocation.service,
            "server": allocation.server,
            "allocated_at": allocation.allocated_at.isoformat(),
            "status": allocation.status.value,
            "notes": allocation.notes,
            "message": f"Port {allocation.port} allocated to {project}/{service}"
        }

    except Exception as e:
        return {
            "success": False,
            "error": "ALLOCATION_FAILED",
            "message": f"Failed to allocate port: {str(e)}"
        }


async def find_next_available_port(store: SQLiteStore, server: str = INFRA_DEFAULT_SERVER) -> Optional[int]:
    """
    Find the next available port in the valid range.

    Args:
        store: SQLiteStore instance
        server: VPS server name

    Returns:
        Next available port number, or None if no ports available
    """
    # Get all allocated ports for this server
    allocations = await store.list_port_allocations(server=server)
    allocated_ports = {alloc.port for alloc in allocations}

    # Find first available port
    for port in range(PORT_MIN, PORT_MAX + 1):
        if port not in allocated_ports:
            return port

    return None


async def validate_allocate_port_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for allocate_port tool.

    Args:
        data: Input data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    if "project" not in data:
        return False, "Missing required field: project"

    if "service" not in data:
        return False, "Missing required field: service"

    # Validate types
    if not isinstance(data["project"], str):
        return False, "Field 'project' must be a string"

    if not isinstance(data["service"], str):
        return False, "Field 'service' must be a string"

    if "preferred_port" in data:
        if not isinstance(data["preferred_port"], int):
            return False, "Field 'preferred_port' must be an integer"

        if data["preferred_port"] < PORT_MIN or data["preferred_port"] > PORT_MAX:
            return False, f"Field 'preferred_port' must be between {PORT_MIN} and {PORT_MAX}"

    if "notes" in data and data["notes"] is not None:
        if not isinstance(data["notes"], str):
            return False, "Field 'notes' must be a string"

    return True, None
