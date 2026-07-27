# Infrastructure MCP Server — Architecture

**Document version**: v2.0
**Last updated**: 2026-05-16
**Status**: Production

---

## Summary

Infrastructure MCP Server is a self-hosted HTTP MCP server that centralises infrastructure resource management. Claude Code connects to it as a remote MCP server and uses its 38 tools to allocate ports, register services, manage Cloudflare Tunnels/DNS/Access, and control Gitea repositories — all without directly SSH-ing into servers or editing config files.

---

## Architecture Overview

```
┌──────────────────────────────────────┐
│          Claude Code (client)         │
│   (any project, any machine)          │
└──────────────┬───────────────────────┘
               │ JSON-RPC 2.0 over HTTPS
               │ Authorization: Bearer <MCP_API_KEY>
               ▼
┌──────────────────────────────────────────────────────┐
│        Infrastructure MCP Server (FastAPI)            │
│        https://infra.your-domain.com/mcp              │
│        running on: the `prod` VPS                     │
│                                                       │
│  ┌──────────────────────────────────────────────┐    │
│  │              Tool Handlers (38 tools)         │    │
│  │  ports │ services │ tunnels │ dns │ access    │    │
│  │  gitea │ cloudflare-api │ inventory           │    │
│  └──────────────────┬───────────────────────────┘    │
│                     │                                 │
│         ┌───────────┴────────────┐                   │
│         ▼                        ▼                   │
│  ┌─────────────┐        ┌──────────────────┐         │
│  │ SQLiteStore  │        │  External APIs   │         │
│  │ resources.db │        │  - Cloudflare    │         │
│  └─────────────┘        │  - Gitea         │         │
│                          └──────────────────┘         │
└──────────────────────────┬───────────────────────────┘
                           │ SSH (paramiko)
         ┌─────────────────┼──────────────────┐
         ▼                 ▼                  ▼
   ┌──────────┐      ┌──────────┐      ┌──────────┐
   │   prod   │      │ staging  │      │  dev1 /  │
   │          │      │          │      │   dev2   │
   └──────────┘      └──────────┘      └──────────┘
```

---

## Component Breakdown

### FastAPI Application (`main/server.py`)

- **Protocol**: MCP over HTTP (JSON-RPC 2.0, `POST /mcp`)
- **Auth**: Optional `Bearer` token middleware (constant-time comparison)
- **CORS**: Allows `localhost` + the configured `INFRA_DOMAIN`
- **Lifecycle**: `asynccontextmanager` initialises and closes the SQLite connection at startup/shutdown
- **Error handling**: `RequestValidationError` handler returns JSON-RPC `-32600`; `InvalidParamsError` returns `-32602`

### Tool Layer (`main/tools/`)

Tool modules are imported directly into `server.py`. Each module exports:
- A `validate_*_input(arguments)` async function that returns `(bool, error_str)`
- A main `async def tool_name(store, ...)` function that returns a result dict

Tool files are grouped:
```
main/tools/
├── allocate_port.py
├── release_port.py
├── list_resources.py
├── register_main_tunnel.py
├── list_main_tunnels.py
├── register_service.py
├── deploy_service.py
├── stop_service.py
├── purge_service.py
├── upgrade_service.py
├── get_service_info.py
├── check_listening_ports.py
├── validate_service_security.py
├── audit_all_services.py
├── restart_service.py
├── get_caddy_config.py
├── get_tunnel_config.py
├── get_service_logs.py
├── check_service_health.py
└── cloudflare/
    ├── dns.py       (create/update/delete/list)
    ├── access.py    (create/delete/list apps + list policies)
    └── tunnel.py    (create/delete/list tunnel, token, hostnames)
└── gitea/
    ├── create_repo.py
    ├── list_repos.py
    ├── get_repo.py
    └── delete_repo.py
```

### Database Layer (`main/db/sqlite_store.py`)

