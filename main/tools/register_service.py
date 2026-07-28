"""
register_service MCP Tool Implementation

This tool ONLY allocates the standard layer: it decides project_root/deploy_root
by convention (or accepts caller-supplied overrides) and writes
layer=ServiceLayer.STANDARD. It does not deploy anything and does not describe
services that already exist elsewhere — for those, use `record_service`
(nonstandard layer; paths are observations, not decisions).

Unified Directory Structure (standard layer, derived by main.utils.resolve_paths):
- /var/www/{project}/          - Static files (actual location; deploy_root)
- ~/PRJ/{project}/             - Project root (project_root)
- ~/PRJ/{project}/app/         - Backend code (Flask/Node.js)

Port Allocation:
- static: No port needed
- flask/nodejs/docker/flask+static: Port allocated on deploy
"""

from datetime import datetime
from typing import Optional, Dict, Any
import re

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore
from main.models.service_deployment import ServiceLayer
from main.utils import resolve_paths


# Service types that actually serve files from disk. Only these get a
# deploy_root by default.
FILE_SERVING_TYPES = {"static", "flask+static"}


async def register_service(
    store: SQLiteStore,
    project: str,
    service: str,
    server: str,
    service_type: str,
    port: Optional[int] = None,
    hostname: Optional[str] = None,
    tunnel_name: Optional[str] = None,
    project_root: Optional[str] = None,
    deploy_root: Optional[str] = None,
    path_overrides: Optional[Dict] = None,
    workspace_url: Optional[str] = None,
    caddy_rules: Optional[Dict] = None,
    environment: Optional[Dict] = None,
    systemd_config: Optional[Dict] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Register a service deployment configuration (standard layer, allocation only).

    Args:
        store: SQLiteStore instance
        project: Project name (e.g., 'pac', 'monitoring')
        service: Service name (e.g., 'dashboard', 'uptime-kuma')
        server: VPS server name (e.g., 'prod')
        service_type: Service type ('flask', 'nodejs', 'static', 'docker', 'flask+static')
        port: Port number (optional, can be allocated later)
        hostname: Public hostname (optional, e.g., 'app.your-domain.com')
        tunnel_name: Cloudflare tunnel name (optional)
        project_root: Project root path (default: '~/PRJ/{project}/')
        deploy_root: Static file deploy root (default: '/var/www/{project}/' for
            file-serving service types; None otherwise)
        path_overrides: Dict of sub-path overrides keyed by
            app/static/data/config/log
        workspace_url: Private workspace repo URL (optional)
        caddy_rules: Caddy routing rules as dict
        environment: Environment variables as dict
        systemd_config: Systemd service configuration as dict
        notes: Optional notes

    Returns:
        Dict with success status and deployment details or error information
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

    # Allocate roots by convention unless the caller overrode them.
    final_project_root = project_root or f"~/PRJ/{project}/"
    final_deploy_root = deploy_root or (
        f"/var/www/{project}/" if service_type in FILE_SERVING_TYPES else None
    )

    # Static services don't need port
    # Port will be allocated during deploy for flask/nodejs/docker/flask+static
    final_port = port if service_type != "static" else None

    # Generate deployment ID
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    deployment_id = f"deploy_{project}_{service}_{server}_{timestamp}"

    # Register the service
    try:
        deployment = await store.register_service(
            deployment_id=deployment_id,
            project=project,
            service=service,
            server=server,
            service_type=service_type,
            port=final_port,
            hostname=hostname,
            tunnel_name=tunnel_name,
            layer=ServiceLayer.STANDARD,
            project_root=final_project_root,
            deploy_root=final_deploy_root,
            path_overrides=path_overrides,
            workspace_url=workspace_url,
            caddy_rules=caddy_rules,
            environment=environment,
            systemd_config=systemd_config,
            notes=notes
        )

        resolved = resolve_paths(deployment)

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
            "message": f"Service {project}/{service} registered on {server}",
            "port_info": "Port will be allocated during deploy" if service_type != "static" and not final_port else (
                "Static service - no port needed" if service_type == "static" else f"Port {final_port} specified"
            ),
            "directory_structure": resolved
        }

    except Exception as e:
        return {
            "success": False,
            "error": "REGISTRATION_FAILED",
            "message": f"Failed to register service: {str(e)}"
        }


async def validate_register_service_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for register_service tool.

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
    string_fields = ["hostname", "tunnel_name", "project_root", "deploy_root",
                     "workspace_url", "notes"]
    for field in string_fields:
        if field in data and data[field] is not None:
            if not isinstance(data[field], str):
                return False, f"Field '{field}' must be a string"

    # Validate that user-supplied paths are project-scoped and safe
    from main.utils import validate_project_path, validate_safe_string
    project = data.get("project", "")
    path_fields = ["project_root", "deploy_root"]
    for field in path_fields:
        if data.get(field):
            try:
                validate_project_path(data[field], project, field)
            except ValueError as e:
                return False, str(e)

    # Validate path_overrides: dict of sub-path key -> project-scoped path
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
                validate_project_path(value, project, f"path_overrides.{key}")
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
