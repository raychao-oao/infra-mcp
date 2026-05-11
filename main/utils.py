"""
Shared utility functions for Infrastructure MCP tools.
"""

import re
import shlex


# Hostname: lowercase alphanumeric, hyphens, dots only (RFC 952 / RFC 1123 subset)
_HOSTNAME_RE = re.compile(r'^[a-z0-9][a-z0-9.\-]{0,252}[a-z0-9]$')
# Safe path: no shell metacharacters (;|&`$<>()\n\r\x00 or unquoted space)
_UNSAFE_RE = re.compile(r'[;&|`$<>()\n\r\x00]')
# Safe identifier: project/service/server names (alphanumeric, hyphen, underscore)
_IDENTIFIER_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


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
        return systemd_config["service_name"]
    return f"{project}-{service}"
