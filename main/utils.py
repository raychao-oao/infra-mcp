"""
Shared utility functions for Infrastructure MCP tools.
"""

import os
import re
import shlex

from main.models.service_deployment import ServiceLayer


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

    Requires the path to be under one of the known allowed roots with the project
    name as the exact first subdirectory component — e.g. /var/www/{project}/...
    or ~/PRJ/{project}/...  A substring match like "project in path" is NOT
    sufficient because /etc/myproject-data would pass it.
    """
    if "\x00" in path:
        raise ValueError(f"Invalid {field}: null byte not allowed")

    # Normalize to collapse .. and extra slashes before any check
    normalized = os.path.normpath(path.lstrip("~"))  # strip leading ~ for normpath
    if ".." in normalized.split(os.sep):
        raise ValueError(f"Invalid {field}: path traversal (..) not allowed")

    # Allowed roots and the expected pattern after them
    # Format: (prefix_to_strip, path_must_start_with_after_strip)
    # For tilde paths we compare the expanded form; for absolute we use literal prefix.
    def _starts_with_component(p: str, root: str, project: str) -> bool:
        """Return True if p starts with root/{project}/ or equals root/{project}."""
        base = root.rstrip("/") + "/" + project
        return p == base or p.startswith(base + "/")

    is_valid = (
        _starts_with_component(path, "/var/www", project)
        or _starts_with_component(path, "/var/log", project)
        or _starts_with_component(path, "~/PRJ", project)
        or _starts_with_component(path, "/tmp", project)  # for internal temp usage
    )

    if not is_valid:
        raise ValueError(
            f"Invalid {field}: path must be under /var/www/{project}/, "
            f"/var/log/{project}/, or ~/PRJ/{project}/"
        )

    # Belt-and-suspenders: also block any absolute path that hits a dangerous prefix
    if path.startswith("/"):
        for prefix in _DANGEROUS_PATH_PREFIXES:
            if path.startswith(prefix):
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


def resolve_paths(deployment) -> dict:
    """Derive concrete sub-paths from roots + convention + overrides.

    The DB stores roots and exceptions only; every consumer that needs a
    concrete sub-path goes through here. NONSTANDARD layers derive nothing —
    a path we did not allocate is an observation, and observations live in
    path_overrides or nowhere.
    """
    paths = {"app": None, "static": None, "data": None, "config": None, "log": None}
    stype = deployment.service_type.value if hasattr(deployment.service_type, "value") else deployment.service_type

    if deployment.layer == ServiceLayer.STANDARD and deployment.project_root:
        root = deployment.project_root.rstrip("/")
        if stype != "static":
            paths["app"] = f"{root}/app/"
        paths["data"] = f"{root}/data/"
        paths["config"] = f"{root}/config/"
        paths["log"] = f"/var/log/{deployment.project}/"

    if deployment.deploy_root:
        paths["static"] = deployment.deploy_root

    for key, value in (deployment.path_overrides or {}).items():
        if key in paths:
            paths[key] = value
    return paths
