"""Central configuration loaded from environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()

_raw = os.getenv("INFRA_SERVERS", "")
INFRA_SERVERS: list[str] = [s.strip() for s in _raw.split(",") if s.strip()]

INFRA_DEFAULT_SERVER: str = os.getenv(
    "INFRA_DEFAULT_SERVER",
    INFRA_SERVERS[0] if INFRA_SERVERS else ""
)

INFRA_DOMAIN: str = os.getenv("INFRA_DOMAIN", "")
