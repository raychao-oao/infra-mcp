"""
upgrade_service MCP Tool Implementation

Handles service type upgrades, primarily:
- static -> flask+static (add backend to existing static site)

When upgrading, this tool:
1. Updates service_type in database
2. Sets app_path if not already set
3. Port will be allocated during deploy (if not already allocated)
"""

from datetime import datetime
from typing import Optional, Dict, Any

from main.db.sqlite_store import SQLiteStore


# Valid upgrade paths
VALID_UPGRADES = {
    "static": ["flask", "flask+static", "nodejs"],
    "flask": ["flask+static"],
}


async def upgrade_service(
    store: SQLiteStore,
    project: str,
    service: str,
    server: str,
    new_service_type: str,
    app_path: Optional[str] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Upgrade a service to a different type.

    Primary use case: static -> flask+static (add backend to static site)

    Args:
        store: SQLiteStore instance
        project: Project name
        service: Service name
        server: VPS server name
        new_service_type: New service type to upgrade to
        app_path: Application code path (optional, will use default if not provided)
        notes: Optional notes about the upgrade

    Returns:
        Dict with success status and upgrade details
    """

    # Get existing deployment
    deployment = await store.get_service_deployment(project, service, server)
    if not deployment:
        return {
            "success": False,
            "error": "SERVICE_NOT_FOUND",
            "message": f"Service {project}/{service} not found on {server}"
        }

    current_type = deployment.service_type.value

    # Validate upgrade path
    valid_types = ["flask", "nodejs", "static", "docker", "flask+static"]
    if new_service_type not in valid_types:
        return {
            "success": False,
            "error": "INVALID_SERVICE_TYPE",
            "message": f"Invalid service type: {new_service_type}. Valid types: {valid_types}"
        }

    # Check if upgrade is valid
    allowed_upgrades = VALID_UPGRADES.get(current_type, [])
    if new_service_type not in allowed_upgrades:
        if current_type == new_service_type:
            return {
                "success": False,
                "error": "NO_UPGRADE_NEEDED",
                "message": f"Service is already type '{current_type}'"
            }
        return {
            "success": False,
            "error": "INVALID_UPGRADE_PATH",
            "message": f"Cannot upgrade from '{current_type}' to '{new_service_type}'. Allowed: {allowed_upgrades or 'none'}"
        }

    # Determine app_path
    final_app_path = app_path or deployment.app_path or f"~/PRJ/{project}/app/"

    # Update the deployment
    try:
        # Update service type and app_path
        updated = await store.update_service_deployment(
            deployment_id=deployment.deployment_id,
            service_type=new_service_type,
            app_path=final_app_path,
            notes=f"Upgraded from {current_type} to {new_service_type}. {notes or ''}"
        )

        if not updated:
            return {
                "success": False,
                "error": "UPDATE_FAILED",
                "message": "Failed to update service deployment"
            }

        return {
            "success": True,
            "deployment_id": deployment.deployment_id,
            "project": project,
            "service": service,
            "server": server,
            "upgrade": {
                "from": current_type,
                "to": new_service_type,
            },
            "app_path": final_app_path,
            "port_info": "Port will be allocated during next deploy" if not deployment.port else f"Port {deployment.port} already allocated",
            "next_steps": [
                f"Upload backend code to {final_app_path}",
                "Run deploy_service to deploy the updated service",
            ],
            "message": f"Service {project}/{service} upgraded from {current_type} to {new_service_type}"
        }

    except Exception as e:
        return {
            "success": False,
            "error": "UPGRADE_FAILED",
            "message": f"Failed to upgrade service: {str(e)}"
        }


async def validate_upgrade_service_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for upgrade_service tool.

    Args:
        data: Input data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    required_fields = ["project", "service", "server", "new_service_type"]
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"

    # Validate types
    for field in required_fields:
        if not isinstance(data[field], str):
            return False, f"Field '{field}' must be a string"

    # Validate optional string fields
    if "app_path" in data and data["app_path"] is not None:
        if not isinstance(data["app_path"], str):
            return False, "Field 'app_path' must be a string"

    if "notes" in data and data["notes"] is not None:
        if not isinstance(data["notes"], str):
            return False, "Field 'notes' must be a string"

    return True, None
