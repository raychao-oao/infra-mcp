"""
validate_service_security MCP Tool Implementation

Validate service security configuration including:
- Docker port bindings (must bind to 127.0.0.1)
- Caddy configuration (must have bind 127.0.0.1)
- Actual listening ports verification
- Optional auto-fix capability
"""

import subprocess
import re

from main.config import INFRA_SERVERS
from main.utils import get_service_name, q
from typing import Optional, Dict, Any, List

from main.db.sqlite_store import SQLiteStore
from main.models.service_deployment import ServiceType
from main.providers.server_snapshot import ServerSnapshot
from main.providers.ssh_provider import run_command
from main.tools.check_listening_ports import _classify_address


async def validate_service_security(
    store: SQLiteStore,
    project: str,
    service: str,
    server: str,
    auto_fix: bool = False,
    snapshot: Optional[ServerSnapshot] = None
) -> Dict[str, Any]:
    """
    Validate service security configuration.

    Args:
        store: SQLiteStore instance
        project: Project name
        service: Service name
        server: VPS server name
        auto_fix: Whether to automatically fix issues
        snapshot: Pre-fetched server state. Callers auditing several services on
            the same host should fetch one and pass it in — otherwise every
            service pays for its own SSH round trip. Fetched on demand when None.

    Returns:
        Dict with validation results and security issues
    """

    # Get deployment
    deployment = await store.get_service_deployment(project, service, server)
    if not deployment:
        return {
            "success": False,
            "error": "SERVICE_NOT_FOUND",
            "message": f"Service {project}/{service} not found on {server}"
        }

    if snapshot is None:
        try:
            snapshot = ServerSnapshot.fetch(server)
        except Exception as e:
            return {
                "success": False,
                "error": "SNAPSHOT_FAILED",
                "message": f"Could not read state from {server}: {str(e)}"
            }

    issues = []
    checks = []
    fixed_issues = []

    service_type = deployment.service_type
    port = deployment.port

    svc_name = get_service_name(project, service, deployment.systemd_config)

    # Check 1: Caddy configuration
    caddy_files, located_by = snapshot.locate_caddy_configs(
        svc_name, deployment.hostname, port, deployment.static_path
    )
    caddy_check = await _check_caddy_config(
        server, snapshot, caddy_files, located_by, project, service, auto_fix
    )
    checks.append(caddy_check)
    if not caddy_check["passed"]:
        issues.extend(caddy_check["issues"])
        if auto_fix and caddy_check.get("fixed"):
            fixed_issues.extend(caddy_check["fixed"])

    # Check 2: Docker or systemd configuration
    if service_type == ServiceType.DOCKER:
        docker_check = await _check_docker_config(server, project, service, auto_fix)
        checks.append(docker_check)
        if not docker_check["passed"]:
            issues.extend(docker_check["issues"])
            if auto_fix and docker_check.get("fixed"):
                fixed_issues.extend(docker_check["fixed"])

    elif service_type in [ServiceType.FLASK, ServiceType.NODEJS, ServiceType.FLASK_STATIC]:
        # For systemd services, check if app binds to 127.0.0.1
        # This is typically in environment variables or config
        systemd_check = await _check_systemd_service(server, project, service, deployment.environment)
        checks.append(systemd_check)
        if not systemd_check["passed"]:
            issues.extend(systemd_check["issues"])

    # Check 3: Actual listening ports
    if port:
        port_check = _check_actual_port_binding(snapshot, port)
    else:
        # No port on record means the binding cannot be verified. Treat that as a
        # failed check, not a skipped one — "unknown" is not "safe". lion-punch/app
        # had port=None and was one of the services found exposed on 2026-07-27,
        # precisely because this check never ran for it.
        port_check = {
            "check": "actual_port_binding",
            "passed": False,
            "issues": [
                f"No port recorded for {project}/{service}, so its actual binding "
                f"could not be verified"
            ],
            "details": "Register the port with allocate_port to enable this check"
        }
    checks.append(port_check)
    if not port_check["passed"]:
        issues.extend(port_check["issues"])

    # Build result
    all_passed = len(issues) == 0
    security_status = "SECURE" if all_passed else "VULNERABLE"

    result = {
        "success": True,
        "project": project,
        "service": service,
        "server": server,
        "service_type": service_type.value,
        "security_status": security_status,
        "checks": checks,
        "issues": issues,
        "issues_count": len(issues)
    }

    if auto_fix:
        result["auto_fix_enabled"] = True
        result["fixed_issues"] = fixed_issues
        result["fixed_count"] = len(fixed_issues)

    if all_passed:
        result["message"] = f"✅ Service {project}/{service} security configuration validated successfully"
    else:
        result["message"] = f"⚠️ Found {len(issues)} security issue(s) in {project}/{service}"
        if auto_fix and fixed_issues:
            result["message"] += f" ({len(fixed_issues)} fixed)"

    return result


