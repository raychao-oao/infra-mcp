#!/usr/bin/env python3
"""
Infrastructure MCP Server
FastAPI-based MCP server for infrastructure resource management.

Accessible at: https://{INFRA_DOMAIN}/mcp (configure via INFRA_DOMAIN env var)
"""

import hmac
import json
import os
import re
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import logging

# Import database store
from main.db.sqlite_store import SQLiteStore

# Import MCP tools
from main.tools.allocate_port import (
    allocate_port,
    validate_allocate_port_input
)
from main.tools.release_port import (
    release_port,
    validate_release_port_input
)
from main.tools.list_resources import (
    list_resources,
    validate_list_resources_input
)
from main.tools.register_main_tunnel import (
    register_main_tunnel,
    validate_register_main_tunnel_input
)
from main.tools.list_main_tunnels import (
    list_main_tunnels,
    validate_list_main_tunnels_input
)
from main.tools.register_service import (
    register_service,
    validate_register_service_input
)
from main.tools.deploy_service import (
    deploy_service,
    validate_deploy_service_input
)
from main.tools.stop_service import (
    stop_service,
    validate_stop_service_input
)
from main.tools.purge_service import (
    purge_service,
    validate_purge_service_input
)
from main.tools.upgrade_service import (
    upgrade_service,
    validate_upgrade_service_input
)
from main.tools.get_service_info import (
    get_service_info,
    validate_get_service_info_input
)
from main.tools.check_listening_ports import (
    check_listening_ports,
    validate_check_listening_ports_input
)
from main.tools.validate_service_security import (
    validate_service_security,
    validate_validate_service_security_input
)
from main.tools.audit_all_services import (
    audit_all_services,
    validate_audit_all_services_input
)
from main.tools.restart_service import (
    restart_service,
    validate_restart_service_input
)
from main.tools.get_caddy_config import (
    get_caddy_config,
    validate_get_caddy_config_input
)
from main.tools.get_tunnel_config import (
    get_tunnel_config,
    validate_get_tunnel_config_input
)
from main.tools.get_service_logs import (
    get_service_logs,
    validate_get_service_logs_input
)
from main.tools.check_service_health import (
    check_service_health,
    validate_check_service_health_input
)

# Import Cloudflare tools
from main.tools.cloudflare.dns import (
    create_dns_record,
    update_dns_record,
    delete_dns_record,
    list_dns_records,
    validate_create_dns_record_input,
    validate_update_dns_record_input,
    validate_delete_dns_record_input,
    validate_list_dns_records_input,
)
from main.tools.cloudflare.access import (
    create_access_application,
    delete_access_application,
    list_access_applications,
    list_access_policies,
    validate_create_access_application_input,
    validate_delete_access_application_input,
    validate_list_access_applications_input,
    validate_list_access_policies_input,
)
from main.tools.cloudflare.tunnel import (
    create_cloudflare_tunnel,
    delete_cloudflare_tunnel,
    list_cloudflare_tunnels,
    get_tunnel_token,
    validate_create_cloudflare_tunnel_input,
    validate_delete_cloudflare_tunnel_input,
    validate_list_cloudflare_tunnels_input,
    validate_get_tunnel_token_input,
)
# Import Gitea tools
from main.tools.gitea.create_repo import create_gitea_repo
from main.tools.gitea.list_repos import list_gitea_repos
from main.tools.gitea.get_repo import get_gitea_repo
from main.tools.gitea.delete_repo import delete_gitea_repo

# Load environment variables
load_dotenv()

from main.config import INFRA_SERVERS, INFRA_DEFAULT_SERVER, INFRA_DOMAIN

# Optional API key auth (set MCP_API_KEY env var to enable)
MCP_API_KEY: str = os.getenv("MCP_API_KEY", "")

# Server configuration
SERVER_NAME = "infrastructure-mcp-server"
SERVER_VERSION = "1.0.0"
DOMAIN = INFRA_DOMAIN

# Global database store instance
store: Optional[SQLiteStore] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    global store

    # Startup
    print(f"🚀 Starting {SERVER_NAME} v{SERVER_VERSION}")
    print(f"📍 Domain: {DOMAIN}")

    # Initialize database
    database_url = os.getenv('DATABASE_URL', 'sqlite:///./configs/resources.db')
    print(f"🗄️  Database: {database_url}")

    store = SQLiteStore(database_url)
    await store.initialize()

    print("✅ Server initialization complete")

    yield

    # Shutdown
    print(f"👋 Shutting down {SERVER_NAME}")

    # Close database connection
    if store:
        await store.close()


# Create FastAPI app
app = FastAPI(
    title="Infrastructure MCP Server",
    description="Resource management for VPS, Cloudflare Tunnels, and deployments",
    version=SERVER_VERSION,
    lifespan=lifespan,
)

