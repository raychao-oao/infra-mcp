"""
validate_service_security MCP Tool Implementation

Validate service security configuration including:
- Docker port bindings (must bind to 127.0.0.1)
- Caddy configuration (must have bind 127.0.0.1)
- Actual listening ports verification
- Optional auto-fix capability
"""

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
    unverified = []
    checks = []
    fixed_issues = []

    def record(check: Dict[str, Any]) -> None:
        """
        File a check's output.

        A failed check that could not reach a conclusion goes to `unverified`,
        not `issues`. Conflating "I found a problem" with "I could not check"
        is what turns a security tool into background noise — the same reason
        the Caddy check was ignored while services sat exposed.
        """
        checks.append(check)
        if check["passed"]:
            return
        if check.get("unverified"):
            unverified.extend(check.get("issues", []))
        else:
            issues.extend(check.get("issues", []))
        if auto_fix and check.get("fixed"):
            fixed_issues.extend(check["fixed"])

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
    record(caddy_check)

    # Check 2: Docker or systemd configuration
    if service_type == ServiceType.DOCKER:
        record(await _check_docker_config(server, project, service, auto_fix))

    elif service_type in [ServiceType.FLASK, ServiceType.NODEJS, ServiceType.FLASK_STATIC]:
        # What address the unit is *configured* to bind. This is the only signal
        # for a service that is not currently running, which is exactly when the
        # live binding check has nothing to say.
        record(_check_systemd_service(
            snapshot, svc_name, project,
            is_listening=bool(port and snapshot.listening_addresses(port))
        ))

    # Check 3: Actual listening ports
    if port:
        record(_check_actual_port_binding(snapshot, port))
    elif service_type == ServiceType.STATIC:
        # A static site has no backend port — Caddy serves the files itself.
        # Reporting that as "could not verify" is a warning about a deliberate
        # state, which is how a report stops being read.
        record({
            "check": "actual_port_binding",
            "passed": True,
            "details": "Static service — served directly by Caddy, no backend port to bind",
        })
    else:
        # No port on record means the binding cannot be verified. Not a silent
        # skip — one of the services found exposed on 2026-07-27 had port=None,
        # and stayed hidden precisely because this check never ran for it — but a
        # gap in the records is not itself a vulnerability.
        record({
            "check": "actual_port_binding",
            "passed": False,
            "unverified": True,
            "issues": [
                f"No port recorded for {project}/{service}, so its actual binding "
                f"could not be verified"
            ],
            "details": "Register the port with allocate_port to enable this check"
        })

    # Build result. Three outcomes, because "could not check" is neither a clean
    # bill of health nor a finding.
    if issues:
        security_status = "VULNERABLE"
    elif unverified:
        security_status = "UNVERIFIED"
    else:
        security_status = "SECURE"

    result = {
        "success": True,
        "project": project,
        "service": service,
        "server": server,
        "service_type": service_type.value,
        "security_status": security_status,
        "checks": checks,
        "issues": issues,
        "unverified": unverified,
        "unverified_count": len(unverified),
        "issues_count": len(issues)
    }

    if auto_fix:
        result["auto_fix_enabled"] = True
        result["fixed_issues"] = fixed_issues
        result["fixed_count"] = len(fixed_issues)

    if issues:
        result["message"] = f"⚠️ Found {len(issues)} security issue(s) in {project}/{service}"
        if auto_fix and fixed_issues:
            result["message"] += f" ({len(fixed_issues)} fixed)"
        if unverified:
            result["message"] += f", {len(unverified)} check(s) could not be verified"
    elif unverified:
        result["message"] = (
            f"❓ No issues found in {project}/{service}, but {len(unverified)} "
            f"check(s) could not be verified"
        )
    else:
        result["message"] = f"✅ Service {project}/{service} security configuration validated successfully"

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


# Bind-address flags, in the forms the servers here actually use:
# uvicorn/hypercorn `--host H`, gunicorn `--bind H:P`, and the short `-b H:P`.
_HOST_FLAG_RE = re.compile(r"--host[= ]([^\s]+)")
_BIND_FLAG_RE = re.compile(r"(?:--bind|-b)[= ]([^\s]+)")

# Environment keys used for a bind address across these projects. There is no
# single convention — nemo and jeeves use BIND_HOST, website-tools SERVER_HOST,
# doc-extract plain HOST — so all of them are consulted.
_HOST_ENV_KEYS = ("BIND_HOST", "SERVER_HOST", "HOST")


