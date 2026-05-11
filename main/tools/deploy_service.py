"""
deploy_service MCP Tool Implementation

Deploys a registered service to VPS via SSH.

Directory Structure Created:
- /var/www/{project}/          - Static files (root owned)
- ~/PRJ/{project}/             - Project directory
- ~/PRJ/{project}/www/         - Symlink to /var/www/{project}/
- ~/PRJ/{project}/app/         - Backend code
- ~/PRJ/{project}/data/        - Data directory
- ~/PRJ/{project}/config/      - Config files

Caddy Configuration:
- /etc/caddy/sites/{service_name}.caddy
- Main Caddyfile imports /etc/caddy/sites/*.caddy

DNS:
- Uses cloudflared CLI to create CNAME records (via SSH)
"""

import asyncio
import os
import secrets
from datetime import datetime
from typing import Optional, Dict, Any

from main.db.sqlite_store import SQLiteStore
from main.providers.ssh_provider import async_run_command
from main.tools.allocate_port import allocate_port
from main.utils import get_service_name, q, validate_hostname, validate_safe_string, validate_config_value, validate_identifier
from main.config import INFRA_SERVERS, INFRA_DEFAULT_SERVER

SSH_USER = os.getenv("SSH_USER", "ubuntu")


# VPS servers configuration
VPS_SERVERS = INFRA_SERVERS

# Server to tunnel name mapping
# Loaded from SERVER_TUNNEL_MAP env var: "prod:prod-main,staging:staging-main"
# Defaults to {server}-main convention if not set
_tunnel_map_raw = os.getenv("SERVER_TUNNEL_MAP", "")
TUNNEL_MAP: dict[str, str] = {}
for _entry in _tunnel_map_raw.split(","):
    if ":" in _entry:
        _k, _v = _entry.strip().split(":", 1)
        TUNNEL_MAP[_k.strip()] = _v.strip()

# Server that has cloudflared credentials for DNS management
DNS_SERVER = os.getenv("INFRA_DNS_SERVER", INFRA_DEFAULT_SERVER)


