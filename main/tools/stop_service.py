"""
stop_service MCP Tool Implementation
"""

from typing import Optional, Dict, Any

from main.db.sqlite_store import SQLiteStore
from main.utils import get_service_name


async def stop_service(
    store: SQLiteStore,
    project: str,
    service: str,
    server: str
) -> Dict[str, Any]:
    """
    Stop a running service (keeps configuration and files).

    Steps:
    1. Check service is deployed
    2. Stop systemd service (if applicable)
    3. Update status: deployed → stopped

    Args:
        store: SQLiteStore instance
        project: Project name
        service: Service name
        server: VPS server name

    Returns:
        Dict with success status and service details or error information
    """

    # Get service deployment
    deployment = await store.get_service_deployment(project, service, server)
    if not deployment:
        return {
            "success": False,
            "error": "SERVICE_NOT_FOUND",
            "message": f"Service {project}/{service} not found on {server}"
        }

    # Check status
    if deployment.status.value == "stopped":
        return {
            "success": False,
            "error": "ALREADY_STOPPED",
            "message": f"Service {project}/{service} is already stopped on {server}",
            "deployment_id": deployment.deployment_id
        }

    if deployment.status.value != "deployed":
        return {
            "success": False,
            "error": "INVALID_STATUS",
            "message": f"Service {project}/{service} is in '{deployment.status.value}' status. Only deployed services can be stopped.",
            "deployment_id": deployment.deployment_id
        }

    steps_completed = []

    try:
        # Stop systemd service (if Flask/Node.js)
        if deployment.service_type.value in ["flask", "nodejs", "flask+static"]:
            service_name = get_service_name(project, service, deployment.systemd_config)

            stop_result = await stop_systemd_service(
                service_name=service_name,
                server=server
            )

            if not stop_result["success"]:
                return {
                    "success": False,
                    "error": "SERVICE_STOP_FAILED",
                    "message": f"Failed to stop service: {stop_result.get('message')}",
                    "details": stop_result
                }

            steps_completed.append("systemd_service_stopped")

        # Update deployment status to stopped
        await store.update_service_status(
            deployment.deployment_id,
            "stopped"
        )
        steps_completed.append("status_updated_to_stopped")

        # Get updated deployment
        deployment = await store.get_service_deployment(project, service, server)

        return {
            "success": True,
            "deployment_id": deployment.deployment_id,
            "project": deployment.project,
            "service": deployment.service,
            "server": deployment.server,
            "status": deployment.status.value,
            "stopped_at": deployment.stopped_at.isoformat() if deployment.stopped_at else None,
            "steps_completed": steps_completed,
            "message": f"Service {project}/{service} stopped on {server}. Configuration and files preserved."
        }

    except Exception as e:
        return {
            "success": False,
            "error": "STOP_FAILED",
            "message": f"Failed to stop service: {str(e)}",
            "steps_completed": steps_completed
        }


async def stop_systemd_service(
    service_name: str,
    server: str
) -> Dict[str, Any]:
    """
    Stop systemd service on VPS server.

    Args:
        service_name: Systemd service name
        server: VPS server name

    Returns:
        Dict with success status
    """

    from main.providers.ssh_provider import async_run_command
    from main.utils import q

    try:
        result = await async_run_command(server, f"sudo systemctl stop {q(service_name)}")
        if not result["success"]:
            return {
                "success": False,
                "error": "STOP_FAILED",
                "message": f"Failed to stop {service_name}: {result.get('stderr', result.get('message'))}",
            }
        return {
            "success": True,
            "service_name": service_name,
            "message": f"Service {service_name} stopped on {server}",
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to stop service: {str(e)}"
        }


async def validate_stop_service_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for stop_service tool.

    Args:
        data: Input data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    required_fields = ["project", "service", "server"]
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"

    # Validate types
    if not isinstance(data["project"], str):
        return False, "Field 'project' must be a string"

    if not isinstance(data["service"], str):
        return False, "Field 'service' must be a string"

    if not isinstance(data["server"], str):
        return False, "Field 'server' must be a string"

    return True, None
