"""
SQLite implementation of ResourceStore
"""

import os
from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from .base import ResourceStore
from main.config import INFRA_DEFAULT_SERVER
from main.models.port_allocation import Base as PortBase, PortAllocation, AllocationStatus
from main.models.main_tunnel import Base as MainTunnelBase, MainTunnel, MainTunnelStatus
from main.models.service_deployment import Base as ServiceBase, ServiceDeployment, DeploymentStatus, ServiceType


class SQLiteStore(ResourceStore):
    """SQLite implementation of resource storage."""

    def __init__(self, database_url: str = "sqlite:///./configs/resources.db"):
        """
        Initialize SQLite store.

        Args:
            database_url: Database URL (e.g., "sqlite:///./configs/resources.db")
        """
        self.database_url = database_url

        # Convert to async URL if needed
        if database_url.startswith("sqlite:///"):
            # For SQLite, use aiosqlite
            async_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
        else:
            async_url = database_url

        self.engine = create_async_engine(async_url, echo=False)
        self.SessionLocal = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def initialize(self):
        """Initialize database and create tables."""
        print(f"📊 Initializing SQLite database: {self.database_url}")

        # Create configs directory if it doesn't exist
        db_path = self.database_url.replace("sqlite:///", "").replace("sqlite+aiosqlite:///", "")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # Create tables
        async with self.engine.begin() as conn:
            await conn.run_sync(PortBase.metadata.create_all)
            await conn.run_sync(MainTunnelBase.metadata.create_all)
            await conn.run_sync(ServiceBase.metadata.create_all)

        print("✅ Database initialized")

    async def close(self):
        """Close database connection."""
        await self.engine.dispose()
        print("👋 Database connection closed")

    # Port operations

    async def allocate_port(
        self,
        allocation_id: str,
        port: int,
        project: str,
        service: str,
        server: str = INFRA_DEFAULT_SERVER,
        notes: Optional[str] = None
    ) -> PortAllocation:
        """Allocate a port."""
        async with self.SessionLocal() as session:
            allocation = PortAllocation(
                allocation_id=allocation_id,
                port=port,
                project=project,
                service=service,
                server=server,
                allocated_at=datetime.utcnow(),
                status=AllocationStatus.ALLOCATED,
                notes=notes
            )
            session.add(allocation)
            await session.commit()
            await session.refresh(allocation)
            return allocation

    async def get_port_allocation(self, port: int, server: str = INFRA_DEFAULT_SERVER) -> Optional[PortAllocation]:
        """Get port allocation by port number."""
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(PortAllocation).where(
                    PortAllocation.port == port,
                    PortAllocation.server == server,
                    PortAllocation.status != AllocationStatus.RELEASED
                )
            )
            return result.scalar_one_or_none()

    async def list_port_allocations(
        self,
        project: Optional[str] = None,
        server: Optional[str] = None
    ) -> List[PortAllocation]:
        """List all port allocations."""
        async with self.SessionLocal() as session:
            query = select(PortAllocation).where(
                PortAllocation.status != AllocationStatus.RELEASED
            )

            if project:
                query = query.where(PortAllocation.project == project)
            if server:
                query = query.where(PortAllocation.server == server)

            result = await session.execute(query)
            return list(result.scalars().all())

    async def is_port_available(self, port: int, server: str = INFRA_DEFAULT_SERVER) -> bool:
        """Check if a port is available."""
        allocation = await self.get_port_allocation(port, server)
        return allocation is None

    async def release_port(self, port: int, server: str = INFRA_DEFAULT_SERVER) -> Optional[PortAllocation]:
        """Release a port allocation."""
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(PortAllocation).where(
                    PortAllocation.port == port,
                    PortAllocation.server == server,
                    PortAllocation.status != AllocationStatus.RELEASED
                )
            )
            allocation = result.scalar_one_or_none()

            if allocation:
                allocation.status = AllocationStatus.RELEASED
                await session.commit()
                await session.refresh(allocation)
                return allocation
            return None

    # Main Tunnel operations (one per VPS)

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
    ) -> MainTunnel:
        """Register a main tunnel (one per VPS)."""
        async with self.SessionLocal() as session:
            tunnel = MainTunnel(
                tunnel_name=tunnel_name,
                cloudflare_tunnel_id=cloudflare_tunnel_id,
                vps_server=vps_server,
                tunnel_target=tunnel_target,
                credentials_file=credentials_file,
                config_file=config_file,
                systemd_service=systemd_service,
                status=MainTunnelStatus.ACTIVE,
                created_at=datetime.utcnow(),
                notes=notes
            )
            session.add(tunnel)
            await session.commit()
            await session.refresh(tunnel)
            return tunnel

    async def get_main_tunnel(self, tunnel_name: str) -> Optional[MainTunnel]:
        """Get main tunnel by name."""
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(MainTunnel).where(
                    MainTunnel.tunnel_name == tunnel_name
                )
            )
            return result.scalar_one_or_none()

    async def get_main_tunnel_by_vps(self, vps_server: str) -> Optional[MainTunnel]:
        """Get main tunnel by VPS server."""
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(MainTunnel).where(
                    MainTunnel.vps_server == vps_server
                )
            )
            return result.scalar_one_or_none()

    async def list_main_tunnels(
        self,
        vps_server: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[MainTunnel]:
        """List all main tunnels."""
        async with self.SessionLocal() as session:
            query = select(MainTunnel)

            if vps_server:
                query = query.where(MainTunnel.vps_server == vps_server)
            if status:
                query = query.where(MainTunnel.status == MainTunnelStatus(status))

            result = await session.execute(query)
            return list(result.scalars().all())

    async def update_main_tunnel_status(
        self,
        tunnel_name: str,
        status: str
    ) -> Optional[MainTunnel]:
        """Update main tunnel status."""
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(MainTunnel).where(
                    MainTunnel.tunnel_name == tunnel_name
                )
            )
            tunnel = result.scalar_one_or_none()

            if tunnel:
                tunnel.status = MainTunnelStatus(status)
                tunnel.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(tunnel)
                return tunnel
            return None

    # Service deployment operations

    async def register_service(
        self,
        deployment_id: str,
        project: str,
        service: str,
        server: str,
        service_type: str,
        **kwargs
    ) -> ServiceDeployment:
        """Register a service deployment."""
        async with self.SessionLocal() as session:
            deployment = ServiceDeployment(
                deployment_id=deployment_id,
                project=project,
                service=service,
                server=server,
                service_type=ServiceType(service_type),
                registered_at=datetime.utcnow(),
                status=DeploymentStatus.REGISTERED,
                **kwargs
            )
            session.add(deployment)
            await session.commit()
            await session.refresh(deployment)
            return deployment

    async def get_service_deployment(
        self,
        project: str,
        service: str,
        server: str
    ) -> Optional[ServiceDeployment]:
        """Get service deployment by project, service, and server."""
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(ServiceDeployment).where(
                    ServiceDeployment.project == project,
                    ServiceDeployment.service == service,
                    ServiceDeployment.server == server,
                    ServiceDeployment.status != DeploymentStatus.PURGED
                )
            )
            return result.scalar_one_or_none()

    async def list_service_deployments(
        self,
        project: Optional[str] = None,
        server: Optional[str] = None,
        status: Optional[str] = None,
        include_purged: bool = False
    ) -> List[ServiceDeployment]:
        """List all service deployments."""
        async with self.SessionLocal() as session:
            query = select(ServiceDeployment)

            if not include_purged:
                query = query.where(ServiceDeployment.status != DeploymentStatus.PURGED)

            if project:
                query = query.where(ServiceDeployment.project == project)
            if server:
                query = query.where(ServiceDeployment.server == server)
            if status:
                query = query.where(ServiceDeployment.status == DeploymentStatus(status))

            result = await session.execute(query)
            return list(result.scalars().all())

    async def update_service_status(
        self,
        deployment_id: str,
        status: str,
        **kwargs
    ) -> Optional[ServiceDeployment]:
        """Update service deployment status."""
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(ServiceDeployment).where(
                    ServiceDeployment.deployment_id == deployment_id
                )
            )
            deployment = result.scalar_one_or_none()

            if deployment:
                deployment.status = DeploymentStatus(status)

                # Update timestamp based on status
                if status == "deployed":
                    deployment.deployed_at = datetime.utcnow()
                elif status == "stopped":
                    deployment.stopped_at = datetime.utcnow()
                elif status == "archived":
                    deployment.archived_at = datetime.utcnow()
                elif status == "purged":
                    deployment.purged_at = datetime.utcnow()

                # Update other fields if provided
                for key, value in kwargs.items():
                    if hasattr(deployment, key):
                        setattr(deployment, key, value)

                await session.commit()
                await session.refresh(deployment)
                return deployment
            return None

    async def update_service_deployment(
        self,
        deployment_id: str,
        service_type: Optional[str] = None,
        port: Optional[int] = None,
        hostname: Optional[str] = None,
        tunnel_name: Optional[str] = None,
        app_path: Optional[str] = None,
        static_path: Optional[str] = None,
        data_path: Optional[str] = None,
        log_path: Optional[str] = None,
        config_path: Optional[str] = None,
        caddy_rules: Optional[dict] = None,
        environment: Optional[dict] = None,
        systemd_config: Optional[dict] = None,
        notes: Optional[str] = None,
        **kwargs
    ) -> Optional[ServiceDeployment]:
        """
        Update service deployment configuration.

        Used for:
        - Upgrading service type (e.g., static -> flask+static)
        - Updating paths and configuration
        """
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(ServiceDeployment).where(
                    ServiceDeployment.deployment_id == deployment_id
                )
            )
            deployment = result.scalar_one_or_none()

            if deployment:
                # Update fields if provided
                if service_type is not None:
                    deployment.service_type = ServiceType(service_type)
                if port is not None:
                    deployment.port = port
                if hostname is not None:
                    deployment.hostname = hostname
                if tunnel_name is not None:
                    deployment.tunnel_name = tunnel_name
                if app_path is not None:
                    deployment.app_path = app_path
                if static_path is not None:
                    deployment.static_path = static_path
                if data_path is not None:
                    deployment.data_path = data_path
                if log_path is not None:
                    deployment.log_path = log_path
                if config_path is not None:
                    deployment.config_path = config_path
                if caddy_rules is not None:
                    deployment.caddy_rules = caddy_rules
                if environment is not None:
                    deployment.environment = environment
                if systemd_config is not None:
                    deployment.systemd_config = systemd_config
                if notes is not None:
                    deployment.notes = notes

                await session.commit()
                await session.refresh(deployment)
                return deployment
            return None