# CORS middleware — regex covers localhost (any port) + deployed domain
_cors_origin_regex = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
if INFRA_DOMAIN:
    _cors_origin_regex = f"({_cors_origin_regex}|https://{re.escape(INFRA_DOMAIN)})"
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=_cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional API key auth middleware — only active when MCP_API_KEY is set
if MCP_API_KEY:
    class APIKeyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Skip auth for health endpoints and CORS preflight
            if request.url.path in ("/", "/health") or request.method == "OPTIONS":
                return await call_next(request)
            auth = request.headers.get("Authorization", "")
            token = auth[7:] if auth.startswith("Bearer ") else ""
            # Constant-time comparison prevents timing attacks
            if not hmac.compare_digest(token.encode(), MCP_API_KEY.encode()):
                return JSONResponse(
                    status_code=401,
                    content={"error": "Unauthorized: valid Bearer token required"},
                )
            return await call_next(request)

    app.add_middleware(APIKeyMiddleware)
    if len(MCP_API_KEY) < 32:
        print("⚠️  MCP_API_KEY is shorter than 32 characters — consider using a longer key")
    print("🔒 API key authentication enabled")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors with request size for debugging."""
    body = await request.body()
    logger.error(f"Validation error: {len(body)} bytes, errors: {exc.errors()}")

    # Return JSON-RPC error response
    return JSONResponse(
        status_code=200,  # MCP uses 200 even for errors
        content={
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32600,  # Invalid Request
                "message": f"Invalid request format: {exc.errors()}"
            }
        }
    )


# Health check endpoint
@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "service": SERVER_NAME,
        "version": SERVER_VERSION,
        "status": "healthy",
        "domain": DOMAIN,
        "endpoints": {
            "health": "/health",
            "mcp": "/mcp",
            "docs": "/docs",
        }
    }


@app.get("/health")
async def health_check():
    """Detailed health check."""
    checks = {}

    # Check database connection
    if store:
        try:
            await store.list_port_allocations()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"
    else:
        checks["database"] = "not_initialized"

    # TODO: Check SSH connectivity to VPS
    checks["vps_connectivity"] = "not_implemented"

    # TODO: Check Cloudflare API
    checks["cloudflare_api"] = "not_implemented"

    # Determine overall status
    status = "healthy" if checks["database"] == "ok" else "degraded"

    return {
        "status": status,
        "version": SERVER_VERSION,
        "checks": checks
    }


class InvalidParamsError(Exception):
    """Raised for JSON-RPC -32602 Invalid Params errors."""


# Pydantic models for JSON-RPC 2.0 / MCP protocol
class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 Request format."""
    jsonrpc: str = "2.0"
    id: str | int
    method: str
    params: Optional[dict[str, Any]] = None


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 Success Response."""
    jsonrpc: str = "2.0"
    id: str | int
    result: dict[str, Any]


class JSONRPCError(BaseModel):
    """JSON-RPC 2.0 Error Response."""
    jsonrpc: str = "2.0"
    id: Optional[str | int] = None
    error: dict[str, Any]  # {code: int, message: str, data?: unknown}


# MCP endpoint - JSON-RPC 2.0 protocol
@app.post("/mcp")
async def mcp_endpoint(request: JSONRPCRequest):
    """
    MCP JSON-RPC 2.0 endpoint.

    Implements three core methods:
    - initialize: Establish connection and capabilities
    - tools/list: List available tools
    - tools/call: Execute a tool
    """
    try:
        method = request.method
        params = request.params or {}

        # Method 1: initialize
        if method == "initialize":
            return JSONRPCResponse(
                id=request.id,
                result={
                    "protocolVersion": "2025-11-25",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION
                    }
                }
            )

        # Method 2: tools/list
        elif method == "tools/list":
            tools = [
                {
                    "name": "allocate_port",
                    "description": "Allocate a port for a project service. Validates project/service names and manages port pool (3000-9999).",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project": {
                                "type": "string",
                                "description": "Project name (lowercase, hyphens allowed)"
                            },
                            "service": {
                                "type": "string",
                                "description": "Service name (lowercase, hyphens allowed)"
                            },
                            "preferred_port": {
                                "type": "integer",
                                "description": "Preferred port number (3000-9999, optional)"
                            },
                            "server": {
                                "type": "string",
                                "description": "VPS server name (e.g., 'prod', 'staging'; configured via INFRA_SERVERS)"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Optional notes about allocation"
                            }
                        },
                        "required": ["project", "service"]
                    }
                },
                {
                    "name": "list_resources",
                    "description": "List infrastructure resource allocations with filtering options",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "resource_type": {
                                "type": "string",
                                "enum": ["all", "ports", "tunnels", "deployments"],
                                "description": "Type of resource to list (default: all)"
                            },
                            "project": {
                                "type": "string",
                                "description": "Filter by project name (optional)"
                            },
                            "server": {
                                "type": "string",
                                "description": "Filter by server name (e.g., 'prod')"
                            },
                            "status": {
                                "type": "string",
                                "description": "Filter by status"
                            },
                            "include_released": {
                                "type": "boolean",
                                "description": "Include released/archived resources (default: false)"
                            }
                        }
                    }
                },
                {
                    "name": "register_main_tunnel",
                    "description": "Register an actual Cloudflare Tunnel (one per VPS). For tracking purposes - the tunnel should already exist.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "tunnel_name": {
                                "type": "string",
                                "description": "Tunnel name (e.g., 'prod-main')"
                            },
                            "cloudflare_tunnel_id": {
                                "type": "string",
                                "description": "Cloudflare Tunnel UUID"
                            },
                            "vps_server": {
                                "type": "string",
                                "description": "VPS server name (configured via INFRA_SERVERS)"
                            },
                            "tunnel_target": {
                                "type": "string",
                                "description": "Tunnel target domain (e.g., 'uuid.cfargotunnel.com')"
                            },
                            "credentials_file": {
                                "type": "string",
                                "description": "Path to credentials file (optional)"
                            },
                            "config_file": {
                                "type": "string",
                                "description": "Path to config file (optional)"
                            },
                            "systemd_service": {
                                "type": "string",
                                "description": "Systemd service name (optional)"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Optional notes"
                            }
                        },
                        "required": ["tunnel_name", "cloudflare_tunnel_id", "vps_server"]
                    }
                },
                {
                    "name": "list_main_tunnels",
                    "description": "List all registered main tunnels (actual Cloudflare Tunnels, one per VPS)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "vps_server": {
                                "type": "string",
                                "description": "Filter by VPS server (optional)"
                            },
                            "status": {
                                "type": "string",
                                "description": "Filter by status (active, inactive, failed)"
                            }
                        }
                    }
                },
                {
                    "name": "release_port",
                    "description": "Release a port allocation and make it available for reuse",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "port": {
                                "type": "integer",
                                "description": "Port number to release (3000-9999)"
                            },
                            "server": {
                                "type": "string",
                                "description": "VPS server name (e.g., 'prod', 'staging'; configured via INFRA_SERVERS)"
                            }
                        },
                        "required": ["port"]
                    }
                },
                {
                    "name": "register_service",
                    "description": "Register a service deployment configuration (planning phase - no actual deployment)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project": {
                                "type": "string",
                                "description": "Project name (lowercase, hyphens allowed)"
                            },
                            "service": {
                                "type": "string",
                                "description": "Service name (lowercase, hyphens allowed)"
                            },
                            "server": {
                                "type": "string",
                                "description": "VPS server name (configured via INFRA_SERVERS)"
                            },
                            "service_type": {
                                "type": "string",
                                "enum": ["flask", "nodejs", "static", "docker", "flask+static"],
                                "description": "Service type"
                            },
                            "port": {
                                "type": "integer",
                                "description": "Port number (optional, can be allocated during deployment)"
                            },
                            "hostname": {
                                "type": "string",
                                "description": "Public hostname (e.g., 'app.your-domain.com')"
                            },
                            "tunnel_name": {
                                "type": "string",
                                "description": "Cloudflare tunnel name (optional)"
                            },
                            "app_path": {
                                "type": "string",
                                "description": "Application code path (e.g., '~/PRJ/PAC/dashboard/flask_app/')"
                            },
                            "static_path": {
                                "type": "string",
                                "description": "Static files path (e.g., '/var/www/pac/')"
                            },
                            "data_path": {
                                "type": "string",
                                "description": "Data directory path"
                            },
                            "log_path": {
                                "type": "string",
                                "description": "Log directory path"
                            },
                            "config_path": {
                                "type": "string",
                                "description": "Config files path"
                            },
                            "caddy_rules": {
                                "type": "object",
                                "description": "Caddy routing rules as JSON object"
                            },
                            "environment": {
                                "type": "object",
                                "description": "Environment variables as JSON object"
                            },
                            "systemd_config": {
                                "type": "object",
                                "description": "Systemd service configuration as JSON object"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Optional notes"
                            }
                        },
                        "required": ["project", "service", "server", "service_type"]
                    }
                },
                {
                    "name": "deploy_service",
                    "description": "Deploy a registered service to VPS (allocate port, add DNS, generate Caddy config, create systemd service, start service)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project": {
                                "type": "string",
                                "description": "Project name"
                            },
                            "service": {
                                "type": "string",
                                "description": "Service name"
                            },
                            "server": {
                                "type": "string",
                                "description": "VPS server name"
                            },
                            "cloudflare_api_token": {
                                "type": "string",
                                "description": "Cloudflare API token (optional, will use env var)"
                            },
                            "cloudflare_account_id": {
                                "type": "string",
                                "description": "Cloudflare account ID (optional, will use env var)"
                            }
                        },
                        "required": ["project", "service", "server"]
                    }
                },
                {
                    "name": "stop_service",
                    "description": "Stop a running service (keeps configuration and files preserved)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project": {
                                "type": "string",
                                "description": "Project name"
                            },
                            "service": {
                                "type": "string",
                                "description": "Service name"
                            },
                            "server": {
                                "type": "string",
                                "description": "VPS server name"
                            }
                        },
                        "required": ["project", "service", "server"]
                    }
                },
                {
                    "name": "purge_service",
                    "description": "Completely purge a service and clean up all resources (stop service, remove systemd, remove Caddy config, release port, optionally delete files)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project": {
                                "type": "string",
                                "description": "Project name"
                            },
                            "service": {
                                "type": "string",
                                "description": "Service name"
                            },
                            "server": {
                                "type": "string",
                                "description": "VPS server name"
                            },
                            "remove_app_files": {
                                "type": "boolean",
                                "description": "Delete application files (default: false)"
                            },
                            "remove_static_files": {
                                "type": "boolean",
                                "description": "Delete static files (default: false)"
                            },
                            "remove_data": {
                                "type": "boolean",
                                "description": "Delete data directory (default: false)"
                            },
                            "remove_logs": {
                                "type": "boolean",
                                "description": "Delete log files (default: false)"
                            },
                            "remove_dns_record": {
                                "type": "boolean",
                                "description": "Remove DNS CNAME record (default: false)"
                            }
                        },
                        "required": ["project", "service", "server"]
                    }
                },
                {
                    "name": "upgrade_service",
                    "description": "Upgrade a service type (e.g., static -> flask+static). Used when a static site needs to add a backend.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project": {
                                "type": "string",
                                "description": "Project name"
                            },
                            "service": {
                                "type": "string",
                                "description": "Service name"
                            },
                            "server": {
                                "type": "string",
                                "description": "VPS server name"
                            },
                            "new_service_type": {
                                "type": "string",
                                "enum": ["flask", "nodejs", "flask+static"],
                                "description": "New service type to upgrade to"
                            },
                            "app_path": {
                                "type": "string",
                                "description": "Application code path (optional, uses default ~/PRJ/{project}/app/)"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Optional notes about the upgrade"
                            }
                        },
                        "required": ["project", "service", "server", "new_service_type"]
                    }
                },
                {
                    "name": "get_service_info",
                    "description": "Get detailed information about a deployed service including connection URL, directory structure, port, Caddy config, and systemd service",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project": {
                                "type": "string",
                                "description": "Project name"
                            },
                            "service": {
                                "type": "string",
                                "description": "Service name"
                            },
                            "server": {
                                "type": "string",
                                "description": "VPS server name"
                            }
                        },
                        "required": ["project", "service", "server"]
                    }
                },
                # Security audit tools
                {
                    "name": "check_listening_ports",
                    "description": "Check listening ports on a VPS server to identify security risks. Returns all ports not bound to 127.0.0.1 (localhost only).",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "server": {
                                "type": "string",
                                **({"enum": INFRA_SERVERS} if INFRA_SERVERS else {}),
                                "description": "VPS server name"
                            },
                            "port": {
                                "type": "integer",
                                "description": "Optional specific port to check"
                            }
                        },
                        "required": ["server"]
                    }
                },
                {
                    "name": "validate_service_security",
                    "description": "Validate service security configuration including Docker port bindings, Caddy bind directives, and actual port bindings. Can optionally auto-fix issues.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project": {
                                "type": "string",
                                "description": "Project name"
                            },
                            "service": {
                                "type": "string",
                                "description": "Service name"
                            },
                            "server": {
                                "type": "string",
                                **({"enum": INFRA_SERVERS} if INFRA_SERVERS else {}),
                                "description": "VPS server name"
                            },
                            "auto_fix": {
                                "type": "boolean",
                                "description": "Whether to automatically fix security issues (default: false)"
                            }
                        },
                        "required": ["project", "service", "server"]
                    }
                },
                {
                    "name": "audit_all_services",
                    "description": "Audit all deployed services' security configuration. Generates a comprehensive security audit report with statistics by server.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "server": {
                                "type": "string",
                                **({"enum": INFRA_SERVERS} if INFRA_SERVERS else {}),
                                "description": "Optional VPS server to filter (if omitted, audits all servers)"
                            },
                            "auto_fix": {
                                "type": "boolean",
                                "description": "Whether to automatically fix security issues (default: false)"
                            }
                        },
                        "required": []
                    }
                },
                {
                    "name": "restart_service",
                    "description": "Restart a deployed service component (service, caddy, or tunnel)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project": {
                                "type": "string",
                                "description": "Project name"
                            },
                            "service": {
                                "type": "string",
                                "description": "Service name"
                            },
                            "server": {
                                "type": "string",
                                **({"enum": INFRA_SERVERS} if INFRA_SERVERS else {}),
                                "description": "VPS server name"
                            },
                            "component": {
                                "type": "string",
                                "enum": ["service", "caddy", "tunnel"],
                                "description": "Component to restart (default: service)"
                            }
                        },
                        "required": ["project", "service", "server"]
                    }
                },
                {
                    "name": "get_caddy_config",
                    "description": "Get Caddy configuration file content (main Caddyfile or service-specific config)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "server": {
                                "type": "string",
                                **({"enum": INFRA_SERVERS} if INFRA_SERVERS else {}),
                                "description": "VPS server name"
                            },
                            "project": {
                                "type": "string",
                                "description": "Optional project name (for service-specific config)"
                            },
                            "service": {
                                "type": "string",
                                "description": "Optional service name (for service-specific config)"
                            }
                        },
                        "required": ["server"]
                    }
                },
                {
                    "name": "get_tunnel_config",
                    "description": "Get Cloudflare Tunnel configuration from VPS server",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "server": {
                                "type": "string",
                                **({"enum": INFRA_SERVERS} if INFRA_SERVERS else {}),
                                "description": "VPS server name"
                            }
                        },
                        "required": ["server"]
                    }
                },
                {
                    "name": "get_service_logs",
                    "description": "Get logs from service components (systemd, Docker, Caddy, or Tunnel)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "server": {
                                "type": "string",
                                **({"enum": INFRA_SERVERS} if INFRA_SERVERS else {}),
                                "description": "VPS server name"
                            },
                            "project": {
                                "type": "string",
                                "description": "Project name (required for service component)"
                            },
                            "service": {
                                "type": "string",
                                "description": "Service name (required for service component)"
                            },
                            "component": {
                                "type": "string",
                                "enum": ["service", "caddy", "tunnel"],
                                "description": "Component to get logs from (default: service)"
                            },
                            "lines": {
                                "type": "integer",
                                "description": "Number of log lines to retrieve (default: 50, max: 1000)"
                            },
                            "since": {
                                "type": "string",
                                "description": "Time filter for logs (e.g. '1 hour ago', '2026-02-11 15:00', '30 min ago'). Uses journalctl --since format."
                            }
                        },
                        "required": ["server"]
                    }
                },
                {
                    "name": "check_service_health",
                    "description": "Check health status of services and system resources",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "server": {
                                "type": "string",
                                **({"enum": INFRA_SERVERS} if INFRA_SERVERS else {}),
                                "description": "VPS server name"
                            },
                            "project": {
                                "type": "string",
                                "description": "Optional project name (for specific service check)"
                            },
                            "service": {
                                "type": "string",
                                "description": "Optional service name (for specific service check)"
                            },
                            "include_system_stats": {
                                "type": "boolean",
                                "description": "Whether to include system resource statistics (default: false)"
                            }
                        },
                        "required": ["server"]
                    }
                },
                # Cloudflare DNS tools
                {
                    "name": "create_dns_record",
                    "description": "Create a DNS record in Cloudflare (A, AAAA, CNAME, TXT, MX, etc.). For tunnel CNAME records, use tunnel_name parameter to create via cloudflared CLI.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "description": "Full domain name (e.g., 'app.your-domain.com')"
                            },
                            "record_type": {
                                "type": "string",
                                "enum": ["A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA"],
                                "description": "DNS record type"
                            },
                            "content": {
                                "type": "string",
                                "description": "Record content (IP address, target domain, etc.)"
                            },
                            "ttl": {
                                "type": "integer",
                                "description": "Time to live (1 = auto, default: 1)"
                            },
                            "proxied": {
                                "type": "boolean",
                                "description": "Proxy through Cloudflare (default: false)"
                            },
                            "priority": {
                                "type": "integer",
                                "description": "Priority for MX/SRV records"
                            },
                            "comment": {
                                "type": "string",
                                "description": "Optional comment"
                            },
                            "tunnel_name": {
                                "type": "string",
                                "description": "Tunnel name for cloudflared CLI method (e.g., 'prod-main'). Use this for tunnel CNAME records."
                            },
                            "server": {
                                "type": "string",
                                "description": "VPS server to run cloudflared on (default: first INFRA_SERVERS). Used with tunnel_name."
                            }
                        },
                        "required": ["domain", "record_type", "content"]
                    }
                },
                {
                    "name": "update_dns_record",
                    "description": "Update an existing DNS record in Cloudflare",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "description": "Full domain name"
                            },
                            "record_id": {
                                "type": "string",
                                "description": "Record ID (if known)"
                            },
                            "record_type": {
                                "type": "string",
                                "description": "Record type to find (if record_id not provided)"
                            },
                            "content": {
                                "type": "string",
                                "description": "New content value"
                            },
                            "ttl": {
                                "type": "integer",
                                "description": "New TTL value"
                            },
                            "proxied": {
                                "type": "boolean",
                                "description": "New proxied status"
                            }
                        },
                        "required": ["domain"]
                    }
                },
                {
                    "name": "delete_dns_record",
                    "description": "Delete a DNS record from Cloudflare",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "record_id": {
                                "type": "string",
                                "description": "Record ID to delete"
                            },
                            "domain": {
                                "type": "string",
                                "description": "Domain name (used to find record)"
                            },
                            "record_type": {
                                "type": "string",
                                "description": "Record type (used with domain to find record)"
                            }
                        }
                    }
                },
                {
                    "name": "list_dns_records",
                    "description": "List DNS records for a Cloudflare zone",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "description": "Domain to list records for (e.g., 'your-domain.com')"
                            },
                            "record_type": {
                                "type": "string",
                                "description": "Filter by record type"
                            },
                            "name_contains": {
                                "type": "string",
                                "description": "Filter records containing this string"
                            }
                        }
                    }
                },
                # Cloudflare Access tools
                {
                    "name": "create_access_application",
                    "description": "Create a Cloudflare Access application to protect a URL",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Application name (e.g., 'Grafana Dashboard')"
                            },
                            "domain": {
                                "type": "string",
                                "description": "Protected domain (e.g., 'metrics.your-domain.com')"
                            },
                            "session_duration": {
                                "type": "string",
                                "description": "Session duration (e.g., '24h', '168h', default: '24h')"
                            },
                            "policy_name": {
                                "type": "string",
                                "description": "Name for new policy (if creating)"
                            },
                            "policy_emails": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of allowed emails for the policy"
                            },
                            "policy_id": {
                                "type": "string",
                                "description": "Existing policy ID to attach"
                            }
                        },
                        "required": ["name", "domain"]
                    }
                },
                {
                    "name": "delete_access_application",
                    "description": "Delete a Cloudflare Access application",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "app_id": {
                                "type": "string",
                                "description": "Application ID to delete"
                            },
                            "domain": {
                                "type": "string",
                                "description": "Domain to find application (if app_id not provided)"
                            }
                        }
                    }
                },
                {
                    "name": "list_access_applications",
                    "description": "List Cloudflare Access applications",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "description": "Domain to filter by zone"
                            }
                        }
                    }
                },
                {
                    "name": "list_access_policies",
                    "description": "List Cloudflare Access policies",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "description": "Domain to derive zone from"
                            },
                            "app_id": {
                                "type": "string",
                                "description": "Application ID to list policies for"
                            }
                        }
                    }
                },
                # Cloudflare Tunnel API tools
                {
                    "name": "create_cloudflare_tunnel",
                    "description": "Create a Cloudflare Tunnel via API",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Tunnel name (e.g., 'prod-main')"
                            },
                            "config_src": {
                                "type": "string",
                                "enum": ["cloudflare", "local"],
                                "description": "Configuration source (default: 'cloudflare')"
                            }
                        },
                        "required": ["name"]
                    }
                },
                {
                    "name": "delete_cloudflare_tunnel",
                    "description": "Delete a Cloudflare Tunnel",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "tunnel_id": {
                                "type": "string",
                                "description": "Tunnel ID to delete"
                            },
                            "tunnel_name": {
                                "type": "string",
                                "description": "Tunnel name (if tunnel_id not provided)"
                            },
                            "force": {
                                "type": "boolean",
                                "description": "Force delete even with active connections"
                            }
                        }
                    }
                },
                {
                    "name": "list_cloudflare_tunnels",
                    "description": "List Cloudflare Tunnels",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "include_deleted": {
                                "type": "boolean",
                                "description": "Include deleted tunnels"
                            },
                            "status": {
                                "type": "string",
                                "description": "Filter by status ('active', 'inactive')"
                            },
                            "name_contains": {
                                "type": "string",
                                "description": "Filter tunnels by name"
                            }
                        }
                    }
                },
                {
                    "name": "get_tunnel_token",
                    "description": "Get the connection token for a Cloudflare Tunnel",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "tunnel_id": {
                                "type": "string",
                                "description": "Tunnel ID"
                            },
                            "tunnel_name": {
                                "type": "string",
                                "description": "Tunnel name (if tunnel_id not provided)"
                            }
                        }
                    }
                },
                {
                    "name": "create_gitea_repo",
                    "description": "Create a new repository in Gitea",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Repository name (required)"
                            },
                            "description": {
                                "type": "string",
                                "description": "Repository description (optional)"
                            },
                            "private": {
                                "type": "boolean",
                                "description": "Whether the repository is private (default: false)"
                            },
                            "auto_init": {
                                "type": "boolean",
                                "description": "Initialize repository with README (default: true)"
                            },
                            "gitignores": {
                                "type": "string",
                                "description": "Gitignore template name (optional)"
                            },
                            "license": {
                                "type": "string",
                                "description": "License template name (optional)"
                            },
                            "readme": {
                                "type": "string",
                                "description": "README template (default: 'Default')"
                            },
                            "default_branch": {
                                "type": "string",
                                "description": "Default branch name (default: 'main')"
                            }
                        },
                        "required": ["name"]
                    }
                },
                {
                    "name": "list_gitea_repos",
                    "description": "List all repositories for the authenticated user",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of repositories to return (default: 50, max: 100)"
                            },
                            "page": {
                                "type": "integer",
                                "description": "Page number for pagination (default: 1)"
                            }
                        }
                    }
                },
                {
                    "name": "get_gitea_repo",
                    "description": "Get detailed information about a specific repository",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "owner": {
                                "type": "string",
                                "description": "Repository owner username"
                            },
                            "repo": {
                                "type": "string",
                                "description": "Repository name"
                            }
                        },
                        "required": ["owner", "repo"]
                    }
                },
                {
                    "name": "delete_gitea_repo",
                    "description": "Delete a repository from Gitea (WARNING: IRREVERSIBLE). Requires special danger token for security.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "owner": {
                                "type": "string",
                                "description": "Repository owner username"
                            },
                            "repo": {
                                "type": "string",
                                "description": "Repository name"
                            },
                            "danger_token": {
                                "type": "string",
                                "description": "Special danger token for irreversible operations (required for security)"
                            }
                        },
                        "required": ["owner", "repo", "danger_token"]
                    }
                }
            ]

            return JSONRPCResponse(
                id=request.id,
                result={"tools": tools}
            )

        # Method 3: tools/call
        elif method == "tools/call":
            if not store:
                raise Exception("Database not initialized")

            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if not tool_name:
                return JSONResponse(
                    status_code=200,
                    content={
                        "jsonrpc": "2.0",
                        "id": request.id,
                        "error": {"code": -32602, "message": "Missing required parameter: name"}
                    }
                )

            if not isinstance(arguments, dict):
                return JSONResponse(
                    status_code=200,
                    content={
                        "jsonrpc": "2.0",
                        "id": request.id,
                        "error": {"code": -32602, "message": "Parameter 'arguments' must be an object"}
                    }
                )

            # Execute the requested tool
            result = None

            if tool_name == "allocate_port":
                is_valid, error_msg = await validate_allocate_port_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await allocate_port(
                    store=store,
                    project=arguments["project"],
                    service=arguments["service"],
                    preferred_port=arguments.get("preferred_port"),
                    server=arguments.get("server", INFRA_DEFAULT_SERVER),
                    notes=arguments.get("notes")
                )

            elif tool_name == "list_resources":
                is_valid, error_msg = await validate_list_resources_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await list_resources(
                    store=store,
                    resource_type=arguments.get("resource_type", "all"),
                    project=arguments.get("project"),
                    server=arguments.get("server"),
                    status=arguments.get("status"),
                    include_released=arguments.get("include_released", False)
                )

            elif tool_name == "register_main_tunnel":
                is_valid, error_msg = await validate_register_main_tunnel_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await register_main_tunnel(
                    store=store,
                    tunnel_name=arguments["tunnel_name"],
                    cloudflare_tunnel_id=arguments["cloudflare_tunnel_id"],
                    vps_server=arguments["vps_server"],
                    tunnel_target=arguments.get("tunnel_target"),
                    credentials_file=arguments.get("credentials_file"),
                    config_file=arguments.get("config_file"),
                    systemd_service=arguments.get("systemd_service"),
                    notes=arguments.get("notes")
                )

            elif tool_name == "list_main_tunnels":
                is_valid, error_msg = await validate_list_main_tunnels_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await list_main_tunnels(
                    store=store,
                    vps_server=arguments.get("vps_server"),
                    status=arguments.get("status")
                )

            elif tool_name == "release_port":
                is_valid, error_msg = await validate_release_port_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await release_port(
                    store=store,
                    port=arguments["port"],
                    server=arguments.get("server", INFRA_DEFAULT_SERVER)
                )

            elif tool_name == "register_service":
                is_valid, error_msg = await validate_register_service_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await register_service(
                    store=store,
                    project=arguments["project"],
                    service=arguments["service"],
                    server=arguments["server"],
                    service_type=arguments["service_type"],
                    port=arguments.get("port"),
                    hostname=arguments.get("hostname"),
                    tunnel_name=arguments.get("tunnel_name"),
                    app_path=arguments.get("app_path"),
                    static_path=arguments.get("static_path"),
                    data_path=arguments.get("data_path"),
                    log_path=arguments.get("log_path"),
                    config_path=arguments.get("config_path"),
                    caddy_rules=arguments.get("caddy_rules"),
                    environment=arguments.get("environment"),
                    systemd_config=arguments.get("systemd_config"),
                    notes=arguments.get("notes")
                )

            elif tool_name == "deploy_service":
                is_valid, error_msg = await validate_deploy_service_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await deploy_service(
                    store=store,
                    project=arguments["project"],
                    service=arguments["service"],
                    server=arguments["server"],
                    cloudflare_api_token=arguments.get("cloudflare_api_token"),
                    cloudflare_account_id=arguments.get("cloudflare_account_id")
                )

            elif tool_name == "stop_service":
                is_valid, error_msg = await validate_stop_service_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await stop_service(
                    store=store,
                    project=arguments["project"],
                    service=arguments["service"],
                    server=arguments["server"]
                )

            elif tool_name == "purge_service":
                is_valid, error_msg = await validate_purge_service_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await purge_service(
                    store=store,
                    project=arguments["project"],
                    service=arguments["service"],
                    server=arguments["server"],
                    remove_app_files=arguments.get("remove_app_files", False),
                    remove_static_files=arguments.get("remove_static_files", False),
                    remove_data=arguments.get("remove_data", False),
                    remove_logs=arguments.get("remove_logs", False),
                    remove_dns_record=arguments.get("remove_dns_record", False)
                )

            elif tool_name == "upgrade_service":
                is_valid, error_msg = await validate_upgrade_service_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await upgrade_service(
                    store=store,
                    project=arguments["project"],
                    service=arguments["service"],
                    server=arguments["server"],
                    new_service_type=arguments["new_service_type"],
                    app_path=arguments.get("app_path"),
                    notes=arguments.get("notes")
                )

            elif tool_name == "get_service_info":
                is_valid, error_msg = await validate_get_service_info_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await get_service_info(
                    store=store,
                    project=arguments["project"],
                    service=arguments["service"],
                    server=arguments["server"]
                )

            # Security audit tools
            elif tool_name == "check_listening_ports":
                is_valid, error_msg = await validate_check_listening_ports_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await check_listening_ports(
                    store=store,
                    server=arguments["server"],
                    port=arguments.get("port")
                )

            elif tool_name == "validate_service_security":
                is_valid, error_msg = await validate_validate_service_security_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await validate_service_security(
                    store=store,
                    project=arguments["project"],
                    service=arguments["service"],
                    server=arguments["server"],
                    auto_fix=arguments.get("auto_fix", False)
                )

            elif tool_name == "audit_all_services":
                is_valid, error_msg = await validate_audit_all_services_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await audit_all_services(
                    store=store,
                    server=arguments.get("server"),
                    auto_fix=arguments.get("auto_fix", False)
                )

            elif tool_name == "restart_service":
                is_valid, error_msg = await validate_restart_service_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await restart_service(
                    store=store,
                    project=arguments["project"],
                    service=arguments["service"],
                    server=arguments["server"],
                    component=arguments.get("component", "service")
                )

            elif tool_name == "get_caddy_config":
                is_valid, error_msg = await validate_get_caddy_config_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await get_caddy_config(
                    store=store,
                    server=arguments["server"],
                    project=arguments.get("project"),
                    service=arguments.get("service")
                )

            elif tool_name == "get_tunnel_config":
                is_valid, error_msg = await validate_get_tunnel_config_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await get_tunnel_config(
                    store=store,
                    server=arguments["server"]
                )

            elif tool_name == "get_service_logs":
                is_valid, error_msg = await validate_get_service_logs_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await get_service_logs(
                    store=store,
                    server=arguments["server"],
                    project=arguments["project"],
                    service=arguments["service"],
                    component=arguments.get("component", "service"),
                    lines=arguments.get("lines", 50),
                    since=arguments.get("since")
                )

            elif tool_name == "check_service_health":
                is_valid, error_msg = await validate_check_service_health_input(arguments)
                if not is_valid:
                    raise InvalidParamsError(error_msg)

                result = await check_service_health(
                    store=store,
                    server=arguments["server"],
                    project=arguments["project"],
                    service=arguments["service"],
                    include_system_stats=arguments.get("include_system_stats", False)
                )

            # Cloudflare DNS tools
            elif tool_name == "create_dns_record":
                validation = validate_create_dns_record_input(arguments)
                if not validation.get("valid"):
                    raise InvalidParamsError(str(validation.get('errors')))

                result = await create_dns_record(**arguments)

            elif tool_name == "update_dns_record":
                validation = validate_update_dns_record_input(arguments)
                if not validation.get("valid"):
                    raise InvalidParamsError(str(validation.get('errors')))

                result = await update_dns_record(**arguments)

            elif tool_name == "delete_dns_record":
                validation = validate_delete_dns_record_input(arguments)
                if not validation.get("valid"):
                    raise InvalidParamsError(str(validation.get('errors')))

                result = await delete_dns_record(**arguments)

            elif tool_name == "list_dns_records":
                validation = validate_list_dns_records_input(arguments)
                if not validation.get("valid"):
                    raise InvalidParamsError(str(validation.get('errors')))

                result = await list_dns_records(**arguments)

            # Cloudflare Access tools
            elif tool_name == "create_access_application":
                validation = validate_create_access_application_input(arguments)
                if not validation.get("valid"):
                    raise InvalidParamsError(str(validation.get('errors')))

                result = await create_access_application(**arguments)

            elif tool_name == "delete_access_application":
                validation = validate_delete_access_application_input(arguments)
                if not validation.get("valid"):
                    raise InvalidParamsError(str(validation.get('errors')))

                result = await delete_access_application(**arguments)

            elif tool_name == "list_access_applications":
                validation = validate_list_access_applications_input(arguments)
                if not validation.get("valid"):
                    raise InvalidParamsError(str(validation.get('errors')))

                result = await list_access_applications(**arguments)

            elif tool_name == "list_access_policies":
                validation = validate_list_access_policies_input(arguments)
                if not validation.get("valid"):
                    raise InvalidParamsError(str(validation.get('errors')))

                result = await list_access_policies(**arguments)

            # Cloudflare Tunnel API tools
            elif tool_name == "create_cloudflare_tunnel":
                validation = validate_create_cloudflare_tunnel_input(arguments)
                if not validation.get("valid"):
                    raise InvalidParamsError(str(validation.get('errors')))

                result = await create_cloudflare_tunnel(**arguments)

            elif tool_name == "delete_cloudflare_tunnel":
                validation = validate_delete_cloudflare_tunnel_input(arguments)
                if not validation.get("valid"):
                    raise InvalidParamsError(str(validation.get('errors')))

                result = await delete_cloudflare_tunnel(**arguments)

            elif tool_name == "list_cloudflare_tunnels":
                validation = validate_list_cloudflare_tunnels_input(arguments)
                if not validation.get("valid"):
                    raise InvalidParamsError(str(validation.get('errors')))

                result = await list_cloudflare_tunnels(**arguments)

            elif tool_name == "get_tunnel_token":
                validation = validate_get_tunnel_token_input(arguments)
                if not validation.get("valid"):
                    raise InvalidParamsError(str(validation.get('errors')))

                result = await get_tunnel_token(**arguments)

            elif tool_name == "create_gitea_repo":
                result = await create_gitea_repo(
                    name=arguments["name"],
                    description=arguments.get("description", ""),
                    private=arguments.get("private", False),
                    auto_init=arguments.get("auto_init", True),
                    gitignores=arguments.get("gitignores", ""),
                    license=arguments.get("license", ""),
                    readme=arguments.get("readme", "Default"),
                    default_branch=arguments.get("default_branch", "main")
                )

            elif tool_name == "list_gitea_repos":
                result = await list_gitea_repos(
                    limit=arguments.get("limit", 50),
                    page=arguments.get("page", 1)
                )

            elif tool_name == "get_gitea_repo":
                result = await get_gitea_repo(
                    owner=arguments["owner"],
                    repo=arguments["repo"]
                )

            elif tool_name == "delete_gitea_repo":
                result = await delete_gitea_repo(
                    owner=arguments["owner"],
                    repo=arguments["repo"],
                    danger_token=arguments.get("danger_token", "")
                )

            else:
                return JSONResponse(
                    status_code=200,
                    content={
                        "jsonrpc": "2.0",
                        "id": request.id,
                        "error": {
                            "code": -32601,  # Method not found
                            "message": f"Unknown tool: {tool_name}"
                        }
                    }
                )

            # Format result for MCP - return full JSON data so AI clients can parse it
            text_content = json.dumps(result, default=str)

            return JSONRPCResponse(
                id=request.id,
                result={
                    "content": [
                        {
                            "type": "text",
                            "text": text_content
                        }
                    ]
                }
            )

        # Unknown method
        else:
            return JSONResponse(
                status_code=200,
                content={
                    "jsonrpc": "2.0",
                    "id": request.id,
                    "error": {
                        "code": -32601,  # Method not found
                        "message": f"Method not found: {method}"
                    }
                }
            )

    except InvalidParamsError as e:
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "id": request.id if hasattr(request, 'id') else None,
                "error": {"code": -32602, "message": str(e)}
            }
        )
    except Exception as e:
        logger.error("Unhandled error in mcp_endpoint: %s", e, exc_info=True)
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "id": request.id if hasattr(request, 'id') else None,
                "error": {"code": -32603, "message": "Internal server error"}
            }
        )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("SERVER_PORT", "8000"))

    print(f"🌐 Starting server on {host}:{port}")
    print(f"📖 Docs available at http://{host}:{port}/docs")

    uvicorn.run(
        "main.server:app",
        host=host,
        port=port,
        reload=True,  # For development
        log_level="info"
    )
