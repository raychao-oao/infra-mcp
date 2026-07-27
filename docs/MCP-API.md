# MCP Tools API Reference

**Document version**: v2.0
**Last updated**: 2026-05-16
**Status**: Production

---

## Overview

The Infrastructure MCP Server exposes **38 tools** via JSON-RPC 2.0 over HTTP.

**Endpoint**: `POST /mcp`
**Auth**: `Authorization: Bearer <MCP_API_KEY>` (when `MCP_API_KEY` env var is set)

### Tool Categories

| Category | Tools | Count |
|----------|-------|-------|
| [Port Management](#port-management) | allocate_port, release_port, reconcile_ports, check_listening_ports | 4 |
| [Service Management](#service-management) | register_service, update_service, deploy_service, stop_service, purge_service, upgrade_service, get_service_info, get_service_logs, check_service_health, validate_service_security, audit_all_services, check_firewall, get_caddy_config, restart_service | 14 |
| [Tunnel Registry](#tunnel-registry) | register_main_tunnel, list_main_tunnels, get_tunnel_config | 3 |
| [Cloudflare Tunnel API](#cloudflare-tunnel-api) | create_cloudflare_tunnel, delete_cloudflare_tunnel, list_cloudflare_tunnels, get_tunnel_token, list_public_hostnames, add_public_hostname, remove_public_hostname | 7 |
| [DNS Management](#dns-management) | create_dns_record, update_dns_record, delete_dns_record, list_dns_records | 4 |
| [Cloudflare Access](#cloudflare-access) | create_access_application, delete_access_application, list_access_applications, list_access_policies | 4 |
| [Gitea](#gitea) | create_gitea_repo, list_gitea_repos, get_gitea_repo, delete_gitea_repo | 4 |
| [Inventory](#inventory) | list_resources | 1 |

---

## Port Management

### `allocate_port`

Allocate a port (3000–9999) for a project service. If `preferred_port` is taken, the next available port is assigned.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | ✅ | Project name (lowercase, hyphens allowed) |
| `service` | string | ✅ | Service name (lowercase, hyphens allowed) |
| `preferred_port` | integer | | Preferred port (3000–9999) |
| `server` | string | | VPS server name (default: first in INFRA_SERVERS) |
| `notes` | string | | Optional notes |

---

### `release_port`

Release a port allocation and return it to the pool.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `port` | integer | ✅ | Port number to release (3000–9999) |
| `server` | string | | VPS server name |

---

### `reconcile_ports`

Three-way drift check between what is listening, what the registry has allocated, and what it has released. Only ports in the managed range (3000–9999) can be flagged as unregistered — anything outside it was never allocatable.

A registered port with nothing listening is reported as information, **not** a warning: a reserved port for a stopped or on-demand service is normal, and warning about it teaches people to skim past the rest.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `server` | string | | Filter to one VPS (default: all servers) |

---

### `check_listening_ports`

Check listening ports on a VPS and grade each by reachability. Addresses are parsed, not string-matched: loopback is `none`, a Tailscale (`100.64.0.0/10`, `fd7a:115c:a1e0::/48`) or private address is `low`, a wildcard or public bind is `high`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `server` | string | ✅ | VPS server name |
| `port` | integer | | Specific port to check (optional) |

---

## Service Management

### `register_service`

Register a service deployment configuration in the database. Does **not** perform actual deployment — use `deploy_service` to deploy.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | ✅ | Project name |
| `service` | string | ✅ | Service name |
| `server` | string | ✅ | VPS server name |
| `service_type` | string | ✅ | `flask`, `nodejs`, `static`, `docker`, `flask+static` |
| `port` | integer | | Port number (can be allocated later) |
| `hostname` | string | | Public hostname (e.g., `app.your-domain.com`) |
| `tunnel_name` | string | | Cloudflare tunnel name |
| `app_path` | string | | Application code path (e.g., `~/PRJ/PAC/app/`) |
| `static_path` | string | | Static files path (e.g., `/var/www/pac/`) |
| `data_path` | string | | Data directory path |
| `log_path` | string | | Log directory path |
| `config_path` | string | | Config files path |
| `caddy_rules` | object | | Caddy routing rules as JSON |
| `environment` | object | | Environment variables as JSON |
| `systemd_config` | object | | Systemd service config as JSON |
| `notes` | string | | Optional notes |

Paths are only defaulted where the service type implies them and the deploy step actually creates them. A `docker` service gets none — it comes up from a compose file wherever its author put it, and guessing produces a record that describes a directory nobody made.

---

### `update_service`

Correct a deployment record. **Database only** — nothing is restarted, redeployed, or written on any server. Use `upgrade_service` to change a service's type, and `deploy_service` to change the machine.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | ✅ | Project name |
| `service` | string | ✅ | Service name |
| `server` | string | ✅ | VPS server name |
| `port` | integer | | Port the service listens on |
| `hostname` | string | | Public hostname |
| `tunnel_name` | string | | Cloudflare tunnel name |
| `app_path` `static_path` `data_path` `log_path` `config_path` | string | | Paths |
| `caddy_rules` `environment` `systemd_config` | object | | JSON config |
| `notes` | string | | Replaces the existing notes — it does not append |
| `status` | string | | `registered` / `deployed` / `stopped` / `archived` / `purged`; sets the matching timestamp |
| `clear` | array | | Field names to set back to NULL |
| `force` | boolean | | Allow a hostname or port already held by another live deployment |

Omitting a field leaves it unchanged, so `clear` is the only way to blank one — `null` cannot express the difference between "leave this alone" and "erase this".

Changing `hostname` or `port` to a value another non-purged deployment already holds is refused unless `force` is set. Pointing a record at another service's resources is what makes a later `purge_service` dangerous.

The response reports every field that changed as `from` → `to`, so a correction can be checked rather than assumed.

---

### `deploy_service`

Deploy a registered service to VPS. Allocates port, adds DNS record, generates Caddy config, creates systemd service, and starts it.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | ✅ | Project name |
| `service` | string | ✅ | Service name |
| `server` | string | ✅ | VPS server name |
| `cloudflare_api_token` | string | | Override env var `CF_API_TOKEN` |
| `cloudflare_account_id` | string | | Override env var `CF_ACCOUNT_ID` |

---

### `stop_service`

Stop a running service. Keeps all configuration and files intact.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | ✅ | Project name |
| `service` | string | ✅ | Service name |
| `server` | string | ✅ | VPS server name |

---

### `purge_service`

Completely remove a service and all associated resources: stops service, removes systemd unit, removes Caddy config, releases port. File deletion is opt-in.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | ✅ | Project name |
| `service` | string | ✅ | Service name |
| `server` | string | ✅ | VPS server name |
| `remove_app_files` | boolean | | Delete application files (default: false) |
| `remove_static_files` | boolean | | Delete static files (default: false) |
| `remove_data` | boolean | | Delete data directory (default: false) |
| `remove_logs` | boolean | | Delete log files (default: false) |
| `remove_dns_record` | boolean | | Remove DNS CNAME record (default: false) |
| `dry_run` | boolean | | Report the plan and change nothing (default: false) |
| `force` | boolean | | Proceed despite conflicts (default: false) |

**Refuses to run** when another non-purged deployment on the same server shares this one's hostname, port, `app_path` or `static_path` — purging on the strength of a superseded record removes a *live* service's configuration. The conflicts are named in the response; `force` overrides.

**Reports partial failure honestly.** If any cleanup step fails, the result is `PURGE_INCOMPLETE` with `failed_steps` listing what was left behind, even though the record is marked purged. A purge that leaves the site serving must not report success, and retrying will not help once the record is purged.

The unit and Caddy files it acts on are **located**, not derived from the project and service names.

---

### `upgrade_service`

Change a service's type (e.g., `static` → `flask+static`). Used when a static site needs a backend added.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | ✅ | Project name |
| `service` | string | ✅ | Service name |
| `server` | string | ✅ | VPS server name |
| `new_service_type` | string | ✅ | `flask`, `nodejs`, `flask+static` |
| `app_path` | string | | App path (default: `~/PRJ/{project}/app/`) |
| `notes` | string | | Optional notes |

---

### `get_service_info`

Get detailed information about a deployed service: connection URL, directory structure, port, Caddy config, systemd service name.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | ✅ | Project name |
| `service` | string | ✅ | Service name |
| `server` | string | ✅ | VPS server name |

---

### `get_service_logs`

Retrieve logs from a service component via journalctl (SSH to VPS).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `server` | string | ✅ | VPS server name |
| `project` | string | | Project name (required for `service` component) |
| `service` | string | | Service name (required for `service` component) |
| `component` | string | | `service`, `caddy`, or `tunnel` (default: `service`) |
| `lines` | integer | | Lines to return (default: 50, max: 1000) |
| `since` | string | | journalctl `--since` value (e.g., `"1 hour ago"`, `"30 min ago"`) |

---

### `check_service_health`

Check health status of services and optionally system resources (CPU, memory, disk).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `server` | string | ✅ | VPS server name |
| `project` | string | | Filter to specific project |
| `service` | string | | Filter to specific service |
| `include_system_stats` | boolean | | Include CPU/memory/disk stats (default: false) |

---

### `validate_service_security`

Validate security configuration for a service: Docker port bindings, Caddy `bind` directives, actual listening interfaces. Optionally auto-fix issues.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | ✅ | Project name |
| `service` | string | ✅ | Service name |
| `server` | string | ✅ | VPS server name |
| `auto_fix` | boolean | | Auto-fix detected issues (default: false) |

---

### `audit_all_services`

Run a security audit across every recorded service. Covers all non-purged deployments, not only those marked `deployed`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `server` | string | | Filter to one VPS (default: audit all) |
| `auto_fix` | boolean | | Auto-fix detected issues (default: false) |

Each service comes back as `SECURE`, `VULNERABLE` or `UNVERIFIED`, and the score is computed over the first two only — a check that could not reach a conclusion is neither a pass nor a finding. Servers that could not be reached are listed separately rather than counted as clean.

One `ServerSnapshot` is taken per server and shared by every check on it, so the cost is a few SSH round trips per *server*, not per service.

---

### `check_firewall`

Check whether a host actually has a working, persistent packet filter — not merely a firewall service that reports as enabled.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `server` | string | | Filter to one VPS (default: all servers) |

It reads the live `iptables`/`ip6tables` rules, the package states, and the persistence mechanism, because every casual indicator can lie: a `ufw` package in `rc` state (removed but not purged) leaves `/etc/ufw/ufw.conf` saying `ENABLED=yes` and `systemctl is-enabled ufw` answering `enabled`, while no filter exists at all. That exact combination hid the absence of any firewall on a production host for months.

Accepted ports may carry a source restriction (e.g. `2020 from 172.20.0.0/16`), so a port open only to a private range is not reported as open to the internet.

---

### `get_caddy_config`

Read the Caddy configuration from a VPS (main Caddyfile or service-specific config file).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `server` | string | ✅ | VPS server name |
| `project` | string | | Project name for service-specific config |
| `service` | string | | Service name for service-specific config |

---

### `restart_service`

Restart a service component (application service, Caddy, or Cloudflare tunnel).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | ✅ | Project name |
| `service` | string | ✅ | Service name |
| `server` | string | ✅ | VPS server name |
| `component` | string | | `service`, `caddy`, or `tunnel` (default: `service`) |

---

## Tunnel Registry

These tools manage the local database record of Cloudflare Tunnels that are actually running on VPS servers (one tunnel per VPS, carrying many public hostnames).

### `register_main_tunnel`

Register an existing Cloudflare Tunnel in the local database for tracking. The tunnel should already exist in Cloudflare — use `create_cloudflare_tunnel` to create new ones.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tunnel_name` | string | ✅ | Tunnel name (e.g., `prod-main`) |
| `cloudflare_tunnel_id` | string | ✅ | Cloudflare Tunnel UUID |
| `vps_server` | string | ✅ | VPS server name |
| `tunnel_target` | string | | Tunnel target domain (e.g., `uuid.cfargotunnel.com`) |
| `credentials_file` | string | | Path to credentials JSON file |
| `config_file` | string | | Path to config YAML file |
| `systemd_service` | string | | Systemd service name |
| `notes` | string | | Optional notes |

---

### `list_main_tunnels`

List all registered main tunnels from the local database.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `vps_server` | string | | Filter by VPS server |
| `status` | string | | Filter by status (`active`, `inactive`, `failed`) |

---

### `get_tunnel_config`

Read the Cloudflare Tunnel configuration file from a VPS server via SSH.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `server` | string | ✅ | VPS server name |

---

## Cloudflare Tunnel API

These tools call the Cloudflare API directly to create and manage tunnels and their public hostname routing rules.

### `create_cloudflare_tunnel`

Create a new Cloudflare Tunnel via the Cloudflare API.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | ✅ | Tunnel name (e.g., `prod-main`) |
| `config_src` | string | | `cloudflare` (remotely managed) or `local` (default: `cloudflare`) |

---

### `delete_cloudflare_tunnel`

Delete a Cloudflare Tunnel via the API.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tunnel_id` | string | | Tunnel UUID |
| `tunnel_name` | string | | Tunnel name (used if `tunnel_id` not provided) |
| `force` | boolean | | Force delete even with active connections |

---

### `list_cloudflare_tunnels`

List tunnels in the Cloudflare account.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `include_deleted` | boolean | | Include deleted tunnels |
| `status` | string | | Filter by `active` or `inactive` |
| `name_contains` | string | | Filter by name substring |

---

### `get_tunnel_token`

Get the connection token for a Cloudflare Tunnel (used when installing `cloudflared` on a new VPS).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tunnel_id` | string | | Tunnel UUID |
| `tunnel_name` | string | | Tunnel name (used if `tunnel_id` not provided) |

---

### `list_public_hostnames`

List all public hostname routes configured for a remotely-managed Cloudflare Tunnel.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tunnel_id` | string | | Tunnel UUID |
| `tunnel_name` | string | | Tunnel name (used if `tunnel_id` not provided) |

---

### `add_public_hostname`

Add a public hostname route to a remotely-managed Cloudflare Tunnel. Updates the Cloudflare-side config — no `config.yml` required.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hostname` | string | ✅ | Public hostname (e.g., `app.your-domain.com`) |
| `service` | string | | Backend URL (default: `http://localhost:80`) |
| `tunnel_id` | string | | Tunnel UUID |
| `tunnel_name` | string | | Tunnel name (used if `tunnel_id` not provided) |

---

### `remove_public_hostname`

Remove a public hostname route from a remotely-managed Cloudflare Tunnel.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hostname` | string | ✅ | Public hostname to remove |
| `tunnel_id` | string | | Tunnel UUID |
| `tunnel_name` | string | | Tunnel name (used if `tunnel_id` not provided) |

---

## DNS Management

All DNS tools operate against Cloudflare DNS via the API. The zone is derived automatically from the domain name.

### `create_dns_record`

Create a DNS record in Cloudflare.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `domain` | string | ✅ | Full domain (e.g., `app.your-domain.com`) |
| `record_type` | string | ✅ | `A`, `AAAA`, `CNAME`, `TXT`, `MX`, `NS`, `SRV`, `CAA` |
| `content` | string | ✅ | Record value (IP, target hostname, etc.) |
| `ttl` | integer | | TTL in seconds (1 = auto, default: 1) |
| `proxied` | boolean | | Proxy through Cloudflare (default: false) |
| `priority` | integer | | Priority for MX/SRV records |
| `comment` | string | | Optional comment |
| `tunnel_name` | string | | Use `cloudflared` CLI to create tunnel CNAME instead of API |
| `server` | string | | VPS to run `cloudflared` on (used with `tunnel_name`) |

---

### `update_dns_record`

Update an existing DNS record.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `domain` | string | ✅ | Full domain name |
| `record_id` | string | | Record ID (skips lookup if provided) |
| `record_type` | string | | Record type for lookup (if `record_id` not provided) |
| `content` | string | | New content value |
| `ttl` | integer | | New TTL |
| `proxied` | boolean | | New proxied status |

---

### `delete_dns_record`

Delete a DNS record.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `record_id` | string | | Record ID to delete |
| `domain` | string | | Domain (used to find record) |
| `record_type` | string | | Record type (used with `domain` to find record) |

---

### `list_dns_records`

List DNS records for a zone.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `domain` | string | | Domain/zone to list (e.g., `your-domain.com`) |
| `record_type` | string | | Filter by record type |
| `name_contains` | string | | Filter by name substring |

---

## Cloudflare Access

### `create_access_application`

Create a Cloudflare Access application to protect a URL with authentication.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | ✅ | Application name (e.g., `Grafana Dashboard`) |
| `domain` | string | ✅ | Protected domain (e.g., `metrics.your-domain.com`) |
| `session_duration` | string | | Session TTL (e.g., `24h`, `168h`; default: `24h`) |
| `policy_name` | string | | Name for a new policy to create |
| `policy_emails` | array | | Allowed email addresses for the new policy |
| `policy_id` | string | | Existing policy ID to attach |

---

### `delete_access_application`

Delete a Cloudflare Access application.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `app_id` | string | | Application UUID |
| `domain` | string | | Domain to look up app (if `app_id` not provided) |

---

### `list_access_applications`

List Cloudflare Access applications in the account.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `domain` | string | | Filter by zone derived from domain |

---

### `list_access_policies`

List Cloudflare Access policies.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `domain` | string | | Derive zone from this domain |
| `app_id` | string | | List policies for a specific application |

---

## Gitea

Manages repositories on the self-hosted Gitea instance (`git.your-domain.com`). Credentials are read from the `GITEA_TOKEN` and `GITEA_URL` environment variables.

### `create_gitea_repo`

Create a new repository.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | ✅ | Repository name |
| `description` | string | | Repository description |
| `private` | boolean | | Private repository (default: false) |
| `auto_init` | boolean | | Initialize with README (default: true) |
| `gitignores` | string | | Gitignore template name |
| `license` | string | | License template name |
| `readme` | string | | README template (default: `Default`) |
| `default_branch` | string | | Default branch (default: `main`) |

---

### `list_gitea_repos`

List repositories for the authenticated user.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | | Max repos to return (default: 50, max: 100) |
| `page` | integer | | Pagination page (default: 1) |

---

### `get_gitea_repo`

Get detailed information about a repository.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | ✅ | Repository owner username |
| `repo` | string | ✅ | Repository name |

---

### `delete_gitea_repo`

Delete a repository. **Irreversible.** Requires a `danger_token` to prevent accidental deletion.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | ✅ | Repository owner username |
| `repo` | string | ✅ | Repository name |
| `danger_token` | string | ✅ | Safety token required for irreversible operations |

---

## Inventory

### `list_resources`

List all infrastructure resource allocations with optional filtering.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `resource_type` | string | | `all`, `ports`, `tunnels`, or `deployments` (default: `all`) |
| `project` | string | | Filter by project name |
| `server` | string | | Filter by VPS server |
| `status` | string | | Filter by status |
| `include_released` | boolean | | Include released/archived records (default: false) |

---

## Typical Workflow

### Deploy a new service

```
1. allocate_port         → get a port
2. register_service      → record config in DB
3. deploy_service        → SSH to VPS, set up systemd + Caddy
4. add_public_hostname   → route hostname through CF tunnel
5. get_service_info      → confirm live URL
```

### Protect a service with Cloudflare Access

```
1. create_access_application  → create the Access app + policy
2. (service is now behind CF Access login)
```

### Tear down a service

```
1. remove_public_hostname  → stop routing traffic
2. purge_service           → stop systemd, remove Caddy config, release port
```

---

## Changelog

### v2.0 (2026-05-16)
- Complete rewrite based on actual production code
- Documented all 38 tools (was 4 in v1.0)
- Removed design-phase placeholders
- Added Gitea, Cloudflare Access, Cloudflare Tunnel API sections

### v1.0 (2025-12-28)
- Initial draft (design phase, 4 tools)