- **Engine**: SQLAlchemy async with SQLite
- **Database file**: `~/PRJ/infra-mcp/configs/resources.db` (production)
- Stores port allocations, service registrations, and main tunnel records
- See [`Data-Models.md`](./Data-Models.md) for table schemas

### Config (`main/config.py`)

Reads server topology from environment:
- `INFRA_SERVERS` — list of known VPS server names
- `INFRA_DEFAULT_SERVER` — default server when not specified
- `INFRA_DOMAIN` — server's own public hostname

---

## Deployment

### Production

```
Server:     prod (any VPS; 2 vCPU / 2 GB is ample)
Directory:  ~/PRJ/infra-mcp/
Bind:       127.0.0.1:8000  (systemd service)
Public URL: https://infra.your-domain.com/mcp  (via Cloudflare Tunnel + CF Access)
Database:   ~/PRJ/infra-mcp/configs/resources.db
```

**Two-layer authentication**:
1. Cloudflare Access (email OTP / service token) — protects the public hostname
2. `MCP_API_KEY` Bearer token — validates the MCP client itself

**systemd service**: `infra-mcp-api.service`

### Local Development

```bash
cd ~/PROJECTS/infra-mcp/repo
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in tokens
uvicorn main.server:app --reload --port 8000
```

---

## VPS Connectivity

Tools that act on VPS servers (service management, log retrieval, config reading) connect via SSH using [paramiko](https://www.paramiko.org/). SSH credentials are read from env vars:
- `SSH_KEY_PATH` — path to private key (default: `~/.ssh/id_ed25519`)
- Server hostnames/users defined in `INFRA_SERVERS` config

**Example server set** (aliases are yours to choose; they must match `~/.ssh/config`):
| Alias | Role |
|-------|------|
| `prod` | Production |
| `staging` | Staging |
| `dev1`, `dev2` | Development |

---

## External API Integrations

### Cloudflare

Environment variables:
- `CF_API_TOKEN` — Cloudflare API token (Zone:Edit, Access:Edit, Tunnel:Edit)
- `CF_ACCOUNT_ID` — Cloudflare account ID
- `CF_ZONE_ID` — default zone (can be derived from domain)

Used by: DNS tools, Access tools, Tunnel API tools

### Gitea

Environment variables:
- `GITEA_URL` — Gitea base URL (e.g., `https://git.your-domain.com`)
- `GITEA_TOKEN` — personal access token

---

## Security Model

| Layer | Mechanism |
|-------|-----------|
| Public network | Cloudflare Tunnel + CF Access (email/service token) |
| MCP client auth | `MCP_API_KEY` Bearer token (constant-time comparison) |
| VPS access | SSH key (`~/.ssh/id_ed25519`), no password |
| Cloudflare API | Scoped API token in env var |
| Service binding | All services bind to `127.0.0.1` only (enforced by `check_listening_ports` / `validate_service_security`) |

---

## Typical Workflows

### New service deployment
```
1. allocate_port          → reserve a port in DB
2. register_service       → record service config in DB
3. deploy_service         → SSH to VPS: create systemd + Caddy config + start
4. add_public_hostname    → add route to CF Tunnel (no config.yml needed)
```

### Security audit
```
1. audit_all_services     → scan all registered services for misconfigs
2. validate_service_security {project, service} → deep-check one service
3. check_listening_ports  → verify no service is exposed beyond 127.0.0.1
```

### Tear down a service
```
1. remove_public_hostname → stop routing traffic from CF Tunnel
2. purge_service          → stop systemd, remove Caddy config, release port
```

---

## Changelog

### v2.0 (2026-05-16)
- Rewritten to reflect production state
- Removed design-phase content (JSON DB, Phase 1/2/3 goals)
- Documented actual deployment (prod, CF Tunnel + CF Access auth)
- Updated tool count (38, not 4)
- Added VPS connectivity, external API, and security model sections

### v1.0 (2025-12-28)
- Initial design document
