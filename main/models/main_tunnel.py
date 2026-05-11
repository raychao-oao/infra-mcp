"""
Main Tunnel Data Model

Represents actual Cloudflare Tunnels (one per VPS).
This is different from service routes - each VPS has exactly one main tunnel,
and services are routed through Caddy on that tunnel.

Architecture:
    MainTunnel (one per VPS)
    └── prod-main (xxxxxxxx-...)
        └── All traffic goes to Caddy (port 80)
            ├── infra.your-domain.com → :8000
            ├── app.your-domain.com → :3000
            └── api.your-domain.com → :8080
"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base
import enum

Base = declarative_base()


class MainTunnelStatus(str, enum.Enum):
    """Main tunnel status."""
    ACTIVE = "active"              # Running and healthy
    INACTIVE = "inactive"          # Registered but not running
    FAILED = "failed"              # Error state


class MainTunnel(Base):
    """
    Main Tunnel record.

    Each VPS has exactly one main tunnel that routes all traffic to Caddy.
    Services are configured in Caddy, not in the tunnel itself.
    """

    __tablename__ = "main_tunnels"

    # Primary key - tunnel name (e.g., "prod-main")
    tunnel_name = Column(String, primary_key=True)

    # Cloudflare Tunnel UUID (e.g., "ce87659b-4df1-4787-b516-263b628aadf9")
    cloudflare_tunnel_id = Column(String, nullable=False, unique=True)

    # VPS server name (e.g., "prod", "staging")
    vps_server = Column(String, nullable=False, unique=True, index=True)

    # Tunnel target (e.g., "ce87659b-4df1-4787-b516-263b628aadf9.cfargotunnel.com")
    tunnel_target = Column(String, nullable=True)

    # Credentials file path (e.g., "~/.cloudflared/<uuid>.json")
    credentials_file = Column(String, nullable=True)

    # Config file path (e.g., "~/.cloudflared/config.yml")
    config_file = Column(String, nullable=True)

    # Systemd service name (e.g., "cloudflared-prod-main")
    systemd_service = Column(String, nullable=True)

    # Status
    status = Column(Enum(MainTunnelStatus), nullable=False, default=MainTunnelStatus.ACTIVE)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)

    # Notes
    notes = Column(String, nullable=True)

    def __repr__(self):
        return f"<MainTunnel(name={self.tunnel_name}, vps={self.vps_server}, status={self.status})>"

    def to_dict(self):
        """Convert to dictionary."""
        return {
            "tunnel_name": self.tunnel_name,
            "cloudflare_tunnel_id": self.cloudflare_tunnel_id,
            "vps_server": self.vps_server,
            "tunnel_target": self.tunnel_target,
            "credentials_file": self.credentials_file,
            "config_file": self.config_file,
            "systemd_service": self.systemd_service,
            "status": self.status.value if self.status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "notes": self.notes,
        }