CADDY_SITES_DIR = "/etc/caddy/sites"


async def _check_caddy_config(
    server: str,
    snapshot: ServerSnapshot,
    caddy_files: List[str],
    located_by: str,
    project: str,
    service: str,
    auto_fix: bool
) -> Dict[str, Any]:
    """Check that every Caddy site serving this service has bind 127.0.0.1."""

    # No site file is not a security problem. Plenty of services are internal
    # only and deliberately have no Caddy entry; whether their port is exposed
    # is what _check_actual_port_binding decides. Failing here instead is what
    # produced a permanent false positive for every service.
    if not caddy_files:
        return {
            "check": "caddy_config",
            "passed": True,
            "details": (
                f"No Caddy site references {project}/{service} — nothing to "
                f"misconfigure (an internal-only service is expected to have none)"
            )
        }

    issues = []
    fixed = []
    checked = []

    for caddy_file in caddy_files:
        try:
            config_content = snapshot.caddy_files.get(caddy_file)

            if config_content is None:
                issues.append(f"Caddy config could not be read: {caddy_file}")
                continue

            if "bind 127.0.0.1" in config_content:
                checked.append(f"{caddy_file} (bound)")
                continue

            issue = f"Caddy config missing 'bind 127.0.0.1' directive in {caddy_file}"

            if auto_fix:
                fix_result = await _fix_caddy_bind(server, caddy_file, config_content)
                if fix_result["success"]:
                    issues.append(issue)
                    fixed.append(f"Added 'bind 127.0.0.1' to {caddy_file}")
                    continue

            issues.append(issue)
            checked.append(f"{caddy_file} (NOT bound)")

        except Exception as e:
            issues.append(f"Failed to check Caddy config {caddy_file}: {str(e)}")

    if issues:
        result_dict = {
            "check": "caddy_config",
            "passed": False,
            "issues": issues,
            "details": f"Located by {located_by}: {', '.join(checked) or 'read failed'}"
        }
        if fixed:
            result_dict["fixed"] = fixed
        return result_dict

    return {
        "check": "caddy_config",
        "passed": True,
        "details": f"Located by {located_by}: {', '.join(checked)}"
    }


async def _fix_caddy_bind(server: str, caddy_file: str, config_content: str) -> Dict[str, Any]:
    """Fix Caddy configuration by adding bind 127.0.0.1."""

    # Find the first line with a opening brace (server block start)
    lines = config_content.split('\n')
    for i, line in enumerate(lines):
        if '{' in line:
            # Add bind directive after opening brace
            try:
                result = run_command(
                    server,
                    f"sudo sed -i '{i+2}i\\    bind 127.0.0.1' {q(caddy_file)}",
                    timeout=10
                )

                if result.returncode == 0:
                    return {"success": True}

            except Exception:
                pass

            break

    return {"success": False}


