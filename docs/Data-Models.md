# Infrastructure MCP Server — Data Models

**Document version**: v2.0
**Last updated**: 2026-05-16
**Status**: Production

---

## Overview

The server uses **SQLite** via SQLAlchemy async (aiosqlite driver). Three tables are managed by SQLAlchemy ORM; Cloudflare and Gitea data is not persisted locally — it is fetched live from their respective APIs.

**Database file**: `~/PRJ/infra-mcp/configs/resources.db` (production)
**ORM models**: `main/models/`
**Store layer**: `main/db/sqlite_store.py` (SQLiteStore class)

---

## Tables

### `port_allocations`

Tracks port assignments in the 3000–9999 range.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `allocation_id` | String | PK | Unique ID (e.g., `alloc_20260101_001`) |
| `port` | Integer | NOT NULL, indexed | Port number (3000–9999) |
| `project` | String | NOT NULL, indexed | Project name |
| `service` | String | NOT NULL | Service name within project |
| `server` | String | NOT NULL | VPS server (default: `INFRA_DEFAULT_SERVER`) |
| `allocated_at` | DateTime | NOT NULL | Allocation timestamp (UTC) |
| `allocated_by` | String | NOT NULL | Always `"mcp-server"` |
| `status` | Enum | NOT NULL, indexed | See statuses below |
| `notes` | String | nullable | Optional notes |

**Unique constraint**: `(port, server)` — a port can only be allocated once per server.

**`AllocationStatus` enum**:
| Value | Meaning |
|-------|---------|
| `allocated` | Reserved but service not yet started |
| `in-use` | Service actively using this port |
| `reserved` | Held, not actively in use |
| `released` | Freed; eligible for reuse |

`list_port_allocations` excludes `released` records by default.

---

### `main_tunnels`

Tracks the Cloudflare Tunnel running on each VPS. One tunnel per VPS — all service traffic routes through Caddy on that tunnel.

```
MainTunnel (one per VPS)
└── prod-main (CF tunnel UUID)
    └── All HTTPS traffic → Caddy :80
        ├── infra.nowhere.tw → :8000
        ├── app.nowhere.tw   → :3000
        └── api.nowhere.tw   → :8080
```

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `tunnel_name` | String | PK | Tunnel name (e.g., `prod-main`) |
| `cloudflare_tunnel_id` | String | NOT NULL, UNIQUE | Cloudflare Tunnel UUID |
| `vps_server` | String | NOT NULL, UNIQUE, indexed | VPS server (one tunnel per VPS) |
| `tunnel_target` | String | nullable | `<uuid>.cfargotunnel.com` |
| `credentials_file` | String | nullable | Path to `~/.cloudflared/<uuid>.json` |
| `config_file` | String | nullable | Path to `~/.cloudflared/config.yml` |
| `systemd_service` | String | nullable | Systemd unit name (e.g., `cloudflared-prod-main`) |
| `status` | Enum | NOT NULL | See statuses below |
| `created_at` | DateTime | NOT NULL | Creation timestamp (UTC) |
| `updated_at` | DateTime | nullable | Last update timestamp (auto-updated) |
| `notes` | String | nullable | Optional notes |

**`MainTunnelStatus` enum**:
| Value | Meaning |
|-------|---------|
| `active` | Running and healthy |
| `inactive` | Registered but not running |
| `failed` | Error state |

---

### `service_deployments`