def _check_systemd_service(
    snapshot: ServerSnapshot,
    svc_name: str,
    project: str,
    is_listening: bool
) -> Dict[str, Any]:
    """
    Check what address the unit is configured to bind.

    This reads the unit file and its EnvironmentFile off the server rather than
    the `environment` metadata in the database, and it resolves the ExecStart
    command line, because that is where the real answer lives:

      - The old check looked for a key named HOST. The convention in these
        projects is BIND_HOST, so it never matched anything.
      - Not finding a key returned passed=True. Absence of information was
        being reported as a clean bill of health.
      - It could not see a CLI argument overriding the environment. That is the
        trap that hid two exposed services: `--host 0.0.0.0` in ExecStart wins
        over BIND_HOST in .env, so editing .env changed nothing and looked
        correct in the database all along.
    """
    unit_path = snapshot.locate_unit(svc_name, project)

    if unit_path is None:
        return _systemd_unverified(
            f"No systemd unit found for {project}/{svc_name} on {snapshot.server}",
            is_listening
        )

    unit = snapshot.unit_files[unit_path]

    env = snapshot.env_for_unit(unit_path)

    exec_start = ""
    for line in unit.split("\n"):
        if line.startswith("ExecStart="):
            exec_start = line[len("ExecStart="):]
            break

    raw_host = None
    source = None

    match = _HOST_FLAG_RE.search(exec_start)
    if match:
        raw_host, source = match.group(1), "ExecStart --host"
    else:
        match = _BIND_FLAG_RE.search(exec_start)
        if match:
            # gunicorn takes HOST:PORT; rpartition keeps IPv6 literals intact.
            raw_host = match.group(1).rpartition(":")[0] or match.group(1)
            source = "ExecStart --bind"

    if raw_host is None:
        # No flag: the app reads its own address from the environment.
        for key in _HOST_ENV_KEYS:
            if key in env:
                raw_host, source = env[key], f"{key} in EnvironmentFile"
                break

    if raw_host is None:
        return _systemd_unverified(
            f"No bind address in {unit_path} or its EnvironmentFile", is_listening
        )

    host = _expand_env(raw_host, env)
    if host is None:
        return _systemd_unverified(
            f"{source} is {raw_host}, which is not defined in the EnvironmentFile",
            is_listening
        )

    issues = []
    level, note = _classify_address(host)
    if level in ("high", "unknown"):
        issues.append(f"Configured to bind {host} ({source}) — {note}")

    # The trap that hid two exposed services: a hardcoded --host silently wins
    # over the environment, so .env can say 127.0.0.1 while the process binds
    # 0.0.0.0. Flag the contradiction even when the effective value is safe,
    # because editing .env will appear to work and won't.
    if source and source.startswith("ExecStart") and "$" not in raw_host:
        for key in _HOST_ENV_KEYS:
            if key in env and env[key] != host:
                issues.append(
                    f"{key}={env[key]} in the EnvironmentFile has no effect: "
                    f"{source} hardcodes {host} and overrides it"
                )
                break

    if issues:
        return {
            "check": "systemd_service",
            "passed": False,
            "issues": issues,
            "details": f"{source}: {raw_host} -> {host}"
        }

    return {
        "check": "systemd_service",
        "passed": True,
        "details": f"Binds {host} ({source})"
    }


def _expand_env(value: str, env: Dict[str, str]) -> Optional[str]:
    """
    Resolve ${VAR} / $VAR against the unit's environment.

    Returns None when a referenced variable is undefined — systemd expands that
    to an empty string, so the service would fail to start rather than bind
    something unexpected, but either way it cannot be vouched for.
    """
    def replace(match):
        return env.get(match.group(1) or match.group(2), "\x00")

    expanded = re.sub(r"\$\{(\w+)\}|\$(\w+)", replace, value)
    return None if "\x00" in expanded else expanded


def _systemd_unverified(reason: str, is_listening: bool) -> Dict[str, Any]:
    """
    Report a unit whose configured bind address could not be determined.

    Three-way rather than pass/fail. If the service is listening,
    _check_actual_port_binding has the authoritative answer and this check adds
    nothing, so it passes. If it is not listening, nothing else can speak for
    it — but "could not check" is not "found a problem", and reporting it as a
    vulnerability is how a tool teaches people to ignore it. It is surfaced as
    unverified instead: visible, never silently passed, never miscounted as a
    finding.
    """
    if is_listening:
        return {
            "check": "systemd_service",
            "passed": True,
            "details": f"{reason} — actual binding verified from listening sockets instead"
        }
    return {
        "check": "systemd_service",
        "passed": False,
        "unverified": True,
        "issues": [f"Cannot verify bind address and the service is not running: {reason}"],
        "details": reason
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
