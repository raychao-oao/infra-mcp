"""
Database base interface
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from main.config import INFRA_DEFAULT_SERVER


class ResourceStore(ABC):
    """Abstract base class for resource storage."""

    @abstractmethod
    async def initialize(self):
        """Initialize database connection and create tables."""
        pass

    @abstractmethod
    async def close(self):
        """Close database connection."""
        pass

    # Port operations
    @abstractmethod
    async def allocate_port(
        self,
        allocation_id: str,
        port: int,
        project: str,
        service: str,
        server: str = INFRA_DEFAULT_SERVER,
        notes: Optional[str] = None
    ):
        """Allocate a port."""
        pass

    @abstractmethod
    async def get_port_allocation(self, port: int, server: str = INFRA_DEFAULT_SERVER):
        """Get port allocation by port number."""
        pass

    @abstractmethod
    async def list_port_allocations(self, project: Optional[str] = None, server: Optional[str] = None):
        """List all port allocations."""
        pass

    @abstractmethod
    async def is_port_available(self, port: int, server: str = INFRA_DEFAULT_SERVER) -> bool:
        """Check if a port is available."""
        pass

    @abstractmethod
    async def release_port(self, port: int, server: str = INFRA_DEFAULT_SERVER):
        """Release a port allocation."""
        pass

    # Main Tunnel operations (one per VPS)
    @abstractmethod
    async def register_main_tunnel(
        self,
        tunnel_name: str,
        cloudflare_tunnel_id: str,
        vps_server: str,
        tunnel_target: Optional[str] = None,
        credentials_file: Optional[str] = None,
        config_file: Optional[str] = None,
        systemd_service: Optional[str] = None,
        notes: Optional[str] = None
    ):
        """Register a main tunnel (one per VPS)."""
        pass

    @abstractmethod
    async def get_main_tunnel(self, tunnel_name: str):
        """Get main tunnel by name."""
        pass

    @abstractmethod
    async def get_main_tunnel_by_vps(self, vps_server: str):
        """Get main tunnel by VPS server."""
        pass

    @abstractmethod
    async def list_main_tunnels(
        self,
        vps_server: Optional[str] = None,
        status: Optional[str] = None
    ):
        """List all main tunnels."""
        pass

    @abstractmethod
    async def update_main_tunnel_status(self, tunnel_name: str, status: str):
        """Update main tunnel status."""
        pass
