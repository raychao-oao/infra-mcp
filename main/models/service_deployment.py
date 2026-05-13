"""
Service Deployment Data Model
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Enum, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
import enum

Base = declarative_base()


class DeploymentStatus(str, enum.Enum):
    """Service deployment status."""
    REGISTERED = "registered"      # Configuration registered, not yet deployed
    DEPLOYED = "deployed"          # Deployed and running
    STOPPED = "stopped"            # Stopped, files retained
    ARCHIVED = "archived"          # Archived: Caddy/tunnel removed, config backed up
    PURGED = "purged"              # Purged: completely deleted


class ServiceType(str, enum.Enum):
    """Service type."""
    FLASK = "flask"                # Flask application
    NODEJS = "nodejs"              # Node.js application
    STATIC = "static"              # Static website
    DOCKER = "docker"              # Docker container
    FLASK_STATIC = "flask+static"  # Flask + static files


class ServiceDeployment(Base):
    """Service deployment record."""

    __tablename__ = "service_deployments"

    # Primary key
    deployment_id = Column(String, primary_key=True)

    # Service identification
    project = Column(String, nullable=False, index=True)
    service = Column(String, nullable=False, index=True)
    server = Column(String, nullable=False, index=True)  # e.g., prod, staging
    service_type = Column(Enum(ServiceType), nullable=False)

    # Network configuration
    port = Column(Integer, nullable=True)  # References port_allocations
    hostname = Column(String, nullable=True)  # References tunnel_registrations
    tunnel_name = Column(String, nullable=True)

    # File paths
    app_path = Column(String, nullable=True)  # Application code path
    static_path = Column(String, nullable=True)  # Static files path
    data_path = Column(String, nullable=True)  # Data directory
    log_path = Column(String, nullable=True)  # Log directory
    config_path = Column(String, nullable=True)  # Config files path

    # Configuration (stored as JSON)
    caddy_rules = Column(JSON, nullable=True)  # Caddy routing rules
    environment = Column(JSON, nullable=True)  # Environment variables
    systemd_config = Column(JSON, nullable=True)  # systemd service configuration

    # Status management
    status = Column(Enum(DeploymentStatus), nullable=False, default=DeploymentStatus.REGISTERED, index=True)
    registered_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    registered_by = Column(String, nullable=False, default="mcp-server")
    deployed_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    purged_at = Column(DateTime, nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    backup_config = Column(JSON, nullable=True)  # Config backup saved when status is archived

    def __repr__(self):
        return f"<ServiceDeployment(project={self.project}, service={self.service}, server={self.server}, status={self.status})>"

    def to_dict(self):
        """Convert to dictionary."""
        return {
            "deployment_id": self.deployment_id,
            "project": self.project,
            "service": self.service,
            "server": self.server,
            "service_type": self.service_type.value if self.service_type else None,
            "port": self.port,
            "hostname": self.hostname,
            "tunnel_name": self.tunnel_name,
            "app_path": self.app_path,
            "static_path": self.static_path,
            "data_path": self.data_path,
            "log_path": self.log_path,
            "config_path": self.config_path,
            "caddy_rules": self.caddy_rules,
            "environment": self.environment,
            "systemd_config": self.systemd_config,
            "status": self.status.value if self.status else None,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
            "registered_by": self.registered_by,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
            "purged_at": self.purged_at.isoformat() if self.purged_at else None,
            "notes": self.notes,
            "backup_config": self.backup_config,
        }