Records the configuration and lifecycle state of every managed service.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `deployment_id` | String | PK | Unique ID (e.g., `deploy_infra-mcp_api_asablue`) |
| `project` | String | NOT NULL, indexed | Project name |
| `service` | String | NOT NULL, indexed | Service name |
| `server` | String | NOT NULL, indexed | VPS server |
| `service_type` | Enum | NOT NULL | See types below |
| `port` | Integer | nullable | Port (from `port_allocations`) |
| `hostname` | String | nullable | Public hostname |
| `tunnel_name` | String | nullable | CF tunnel name |
| `app_path` | String | nullable | Application code path on VPS |
| `static_path` | String | nullable | Static files path (e.g., `/var/www/project/`) |
| `data_path` | String | nullable | Data directory path |
| `log_path` | String | nullable | Log directory path |
| `config_path` | String | nullable | Config files path |
| `caddy_rules` | JSON | nullable | Caddy routing rules object |
| `environment` | JSON | nullable | Environment variables object |
| `systemd_config` | JSON | nullable | Systemd unit configuration object |
| `status` | Enum | NOT NULL, indexed | See statuses below |
| `registered_at` | DateTime | NOT NULL | When `register_service` was called |
| `registered_by` | String | NOT NULL | Always `"mcp-server"` |
| `deployed_at` | DateTime | nullable | When `deploy_service` completed |
| `stopped_at` | DateTime | nullable | When `stop_service` was called |
| `archived_at` | DateTime | nullable | When service was archived |
| `purged_at` | DateTime | nullable | When `purge_service` completed |
| `notes` | Text | nullable | Optional notes |
| `backup_config` | JSON | nullable | Config snapshot saved on archive |

**`ServiceType` enum**:
| Value | Description |
|-------|-------------|
| `flask` | Python Flask application |
| `nodejs` | Node.js application |
| `static` | Static website (Caddy file_server) |
| `docker` | Docker container |
| `flask+static` | Flask API + static frontend |

**`DeploymentStatus` enum**:
| Value | Meaning |
|-------|---------|
| `registered` | Config recorded; not yet deployed to VPS |
| `deployed` | Running on VPS |
| `stopped` | Stopped; files and config retained |
| `archived` | Caddy/tunnel removed; config backed up to `backup_config` |
| `purged` | Fully deleted; excluded from normal queries |

`list_service_deployments` excludes `purged` records by default.

---

## Relationships

The three tables are loosely coupled — foreign key enforcement is not done at the DB level (SQLite FK support is off by default), but the application enforces these logical references:

```
port_allocations
    └── (port, server)
        └── referenced by service_deployments.port + .server

main_tunnels
    └── (tunnel_name)
        └── referenced by service_deployments.tunnel_name

service_deployments
    └── one record per (project, service, server)
```

---

## Example Records

### Port allocation

```python
PortAllocation(
    allocation_id = "alloc_20260513_001",
    port          = 8000,
    project       = "infra-mcp",
    service       = "api",
    server        = "asablue",
    allocated_at  = datetime(2026, 5, 13, ...),
    allocated_by  = "mcp-server",
    status        = AllocationStatus.IN_USE,
    notes         = "infra-mcp FastAPI server"
)
```

### Main tunnel

```python
MainTunnel(
    tunnel_name          = "asablue-main",
    cloudflare_tunnel_id = "ce87659b-4df1-4787-b516-263b628aadf9",
    vps_server           = "asablue",
    tunnel_target        = "ce87659b-4df1-4787-b516-263b628aadf9.cfargotunnel.com",
    credentials_file     = "~/.cloudflared/ce87659b-....json",
    config_file          = "~/.cloudflared/config.yml",
    systemd_service      = "cloudflared-asablue-main",
    status               = MainTunnelStatus.ACTIVE,
)
```

### Service deployment

```python
ServiceDeployment(
    deployment_id  = "deploy_infra-mcp_api_asablue",
    project        = "infra-mcp",
    service        = "api",
    server         = "asablue",
    service_type   = ServiceType.FLASK,
    port           = 8000,
    hostname       = "infra.nowhere.tw",
    tunnel_name    = "asablue-main",
    app_path       = "~/PRJ/infra-mcp/",
    status         = DeploymentStatus.DEPLOYED,
    registered_at  = datetime(2026, 5, 13, ...),
    deployed_at    = datetime(2026, 5, 13, ...),
)
```

---

## Migrations

No migration tooling is currently set up. Schema changes require:
1. Stop the service
2. Rename or back up `resources.db`
3. Restart (SQLAlchemy `create_all` will build new schema)
4. Re-register resources via MCP tools

---

## Changelog

### v2.0 (2026-05-16)
- Rewritten from actual SQLAlchemy models
- Replaced design-phase JSON examples with real column definitions
- Removed "Phase 2 SQLite migration" — SQLite is already in production
- Removed PostgreSQL Phase 3 planning content
- Added enum tables, relationship diagram, example records

### v1.0 (2025-12-28)
- Initial design document (JSON storage, SQLite as future phase)