async def _check_docker_config(
    server: str,
    project: str,
    service: str,
    auto_fix: bool
) -> Dict[str, Any]:
    """Check if Docker containers bind ports to 127.0.0.1."""

    # Find docker-compose.yml
    try:
        result = run_command(
            server,
            f"find ~/PRJ/{q(project)} -name 'docker-compose.y*ml' 2>/dev/null | head -1",
            timeout=10
        )

        if result.returncode != 0 or not result.stdout.strip():
            return {
                "check": "docker_config",
                "passed": True,
                "details": "No docker-compose.yml found (may not be a Docker service)"
            }

        compose_file = result.stdout.strip()

        # Read docker-compose.yml
        read_result = run_command(server, f"cat {q(compose_file)}", timeout=10)

        if read_result.returncode != 0:
            return {
                "check": "docker_config",
                "passed": False,
                "issues": [f"Failed to read {compose_file}"],
                "details": "Cannot read docker-compose.yml"
            }

        compose_content = read_result.stdout

        # Check for port bindings without 127.0.0.1
        # Pattern: "8080:8080" or "- 8080:8080" (without 127.0.0.1 prefix)
        bad_pattern = re.compile(r'^\s*-?\s*"?(\d+:\d+)"?\s*$', re.MULTILINE)
        bad_bindings = bad_pattern.findall(compose_content)

        if bad_bindings:
            issues = [f"Docker port binding without 127.0.0.1: {binding}" for binding in bad_bindings]

            return {
                "check": "docker_config",
                "passed": False,
                "issues": issues,
                "details": f"Found {len(bad_bindings)} port binding(s) without localhost restriction"
            }

        return {
            "check": "docker_config",
            "passed": True,
            "details": "All Docker port bindings correctly use 127.0.0.1"
        }

    except Exception as e:
        return {
            "check": "docker_config",
            "passed": False,
            "issues": [f"Failed to check Docker config: {str(e)}"],
            "details": str(e)
        }


async def _check_systemd_service(
    server: str,
    project: str,
    service: str,
    environment: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Check if systemd service binds to 127.0.0.1."""

    # Check environment variables for HOST binding
    if environment and "HOST" in environment:
        host = environment["HOST"]
        if host == "127.0.0.1":
            return {
                "check": "systemd_service",
                "passed": True,
                "details": "Service configured to bind to 127.0.0.1"
            }
        else:
            return {
                "check": "systemd_service",
                "passed": False,
                "issues": [f"Service HOST set to '{host}' instead of '127.0.0.1'"],
                "details": f"HOST environment variable: {host}"
            }

    # If no HOST in environment, assume it's okay (may be in app config)
    return {
        "check": "systemd_service",
        "passed": True,
        "details": "No HOST environment variable configured (check app config manually)"
    }


def _check_actual_port_binding(snapshot: ServerSnapshot, port: int) -> Dict[str, Any]:
    """Check the addresses actually bound to `port`, from the server snapshot."""

    try:
        bound = snapshot.listening_addresses(port)

        if not bound:
            # Not listening is not a security problem: a registered port whose
            # service is stopped is expected (temporary demos, deliberate shutdowns).
            return {
                "check": "actual_port_binding",
                "passed": True,
                "details": f"Port {port} not currently listening (service may be stopped)"
            }

        # Classify every listening address on this port, not the blob of output.
        # A substring test for "127.0.0.1:" passes as soon as *any* line is loopback,
        # so a service listening on both 127.0.0.1 and 0.0.0.0 slipped through; it
        # also flagged deliberate Tailscale binds as insecure.
        exposed = []
        addresses = []
        for addr in bound:
            level, note = _classify_address(addr)
            addresses.append(f"{addr} ({level})")
            if level in ("high", "unknown"):
                exposed.append(f"{addr}: {note}")

        if exposed:
            return {
                "check": "actual_port_binding",
                "passed": False,
                "issues": [f"Port {port} exposed — {e}" for e in exposed],
                "details": f"Listening addresses: {', '.join(addresses)}"
            }

        return {
            "check": "actual_port_binding",
            "passed": True,
            "details": f"Port {port} not publicly reachable: {', '.join(addresses)}"
        }

    except Exception as e:
        return {
            "check": "actual_port_binding",
            "passed": False,
            "issues": [f"Failed to check port binding: {str(e)}"],
            "details": str(e)
        }


async def validate_validate_service_security_input(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate input parameters for validate_service_security tool.

    Args:
        data: Input data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    required_fields = ["project", "service", "server"]
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
        if not isinstance(data[field], str):
            return False, f"Field '{field}' must be a string"

    valid_servers = INFRA_SERVERS
    if data["server"] not in valid_servers:
        return False, f"Invalid server. Must be one of: {', '.join(valid_servers)}"

    if "auto_fix" in data:
        if not isinstance(data["auto_fix"], bool):
            return False, "Field 'auto_fix' must be a boolean"

    return True, None
