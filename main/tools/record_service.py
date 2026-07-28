"""
record_service MCP Tool Implementation

This tool records the non-standard layer: services that already exist,
built and deployed by their own project — infra-mcp did not allocate their
resources and does not derive paths for them. Every path field is an
observation the caller reports; nothing is defaulted. For services this
server owns and deploys, use `register_service` instead.
"""

from datetime import datetime
from typing import Optional, Dict, Any
import re

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore
from main.models.service_deployment import ServiceLayer


async def record_service(
    store: SQLiteStore,
    project: str,
    service: str,
    server: str,
    service_type: str,
    port: Optional[int] = None,
    hostname: Optional[str] = None,
    tunnel_name: Optional[str] = None,
    project_root: Optional[str] = None,
    path_overrides: Optional[Dict] = None,
    workspace_url: Optional[str] = None,
    caddy_rules: Optional[Dict] = None,
    environment: Optional[Dict] = None,
    systemd_config: Optional[Dict] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Record a service deployment observation (non-standard layer only).

    Args:
        store: SQLiteStore instance
        project: Project name (e.g., 'rss-stack', 'monitoring')
        service: Service name (e.g., 'caddy', 'app')
        server: VPS server name (e.g., 'prod', 'staging')
        service_type: Service type ('flask', 'nodejs', 'static', 'docker', 'flask+static')
        port: Port number observed in use (optional)
        hostname: Public hostname observed (optional)
        tunnel_name: Cloudflare tunnel name observed (optional)
        project_root: Observed project root path (no default; None if not observed)
        path_overrides: Dict of observed sub-path locations keyed by
            app/static/data/config/log
        workspace_url: Observed source-of-truth repo URL (optional)
        caddy_rules: Observed Caddy routing rules as dict
        environment: Observed environment variables as dict
        systemd_config: Observed systemd service configuration as dict
        notes: Optional notes

    Returns:
        Dict with success status and recorded details or error information
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

    # Validate server
    valid_servers = INFRA_SERVERS
    if server not in valid_servers:
        return {
            "success": False,
            "error": "INVALID_SERVER",
            "message": f"Server '{server}' must be one of {valid_servers}"
        }

    # Validate service type
    valid_types = ["flask", "nodejs", "static", "docker", "flask+static"]
    if service_type not in valid_types:
        return {
            "success": False,
            "error": "INVALID_SERVICE_TYPE",
            "message": f"Service type '{service_type}' must be one of {valid_types}"
        }

    # Check if service already registered
    existing = await store.get_service_deployment(project, service, server)
    if existing:
        return {
            "success": False,
            "error": "SERVICE_ALREADY_REGISTERED",
            "message": f"Service {project}/{service} is already registered on {server}",
            "existing_deployment": {
                "deployment_id": existing.deployment_id,
                "status": existing.status.value,
                "registered_at": existing.registered_at.isoformat()
            }
        }

    # Generate deployment ID
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    deployment_id = f"deploy_{project}_{service}_{server}_{timestamp}"

    # Record the observation — no path is derived or defaulted.
    try:
        deployment = await store.register_service(
            deployment_id=deployment_id,
            project=project,
            service=service,
            server=server,
            service_type=service_type,
            port=port,
            hostname=hostname,
            tunnel_name=tunnel_name,
            layer=ServiceLayer.NONSTANDARD,
            project_root=project_root,
            deploy_root=None,
            path_overrides=path_overrides,
            workspace_url=workspace_url,
            caddy_rules=caddy_rules,
            environment=environment,
            systemd_config=systemd_config,
            notes=notes
        )

        return {
            "success": True,
            "deployment_id": deployment.deployment_id,
            "project": deployment.project,
            "service": deployment.service,
            "server": deployment.server,
            "service_type": deployment.service_type.value,
            "status": deployment.status.value,
            "registered_at": deployment.registered_at.isoformat(),
            "configuration": {
                "port": deployment.port,
                "hostname": deployment.hostname,
                "tunnel_name": deployment.tunnel_name,
                "layer": deployment.layer.value,
                "project_root": deployment.project_root,
                "deploy_root": deployment.deploy_root,
                "path_overrides": deployment.path_overrides,
                "workspace_url": deployment.workspace_url,
                "caddy_rules": deployment.caddy_rules,
                "environment": deployment.environment,
                "systemd_config": deployment.systemd_config
            },
            "notes": deployment.notes,
            "message": f"Service {project}/{service} recorded on {server}"
        }

    except Exception as e:
        return {
            "success": False,
            "error": "RECORDING_FAILED",
            "message": f"Failed to record service: {str(e)}"
        }


async def validate_record_service_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for record_service tool.

    Args:
        data: Input data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    required_fields = ["project", "service", "server", "service_type"]
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

    if not isinstance(data["service_type"], str):
        return False, "Field 'service_type' must be a string"

    # Validate optional integer fields
    if "port" in data and data["port"] is not None:
        if not isinstance(data["port"], int):
            return False, "Field 'port' must be an integer"

    # Validate optional string fields
    string_fields = ["hostname", "tunnel_name", "workspace_url", "notes"]
    for field in string_fields:
        if field in data and data[field] is not None:
            if not isinstance(data[field], str):
                return False, f"Field '{field}' must be a string"

    # Validate that observed paths are safe (no project-scope confinement —
    # non-standard-layer paths live wherever their author put them).
    from main.utils import validate_recorded_path, validate_safe_string

    if data.get("project_root") is not None:
        if not isinstance(data["project_root"], str):
            return False, "Field 'project_root' must be a string"
        try:
            validate_recorded_path(data["project_root"], "project_root")
        except ValueError as e:
            return False, str(e)

    # Validate path_overrides: dict of sub-path key -> observed path
    if "path_overrides" in data and data["path_overrides"] is not None:
        overrides = data["path_overrides"]
        if not isinstance(overrides, dict):
            return False, "Field 'path_overrides' must be a dict/object"
        allowed_keys = {"app", "static", "data", "config", "log"}
        for key, value in overrides.items():
            if key not in allowed_keys:
                return False, f"Invalid path_overrides key '{key}': must be one of {sorted(allowed_keys)}"
            if not isinstance(value, str):
                return False, f"path_overrides['{key}'] must be a string"
            try:
                validate_recorded_path(value, f"path_overrides.{key}")
            except ValueError as e:
                return False, str(e)

    # Validate workspace_url
    if data.get("workspace_url"):
        try:
            validate_safe_string(data["workspace_url"], "workspace_url")
        except ValueError as e:
            return False, str(e)

    # Validate optional dict fields
    dict_fields = ["caddy_rules", "environment", "systemd_config"]
    for field in dict_fields:
        if field in data and data[field] is not None:
            if not isinstance(data[field], dict):
                return False, f"Field '{field}' must be a dict/object"

    return True, None