async def run_ssh_command(
    server: str,
    command: str,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Execute a command on VPS server (local or via SSH).

    Delegates to async_run_command from ssh_provider which handles
    local vs remote detection automatically.

    Args:
        server: VPS server name (configured in ~/.ssh/config)
        command: Command to execute
        timeout: Timeout in seconds

    Returns:
        Dict with success status, stdout, stderr
    """
    return await async_run_command(server, command, timeout)


async def write_file_via_ssh(
    server: str,
    file_path: str,
    content: str,
    sudo: bool = False
) -> Dict[str, Any]:
    """
    Write a file on VPS server via SSH.

    Args:
        server: VPS server name
        file_path: File path on remote server
        content: File content
        sudo: Whether to use sudo

    Returns:
        Dict with success status
    """
    # Use a random delimiter to prevent content from escaping the heredoc
    delimiter = f"EOF_{secrets.token_hex(16)}"
    # Regenerate until the delimiter does not appear in content (astronomically unlikely)
    while delimiter in content:
        delimiter = f"EOF_{secrets.token_hex(16)}"

    if sudo:
        # Write to temp file first, then sudo move
        temp_file = f"/tmp/deploy_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}"
        cmd = f"cat > {q(temp_file)} << '{delimiter}'\n{content}\n{delimiter}"
        result = await run_ssh_command(server, cmd)
        if not result["success"]:
            return result

        move_cmd = f"sudo mv {q(temp_file)} {q(file_path)}"
        return await run_ssh_command(server, move_cmd)
    else:
        cmd = f"cat > {q(file_path)} << '{delimiter}'\n{content}\n{delimiter}"
        return await run_ssh_command(server, cmd)


async def create_directories(
    server: str,
    project: str,
    service_type: str,
    static_path: str,
    app_path: Optional[str]
) -> Dict[str, Any]:
    """
    Create unified directory structure on VPS.

    Args:
        server: VPS server name
        project: Project name
        service_type: Service type
        static_path: Static files path (e.g., /var/www/project/)
        app_path: App code path (e.g., ~/PRJ/project/app/)

    Returns:
        Dict with success status and created directories
    """
    created_dirs = []
    errors = []

    # 1. Create /var/www/{project}/ with sudo
    result = await run_ssh_command(
        server,
        f"sudo mkdir -p {q(static_path)} && sudo chown {q(SSH_USER)}:{q(SSH_USER)} {q(static_path)}"
    )
    if result["success"]:
        created_dirs.append(static_path)
    else:
        errors.append(f"Failed to create {static_path}: {result.get('stderr', result.get('message'))}")

    # 2. Create ~/PRJ/{project}/ structure
    prj_base = f"~/PRJ/{project}"
    result = await run_ssh_command(
        server,
        f"mkdir -p {q(prj_base)}"
    )
    if result["success"]:
        created_dirs.append(prj_base)
    else:
        errors.append(f"Failed to create {prj_base}: {result.get('stderr', result.get('message'))}")

    # 3. Create symlink ~/PRJ/{project}/www -> /var/www/{project}/
    symlink_path = f"{prj_base}/www"
    result = await run_ssh_command(
        server,
        f"ln -sfn {q(static_path)} {q(symlink_path)}"
    )
    if result["success"]:
        created_dirs.append(f"{symlink_path} -> {static_path}")
    else:
        errors.append(f"Failed to create symlink: {result.get('stderr', result.get('message'))}")

    # 4. Create app directory if needed (non-static services)
    if service_type != "static" and app_path:
        result = await run_ssh_command(
            server,
            f"mkdir -p {q(app_path)}"
        )
        if result["success"]:
            created_dirs.append(app_path)
        else:
            errors.append(f"Failed to create {app_path}: {result.get('stderr', result.get('message'))}")

    # 5. Create data and config directories
    for subdir in ["data", "config"]:
        dir_path = f"{prj_base}/{subdir}"
        result = await run_ssh_command(
            server,
            f"mkdir -p {dir_path}"
        )
        if result["success"]:
            created_dirs.append(dir_path)

    # 6. Create log directory with sudo
    log_dir = f"/var/log/{project}"
    result = await run_ssh_command(
        server,
        f"sudo mkdir -p {q(log_dir)} && sudo chown {q(SSH_USER)}:{q(SSH_USER)} {q(log_dir)}"
    )
    if result["success"]:
        created_dirs.append(log_dir)

    if errors:
        return {
            "success": False,
            "error": "DIRECTORY_CREATION_PARTIAL",
            "created": created_dirs,
            "errors": errors,
        }

    return {
        "success": True,
        "created": created_dirs,
    }


async def create_dns_via_cloudflared(
    hostname: str,
    tunnel_name: str,
    dns_server: str = DNS_SERVER
) -> Dict[str, Any]:
    """
    Create DNS CNAME record using cloudflared CLI via SSH.

    Args:
        hostname: Full hostname (e.g., 'app.your-domain.com')
        tunnel_name: Tunnel name (e.g., 'prod-main')
        dns_server: Server with cloudflared credentials

    Returns:
        Dict with success status
    """
    cmd = f"cloudflared tunnel route dns {q(tunnel_name)} {q(hostname)}"
    result = await run_ssh_command(dns_server, cmd, timeout=60)

    if result["success"]:
        return {
            "success": True,
            "hostname": hostname,
            "tunnel_name": tunnel_name,
            "message": f"DNS CNAME created: {hostname} -> {tunnel_name}",
        }
    else:
        # Check if record already exists
        stderr = result.get("stderr", "")
        if "already exists" in stderr.lower() or "record already exists" in stderr.lower():
            return {
                "success": True,
                "hostname": hostname,
                "tunnel_name": tunnel_name,
                "message": f"DNS record already exists for {hostname}",
                "note": "existing_record",
            }
        return {
            "success": False,
            "error": "DNS_CREATION_FAILED",
            "message": result.get("stderr") or result.get("message"),
        }


async def generate_and_write_caddy_config(
    server: str,
    deployment,
) -> Dict[str, Any]:
    """
    Generate and write Caddy configuration file.

    Args:
        server: VPS server name
        deployment: ServiceDeployment instance

    Returns:
        Dict with success status and config details
    """
    if not deployment.hostname:
        return {
            "success": False,
            "error": "NO_HOSTNAME",
            "message": "No hostname configured for service"
        }

    try:
        validate_hostname(deployment.hostname)
        if deployment.static_path:
            validate_config_value(deployment.static_path, "static_path")
        if deployment.log_path:
            validate_config_value(deployment.log_path, "log_path")
    except ValueError as e:
        return {"success": False, "error": "INVALID_CONFIG_VALUE", "message": str(e)}

    # Generate Caddy config based on service type
    config_lines = [f"{deployment.hostname}:80 {{"]

    service_type = deployment.service_type.value

    if service_type == "static":
        # Static files only
        config_lines.append(f"    root * {deployment.static_path}")
        config_lines.append(f"    try_files {{path}} /index.html")
        config_lines.append(f"    file_server")

    elif service_type == "flask+static":
        # API routes to Flask, everything else to static
        config_lines.append(f"    handle /api/* {{")
        config_lines.append(f"        reverse_proxy localhost:{deployment.port}")
        config_lines.append(f"    }}")
        config_lines.append(f"    handle /* {{")
        config_lines.append(f"        root * {deployment.static_path}")
        config_lines.append(f"        try_files {{path}} /index.html")
        config_lines.append(f"        file_server")
        config_lines.append(f"    }}")

    elif service_type in ["flask", "nodejs", "docker"]:
        # Reverse proxy to backend
        config_lines.append(f"    reverse_proxy localhost:{deployment.port}")

    # Add logging
    log_file = deployment.log_path or f"/var/log/{deployment.project}/access.log"
    config_lines.append(f"    log {{")
    config_lines.append(f"        output file {log_file}")
    config_lines.append(f"    }}")

    config_lines.append("}")

    config_content = "\n".join(config_lines)
    svc_name = get_service_name(deployment.project, deployment.service, deployment.systemd_config)
    config_file = f"/etc/caddy/sites/{svc_name}.caddy"

    # Write config file
    result = await write_file_via_ssh(server, config_file, config_content, sudo=True)

    if not result["success"]:
        return {
            "success": False,
            "error": "WRITE_FAILED",
            "message": f"Failed to write Caddy config: {result.get('stderr', result.get('message'))}",
        }

    return {
        "success": True,
        "config_file": config_file,
        "config_content": config_content,
    }


async def reload_caddy(server: str) -> Dict[str, Any]:
    """
    Reload Caddy on VPS server.

    Args:
        server: VPS server name

    Returns:
        Dict with success status
    """
    result = await run_ssh_command(server, "sudo systemctl reload caddy", timeout=30)

    if not result["success"]:
        # Try restart if reload fails
        result = await run_ssh_command(server, "sudo systemctl restart caddy", timeout=30)

    return result


async def generate_and_write_systemd_service(
    server: str,
    deployment,
) -> Dict[str, Any]:
    """
    Generate and write systemd service file.

    Args:
        server: VPS server name
        deployment: ServiceDeployment instance

    Returns:
        Dict with success status and service details
    """
    service_type = deployment.service_type.value
    service_name = get_service_name(deployment.project, deployment.service, deployment.systemd_config)

    # Validate values that go into config file content (not shell commands)
    try:
        if deployment.app_path:
            validate_config_value(deployment.app_path, "app_path")
        if deployment.environment:
            for key, value in deployment.environment.items():
                validate_identifier(key, "environment key")
                validate_config_value(str(value), f"environment value for {key}")
    except ValueError as e:
        return {"success": False, "error": "INVALID_CONFIG_VALUE", "message": str(e)}

    if service_type in ["flask", "flask+static"]:
        # Flask service
        service_content = f"""[Unit]
Description={deployment.project} {deployment.service} - Flask Application
After=network.target

[Service]
Type=simple
User={SSH_USER}
WorkingDirectory={deployment.app_path.replace('~', f'/home/{SSH_USER}')}
Environment="PORT={deployment.port}"
"""
        # Add environment variables
        if deployment.environment:
            for key, value in deployment.environment.items():
                service_content += f'Environment="{key}={value}"\n'

        service_content += f"""ExecStart=/usr/bin/python3 app.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""

    elif service_type == "nodejs":
        # Node.js service
        service_content = f"""[Unit]
Description={deployment.project} {deployment.service} - Node.js Application
After=network.target

[Service]
Type=simple
User={SSH_USER}
WorkingDirectory={deployment.app_path.replace('~', f'/home/{SSH_USER}')}
Environment="PORT={deployment.port}"
"""
        if deployment.environment:
            for key, value in deployment.environment.items():
                service_content += f'Environment="{key}={value}"\n'

        service_content += f"""ExecStart=/usr/bin/node index.js
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""

    else:
        return {
            "success": False,
            "error": "NO_SYSTEMD_NEEDED",
            "message": f"Service type '{service_type}' does not need systemd service"
        }

    service_file = f"/etc/systemd/system/{service_name}.service"

    # Write service file
    result = await write_file_via_ssh(server, service_file, service_content, sudo=True)

    if not result["success"]:
        return {
            "success": False,
            "error": "WRITE_FAILED",
            "message": f"Failed to write systemd service: {result.get('stderr', result.get('message'))}",
        }

    # Reload systemd daemon
    await run_ssh_command(server, "sudo systemctl daemon-reload")

    return {
        "success": True,
        "service_name": service_name,
        "service_file": service_file,
        "service_content": service_content,
    }


async def start_systemd_service(
    server: str,
    service_name: str,
    enable: bool = True
) -> Dict[str, Any]:
    """
    Start (and optionally enable) a systemd service.

    Args:
        server: VPS server name
        service_name: Systemd service name
        enable: Whether to enable the service for auto-start

    Returns:
        Dict with success status
    """
    if enable:
        result = await run_ssh_command(
            server,
            f"sudo systemctl enable --now {q(service_name)}",
            timeout=30
        )
    else:
        result = await run_ssh_command(
            server,
            f"sudo systemctl start {q(service_name)}",
            timeout=30
        )

    return result


async def deploy_service(
    store: SQLiteStore,
    project: str,
    service: str,
    server: str,
    cloudflare_api_token: Optional[str] = None,
    cloudflare_account_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deploy a registered service to VPS.

    Steps:
    1. Check service is registered
    2. Create directories on VPS
    3. Allocate port if needed (non-static services)
    4. Add DNS CNAME record via cloudflared
    5. Generate and write Caddy configuration
    6. Reload Caddy
    7. Generate systemd service (for Flask/Node.js apps)
    8. Start application service
    9. Update status: registered -> deployed

    Args:
        store: SQLiteStore instance
        project: Project name
        service: Service name
        server: VPS server name
        cloudflare_api_token: Unused (kept for compatibility)
        cloudflare_account_id: Unused (kept for compatibility)

    Returns:
        Dict with success status and deployment details
    """

    # Validate server
    if server not in VPS_SERVERS:
        return {
            "success": False,
            "error": "INVALID_SERVER",
            "message": f"Server '{server}' must be one of {VPS_SERVERS}"
        }

    # Get service deployment
    deployment = await store.get_service_deployment(project, service, server)
    if not deployment:
        return {
            "success": False,
            "error": "SERVICE_NOT_REGISTERED",
            "message": f"Service {project}/{service} is not registered on {server}. Please register first using register_service."
        }

    # Check status
    if deployment.status.value == "deployed":
        return {
            "success": False,
            "error": "ALREADY_DEPLOYED",
            "message": f"Service {project}/{service} is already deployed on {server}",
            "deployment_id": deployment.deployment_id
        }

    steps_completed = []
    deployment_info = {}
    service_type = deployment.service_type.value

    try:
        # Step 1: Create directories
        dir_result = await create_directories(
            server=server,
            project=project,
            service_type=service_type,
            static_path=deployment.static_path,
            app_path=deployment.app_path
        )

        if not dir_result["success"]:
            return {
                "success": False,
                "error": "DIRECTORY_CREATION_FAILED",
                "message": "Failed to create directories",
                "details": dir_result,
            }

        steps_completed.append("directories_created")
        deployment_info["directories"] = dir_result["created"]

        # Step 2: Allocate port if needed (non-static services)
        if service_type != "static" and not deployment.port:
            port_result = await allocate_port(
                store=store,
                project=project,
                service=service,
                server=server
            )

            if not port_result["success"]:
                return {
                    "success": False,
                    "error": "PORT_ALLOCATION_FAILED",
                    "message": f"Failed to allocate port: {port_result.get('message')}",
                    "steps_completed": steps_completed,
                    "details": port_result
                }

            # Update deployment with port
            await store.update_service_status(
                deployment.deployment_id,
                deployment.status.value,
                port=port_result["allocated_port"]
            )

            # Refresh deployment
            deployment = await store.get_service_deployment(project, service, server)
            if deployment is None:
                return {
                    "success": False,
                    "error": "DEPLOYMENT_NOT_FOUND",
                    "message": "Deployment record disappeared after port allocation",
                    "steps_completed": steps_completed,
                }
            steps_completed.append("port_allocated")
            deployment_info["port"] = deployment.port

        elif deployment.port:
            deployment_info["port"] = deployment.port
            steps_completed.append("port_already_allocated")

        # Step 3: Add DNS CNAME record via cloudflared
        if deployment.hostname:
            tunnel_name = TUNNEL_MAP.get(server, f"{server}-main")
            if tunnel_name:
                dns_result = await create_dns_via_cloudflared(
                    hostname=deployment.hostname,
                    tunnel_name=tunnel_name,
                    dns_server=DNS_SERVER
                )

                if not dns_result["success"]:
                    return {
                        "success": False,
                        "error": "DNS_RECORD_FAILED",
                        "message": f"Failed to add DNS record: {dns_result.get('message')}",
                        "steps_completed": steps_completed,
                        "details": dns_result
                    }

                steps_completed.append("dns_record_added")
                deployment_info["dns"] = dns_result

        # Step 4: Generate and write Caddy config
        caddy_result = await generate_and_write_caddy_config(
            server=server,
            deployment=deployment
        )

        if not caddy_result["success"]:
            return {
                "success": False,
                "error": "CADDY_CONFIG_FAILED",
                "message": f"Failed to write Caddy config: {caddy_result.get('message')}",
                "steps_completed": steps_completed,
                "details": caddy_result
            }

        steps_completed.append("caddy_config_written")
        deployment_info["caddy_config"] = caddy_result["config_file"]

        # Step 5: Reload Caddy
        reload_result = await reload_caddy(server)

        if not reload_result["success"]:
            return {
                "success": False,
                "error": "CADDY_RELOAD_FAILED",
                "message": f"Failed to reload Caddy: {reload_result.get('stderr', reload_result.get('message'))}",
                "steps_completed": steps_completed,
            }

        steps_completed.append("caddy_reloaded")

        # Step 6: Generate systemd service (for Flask/Node.js)
        if service_type in ["flask", "nodejs", "flask+static"]:
            systemd_result = await generate_and_write_systemd_service(
                server=server,
                deployment=deployment
            )

            if systemd_result["success"]:
                steps_completed.append("systemd_service_created")
                deployment_info["systemd_service"] = systemd_result["service_name"]

                # Step 7: Start service
                start_result = await start_systemd_service(
                    server=server,
                    service_name=systemd_result["service_name"]
                )

                if start_result["success"]:
                    steps_completed.append("service_started")
                else:
                    # Service start failed, but deployment still succeeded
                    deployment_info["service_start_error"] = start_result.get("stderr", "Failed to start")

        # Step 8: Update deployment status
        await store.update_service_status(
            deployment.deployment_id,
            "deployed"
        )
        steps_completed.append("status_updated")

        # Get updated deployment
        deployment = await store.get_service_deployment(project, service, server)
        if deployment is None:
            return {
                "success": False,
                "error": "DEPLOYMENT_NOT_FOUND",
                "message": "Deployment record not found after status update",
                "steps_completed": steps_completed,
            }

        return {
            "success": True,
            "deployment_id": deployment.deployment_id,
            "project": deployment.project,
            "service": deployment.service,
            "server": deployment.server,
            "service_type": service_type,
            "status": deployment.status.value,
            "deployed_at": deployment.deployed_at.isoformat() if deployment.deployed_at else None,
            "steps_completed": steps_completed,
            "deployment_info": deployment_info,
            "access_url": f"https://{deployment.hostname}" if deployment.hostname else None,
            "message": f"Service {project}/{service} successfully deployed on {server}"
        }

    except Exception as e:
        return {
            "success": False,
            "error": "DEPLOYMENT_FAILED",
            "message": f"Deployment failed: {str(e)}",
            "steps_completed": steps_completed,
            "deployment_info": deployment_info
        }


async def validate_deploy_service_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for deploy_service tool.

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
