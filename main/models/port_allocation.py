"""
Port Allocation Data Model
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Enum, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
import enum
from main.config import INFRA_DEFAULT_SERVER

Base = declarative_base()


class AllocationStatus(str, enum.Enum):
    """Port allocation status."""
    ALLOCATED = "allocated"      # Just allocated, not yet in use
    IN_USE = "in-use"            # Currently in use
    RESERVED = "reserved"         # Reserved (not in use but not released)
    RELEASED = "released"         # Released (can be reclaimed)


class PortAllocation(Base):
    """Port allocation record."""

    __tablename__ = "port_allocations"
    __table_args__ = (
        UniqueConstraint("port", "server", name="uq_port_server"),
    )

    # Primary key
    allocation_id = Column(String, primary_key=True)

    # Resource info
    port = Column(Integer, nullable=False, index=True)
    project = Column(String, nullable=False, index=True)
    service = Column(String, nullable=False)
    server = Column(String, nullable=False, default=INFRA_DEFAULT_SERVER)

    # Metadata
    allocated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    allocated_by = Column(String, nullable=False, default="mcp-server")
    status = Column(Enum(AllocationStatus), nullable=False, default=AllocationStatus.ALLOCATED, index=True)
    notes = Column(String, nullable=True)

    def __repr__(self):
        return f"<PortAllocation(port={self.port}, project={self.project}, status={self.status})>"

    def to_dict(self):
        """Convert to dictionary."""
        return {
            "allocation_id": self.allocation_id,
            "port": self.port,
            "project": self.project,
            "service": self.service,
            "server": self.server,
            "allocated_at": self.allocated_at.isoformat() if self.allocated_at else None,
            "allocated_by": self.allocated_by,
            "status": self.status.value if self.status else None,
            "notes": self.notes,
        }
