"""
Shared utility functions for Infrastructure MCP tools.
"""


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
