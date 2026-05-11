"""
Shared utility functions for Infrastructure MCP tools.
"""

import re
import shlex


# Hostname: lowercase alphanumeric, hyphens, dots only (RFC 952 / RFC 1123 subset)
_HOSTNAME_RE = re.compile(r'^[a-z0-9][a-z0-9.\-]{0,252}[a-z0-9]$')
# Safe path: no shell metacharacters (;|&`$<>()\n\r\x00 or unquoted space)
_UNSAFE_RE = re.compile(r'[;&|`$<>()\n\r\x00]')
# Safe config value: no characters that break config file quoting (newlines, quotes, NUL)
_CONFIG_UNSAFE_RE = re.compile(r'[\n\r\x00"\'\\]')
# Safe identifier: project/service/server names (alphanumeric, hyphen, underscore)
_IDENTIFIER_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
# Safe systemd unit name: alphanumeric plus hyphen, underscore, dot, @ — no slash, no ..
_SERVICE_NAME_RE = re.compile(r'^[A-Za-z0-9_.@-]{1,128}$')
# Dangerous filesystem path prefixes that must never be touched via user-supplied paths
_DANGEROUS_PATH_PREFIXES = (
    "/etc/", "/root/", "/sys/", "/proc/", "/dev/", "/boot/",
    "/usr/", "/bin/", "/sbin/", "/lib/", "/lib64/",
)


def q(s: str) -> str:
    """shlex.quote shorthand — safely quote a string for use in a shell command."""
    return shlex.quote(str(s))


def validate_hostname(hostname: str) -> str:
    """Raise ValueError if hostname contains unsafe characters."""
    if not _HOSTNAME_RE.match(hostname.lower()):
        raise ValueError(f"Invalid hostname: {hostname!r}")
    return hostname


def validate_identifier(value: str, field: str = "name") -> str:
    """Raise ValueError if value is not a safe alphanumeric identifier."""
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid {field}: {value!r} (alphanumeric, hyphen, underscore only)")
    return value


def validate_safe_string(value: str, field: str = "value") -> str:
    """Raise ValueError if value contains shell metacharacters."""
    if _UNSAFE_RE.search(value):
        raise ValueError(f"Invalid {field}: contains unsafe characters")
    return value


def validate_config_value(value: str, field: str = "value") -> str:
    """Raise ValueError if value contains characters unsafe in config file contexts.

    Rejects newlines, quotes, and backslashes that could escape out of
    Caddy/systemd config values.
    """
    if _CONFIG_UNSAFE_RE.search(value):
        raise ValueError(f"Invalid {field}: contains characters not allowed in config files")
    return value


def validate_service_name(name: str, field: str = "service_name") -> str:
    """Raise ValueError if name is not a safe systemd unit name.

    Rejects slashes and path traversal that could write to arbitrary /etc/ paths.
    """
    if "/" in name or ".." in name:
        raise ValueError(f"Invalid {field}: {name!r} (path separators not allowed)")
    if not _SERVICE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid {field}: {name!r} (alphanumeric, hyphens, underscores, dots, @ only, max 128 chars)"
        )
    return name


def validate_project_path(path: str, project: str, field: str = "path") -> str:
    """Raise ValueError if path is not safely scoped to the given project.

    Guards against path traversal and accidental targeting of system directories
    in register_service and purge_service operations.
    """
    if "\x00" in path:
        raise ValueError(f"Invalid {field}: null byte not allowed")
    # Reject traversal components
    parts = path.replace("\\", "/").split("/")
    if ".." in parts:
        raise ValueError(f"Invalid {field}: path traversal (..) not allowed")
    # Must contain the project name so purge/chown stays scoped
    if project not in path:
        raise ValueError(f"Invalid {field}: path must be scoped to project '{project}'")
    # Block system directories
    resolved = path if path.startswith("/") else path
    for prefix in _DANGEROUS_PATH_PREFIXES:
        if resolved.startswith(prefix):
            raise ValueError(f"Invalid {field}: path cannot target system directory {prefix}")
    return path


def get_service_name(project: str, service: str, systemd_config: dict | None = None) -> str:
    """
    Get the actual systemd/caddy service name.

    Checks systemd_config.service_name first, falls back to {project}-{service}.

    Args:
        project: Project name
        service: Service name
        systemd_config: Optional systemd_config dict from deployment

    Returns:
        Service name string
    """
    if systemd_config and isinstance(systemd_config, dict) and systemd_config.get("service_name"):
        name = systemd_config["service_name"]
        return validate_service_name(name)
    return f"{project}-{service}"
