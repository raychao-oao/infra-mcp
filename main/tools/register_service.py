"""
register_service MCP Tool Implementation

Unified Directory Structure:
- /var/www/{project}/          - Static files (actual location)
- ~/PRJ/{project}/www/         - Symlink to /var/www/{project}/
- ~/PRJ/{project}/app/         - Backend code (Flask/Node.js)

Port Allocation:
- static: No port needed
- flask/nodejs/docker/flask+static: Port allocated on deploy
"""

from datetime import datetime
from typing import Optional, Dict, Any
import re
import json

from main.config import INFRA_SERVERS
from main.db.sqlite_store import SQLiteStore


# Service types that actually serve files from disk. Only these get a
# static_path by default — see _generate_default_paths.
STATIC_SERVING_TYPES = {"static", "flask+static"}


def _generate_default_paths(project: str, service_type: str) -> Dict[str, Optional[str]]:
    """
    Generate default paths based on unified directory structure.

    Only for paths this project's deploy step really creates, and only where the
    service type implies them. A record is a description of reality; inventing a
    path is not a harmless default:

    - `static_path` on a pure flask/nodejs/docker service made deploy_service
      create `/var/www/{project}/` and symlink `~/PRJ/{project}/www` to it, for a
      service with no static files at all.
    - `log_path` was defaulted to `/var/log/{project}/`, which nothing creates —
      so purge_service would offer to delete a directory that never existed, and
      get_service_info reported it as if it did.
    - `app_path`/`data_path`/`config_path` under `~/PRJ/{project}/` are only real
      because deploy_service creates them. A **docker** service is not deployed
      that way — it comes up from a compose file wherever its author put it.
      Registering one produced `~/PRJ/{project}/app/` on a host with no `~/PRJ`
      directory at all.

    Args:
        project: Project name
        service_type: Service type

    Returns:
        Dict with default paths; None means "unknown, do not guess"
    """
    paths: Dict[str, Optional[str]] = {
        "static_path": None,
        "app_path": None,
        "data_path": None,
        "log_path": None,
        "config_path": None,
    }

    # Docker services are brought up from a compose file that this server never
    # placed and cannot locate. Guess nothing; let the caller say where it is.
    if service_type == "docker":
        return paths

    if service_type in STATIC_SERVING_TYPES:
        paths["static_path"] = f"/var/www/{project}/"

    paths["data_path"] = f"~/PRJ/{project}/data/"
    paths["config_path"] = f"~/PRJ/{project}/config/"

    # Static-only services don't need app_path
    if service_type != "static":
        paths["app_path"] = f"~/PRJ/{project}/app/"

    return paths


async def register_service(
    store: SQLiteStore,
    project: str,
    service: str,
    server: str,
    service_type: str,
    port: Optional[int] = None,
    hostname: Optional[str] = None,
    tunnel_name: Optional[str] = None,
    app_path: Optional[str] = None,
    static_path: Optional[str] = None,
    data_path: Optional[str] = None,
    log_path: Optional[str] = None,
    config_path: Optional[str] = None,
    caddy_rules: Optional[Dict] = None,
    environment: Optional[Dict] = None,
    systemd_config: Optional[Dict] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Register a service deployment configuration.

    Args:
        store: SQLiteStore instance
        project: Project name (e.g., 'pac', 'monitoring')
        service: Service name (e.g., 'dashboard', 'uptime-kuma')
        server: VPS server name (e.g., 'prod')
        service_type: Service type ('flask', 'nodejs', 'static', 'docker', 'flask+static')
        port: Port number (optional, can be allocated later)
        hostname: Public hostname (optional, e.g., 'app.your-domain.com')
        tunnel_name: Cloudflare tunnel name (optional)
        app_path: Application code path (e.g., '~/PRJ/PAC/dashboard/flask_app/')
        static_path: Static files path (e.g., '/var/www/pac/')
        data_path: Data directory
        log_path: Log directory
        config_path: Config files path
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

    # Generate default paths based on unified directory structure
    default_paths = _generate_default_paths(project, service_type)

    # Use provided paths or fall back to defaults
    final_static_path = static_path or default_paths["static_path"]
    final_app_path = app_path or default_paths["app_path"]
    final_data_path = data_path or default_paths["data_path"]
    final_log_path = log_path or default_paths["log_path"]
    final_config_path = config_path or default_paths["config_path"]

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
            app_path=final_app_path,
            static_path=final_static_path,
            data_path=final_data_path,
            log_path=final_log_path,
            config_path=final_config_path,
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
                "app_path": deployment.app_path,
                "static_path": deployment.static_path,
                "data_path": deployment.data_path,
                "log_path": deployment.log_path,
                "config_path": deployment.config_path,
                "caddy_rules": deployment.caddy_rules,
                "environment": deployment.environment,
                "systemd_config": deployment.systemd_config
            },
            "notes": deployment.notes,
            "message": f"Service {project}/{service} registered on {server}",
            "port_info": "Port will be allocated during deploy" if service_type != "static" and not final_port else (
                "Static service - no port needed" if service_type == "static" else f"Port {final_port} specified"
            ),
            "directory_structure": {
                "static_files": final_static_path,
                "app_code": final_app_path,
                "symlink": (
                    f"~/PRJ/{project}/www/ -> {final_static_path}"
                    if final_static_path else None
                ),
            }
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
    string_fields = ["hostname", "tunnel_name", "app_path", "static_path",
                     "data_path", "log_path", "config_path", "notes"]
    for field in string_fields:
        if field in data and data[field] is not None:
            if not isinstance(data[field], str):
                return False, f"Field '{field}' must be a string"

    # Validate that user-supplied paths are project-scoped and safe
    from main.utils import validate_project_path
    project = data.get("project", "")
    path_fields = ["app_path", "static_path", "data_path", "log_path", "config_path"]
    for field in path_fields:
        if data.get(field):
            try:
                validate_project_path(data[field], project, field)
            except ValueError as e:
                return False, str(e)

    # Validate optional dict fields
    dict_fields = ["caddy_rules", "environment", "systemd_config"]
    for field in dict_fields:
        if field in data and data[field] is not None:
            if not isinstance(data[field], dict):
                return False, f"Field '{field}' must be a dict/object"

    return True, None
