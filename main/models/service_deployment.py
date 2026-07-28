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


class ServiceLayer(str, enum.Enum):
    """Who owns this service's layout.

    STANDARD: this server allocated its resources and deploys it — paths are
    decisions, derived from project_root/deploy_root by convention.
    NONSTANDARD: it already exists, built by its own project — paths are
    observations; nothing here is derived or enforced.
    """
    STANDARD = "standard"
    NONSTANDARD = "nonstandard"


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

    # Layer and resource roots (see docs: resource model design)
    layer = Column(Enum(ServiceLayer), nullable=False, default=ServiceLayer.STANDARD, index=True)
    project_root = Column(String, nullable=True)   # e.g. ~/PRJ/{project}/
    deploy_root = Column(String, nullable=True)    # e.g. /var/www/{project}/  (file-serving only)
    workspace_url = Column(String, nullable=True)  # private workspace repo URL; NULL = no source of truth
    path_overrides = Column(JSON, nullable=True)   # {"data": "~/PRJ/example/instance/"} — deviations from convention

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
            "layer": self.layer.value if self.layer else None,
            "project_root": self.project_root,
            "deploy_root": self.deploy_root,
            "workspace_url": self.workspace_url,
            "path_overrides": self.path_overrides,
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
