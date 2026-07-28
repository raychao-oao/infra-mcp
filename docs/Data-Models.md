# Infrastructure MCP Server — Data Models

**Document version**: v2.1
**Last updated**: 2026-07-28
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
        ├── infra.your-domain.com → :8000
        ├── app.your-domain.com   → :3000
        └── api.your-domain.com   → :8080
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
| `deployment_id` | String | PK | Unique ID (e.g., `deploy_infra-mcp_api_prod`) |
| `project` | String | NOT NULL, indexed | Project name |
| `service` | String | NOT NULL, indexed | Service name |
| `server` | String | NOT NULL, indexed | VPS server |
| `service_type` | Enum | NOT NULL | See types below |
| `port` | Integer | nullable | Port (from `port_allocations`) |
| `hostname` | String | nullable | Public hostname |
| `tunnel_name` | String | nullable | CF tunnel name |
| `layer` | Enum | NOT NULL, indexed | `standard` (this server allocated the paths) or `nonstandard` (paths are observations) |
| `project_root` | String | nullable | Project root, e.g. `~/PRJ/{project}/` |
| `deploy_root` | String | nullable | Static file deploy root, e.g. `/var/www/{project}/` (file-serving types only) |
| `workspace_url` | String | nullable | Private workspace repo URL; `NULL` = no source of truth recorded |
| `path_overrides` | JSON | nullable | Sub-path deviations from convention, keyed by `app`/`static`/`data`/`config`/`log` |
| `caddy_rules` | JSON | nullable | Caddy routing rules object |
| `environment` | JSON | nullable | Environment variables object |
| `systemd_config` | JSON | nullable | Systemd unit configuration object |
| `status` | Enum | NOT NULL, indexed | See statuses below |
| `registered_at` | DateTime | NOT NULL | When `register_service` or `record_service` was called |
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

**`ServiceLayer` enum**:
| Value | Description |
|-------|-------------|
| `standard` | This server allocated the resources and deploys the service; `project_root`/`deploy_root` are decisions, sub-paths derived by convention |
| `nonstandard` | The service already exists, built by its own project; every path is an observation — nothing is derived or enforced |

**`DeploymentStatus` enum**:
| Value | Meaning |
|-------|---------|
| `registered` | Config recorded; not yet deployed to VPS |
| `deployed` | Running on VPS |
| `stopped` | Stopped; files and config retained |
| `archived` | Caddy/tunnel removed; config backed up to `backup_config` |
| `purged` | Fully deleted; excluded from normal queries |

`list_service_deployments` excludes `purged` records by default.

Only `project_root` and `deploy_root` are stored. Concrete sub-paths — `app/`,
`data/`, `config/`, the log directory, and the resolved static-files path — are
never persisted as their own columns; they are derived at read time by
`resolve_paths()` from the roots + convention + `path_overrides`, and only for
`layer=standard` records. A `layer=nonstandard` record derives nothing: any
sub-path worth recording has to go in `path_overrides` explicitly, because
there is no convention to derive it from.

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
    server        = "prod",
    allocated_at  = datetime(2026, 5, 13, ...),
    allocated_by  = "mcp-server",
    status        = AllocationStatus.IN_USE,
    notes         = "infra-mcp FastAPI server"
)
```

### Main tunnel

```python
MainTunnel(
    tunnel_name          = "prod-main",
    cloudflare_tunnel_id = "a1b2c3d4-0000-0000-0000-000000000000",
    vps_server           = "prod",
    tunnel_target        = "a1b2c3d4-0000-0000-0000-000000000000.cfargotunnel.com",
    credentials_file     = "~/.cloudflared/a1b2c3d4-....json",
    config_file          = "~/.cloudflared/config.yml",
    systemd_service      = "cloudflared-prod-main",
    status               = MainTunnelStatus.ACTIVE,
)
```

### Service deployment

```python
ServiceDeployment(
    deployment_id  = "deploy_infra-mcp_api_prod",
    project        = "infra-mcp",
    service        = "api",
    server         = "prod",
    service_type   = ServiceType.FLASK,
    port           = 8000,
    hostname       = "infra.your-domain.com",
    tunnel_name    = "prod-main",
    layer          = ServiceLayer.STANDARD,
    project_root   = "~/PRJ/infra-mcp/",
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
