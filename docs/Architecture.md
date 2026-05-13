# Infrastructure MCP Server - Complete Architecture Design

**Document version**: v1.0
**Last updated**: 2025-12-28
**Status**: Design Phase

---

## 📖 Executive Summary

Infrastructure Management MCP is a centralized infrastructure resource management system built on the Model Context Protocol (MCP). It provides standardized tools through an MCP Server so that all projects can request and manage infrastructure resources (VPS, Cloudflare Tunnels, Ports, Domains) through Claude Code — avoiding resource conflicts and improving organizational scalability.

### Core Value

1. **Centralized management, conflict prevention**
   - All port allocations, tunnel registrations, and domain usage are recorded in a central database
   - Automatically detects and prevents resource conflicts (duplicate ports, subdomain collisions, etc.)

2. **Standardized request workflow**
   - Projects request resources through unified MCP tools
   - No need to manually edit config files or SSH into servers
   - Reduces human error and configuration inconsistencies

3. **Extensible architecture**
   - Easily add new VPS servers
   - Supports multiple Cloudflare accounts
   - Can integrate additional cloud services in the future (AWS, GCP, etc.)

4. **Full traceability**
   - Records who requested what resource and when
   - Simplifies auditing and cost analysis
   - Streamlines resource reclamation

---

## 🎯 Design Goals

### Must Have (Phase 1)
- ✅ MCP Server core framework (Claude Desktop integration)
- ✅ 4 core MCP tools (allocate_port, register_tunnel, deploy_tunnel, list_resources)
- ✅ JSON file-based resource database
- ✅ Basic resource conflict detection
- ✅ prod VPS support
- ✅ Reference deployment scripts (optional)

### Should Have (Phase 2)
- 📋 SQLite/PostgreSQL database
- 📋 Automatic resource reclamation
- 📋 Usage statistics and cost analysis
- 📋 Web UI (resource usage dashboard)
- 📋 Multi-VPS server support

### Could Have (Phase 3)
- 💡 Cloudflare Workers auto-deployment
- 💡 Cloudflare R2 storage management
- 💡 Automated SSL certificate management
- 💡 Load balancing configuration
- 💡 Backup and disaster recovery

---

## 🏗️ System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude Code / Claude Desktop             │
│                    (using MCP tools in any project)          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ MCP Protocol
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Infrastructure MCP Server                 │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐        │
│  │ allocate    │  │ register    │  │ deploy       │        │
│  │ _port       │  │ _tunnel     │  │ _tunnel      │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘        │
│         │                 │                 │                │
│         └─────────────────┴─────────────────┘                │
│                           │                                  │
│                           ▼                                  │
│                  ┌─────────────────┐                         │
│                  │ Resource Manager │                         │
│                  │  (allocation logic) │                      │
│                  └────────┬─────────┘                         │
│                           │                                  │
│         ┌─────────────────┼─────────────────┐                │
│         ▼                 ▼                 ▼                │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐         │
│  │ Port Pool   │  │ Tunnel      │  │ VPS Server   │         │
│  │ Manager     │  │ Registry    │  │ Deployer     │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘         │
│         │                 │                 │                │
└─────────┼─────────────────┼─────────────────┼────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
   ┌─────────────────────────────────────────────────┐
   │          Resource Database (JSON/SQLite)        │
   │  - Port allocations                              │
   │  - Tunnel registrations                          │
   │  - Server deployments                            │
   │  - Resource ownership                            │
   └──────────────────────┬──────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   ┌──────────┐   ┌─────────────┐  ┌────────────┐
   │ prod     │   │ Cloudflare  │  │ Future VPS │
   │ VPS      │   │ API         │  │ Servers    │
   └──────────┘   └─────────────┘  └────────────┘
```

### Component Details

#### 1. MCP Server Core
**Responsibilities**:
- Handle MCP tool calls from Claude
- Parameter validation and error handling
- Return results to Claude

**Technology**:
- Python 3.11+
- MCP SDK (Anthropic)
- FastAPI (optional, for future Web UI)

#### 2. Resource Manager
**Responsibilities**:
- Unified resource allocation logic
- Conflict detection (duplicate ports, subdomain collisions)
- Resource state tracking (allocated, in-use, released)

**Key functions**:
```python
class ResourceManager:
    def allocate_port(self, project, service, preferred_port=None):
        # 1. Check if preferred_port is available
        # 2. If not, allocate the next available port from the pool
        # 3. Record allocation in the database
        # 4. Return the allocated port
        pass

    def register_tunnel(self, project, tunnel_name, hostname, target_port):
        # 1. Verify hostname is not already in use
        # 2. Verify target_port is allocated to this project
        # 3. Create tunnel config file
        # 4. Register in the database
        pass
```

#### 3. Port Pool Manager
**Responsibilities**:
- Manage available port range (3000-9999)
- Track allocated ports
- Support port reclamation

**Port allocation strategy**:
- System ports (0-1023): Reserved, not used
- Registered ports (1024-2999): Reserved, not used
- User ports (3000-9999): Allocatable range
- Preferred ports are honored if available
- Otherwise, the smallest unallocated port in range is assigned

#### 4. Tunnel Registry
**Responsibilities**:
- Manage Cloudflare Tunnel configurations
- Generate tunnel config YAML
- Update DNS records (via Cloudflare API)
- Create/update systemd services on VPS

**Tunnel lifecycle**:
```
1. Registration phase (register_tunnel)
   - Create config-<tunnel-name>.yml
   - Configure DNS CNAME record

2. Deployment phase (deploy_tunnel)
   - Copy config to VPS
   - Create systemd service
   - Start tunnel

3. Running phase
   - Monitor tunnel status (future)
   - Log management

4. Reclamation phase (future)
   - Stop tunnel
   - Delete DNS record
   - Release port
```

#### 5. VPS Server Deployer
**Responsibilities**:
- SSH into VPS servers
- Deploy applications (Flask, Node.js, etc.)
- Create systemd services
- Start and monitor services

**Supported deployment types**:
- Flask application (Python)
- Express/Fastify application (Node.js)
- Static site (Caddy/Nginx)
- Docker container (Phase 2)

---

## 📊 Data Models

### Resource Allocation Record

```json
{
  "allocation_id": "alloc_20251228_001",
  "resource_type": "port",
  "resource_value": 3000,
  "project": "my-app",
  "service": "web-server",
  "allocated_at": "2025-12-28T10:00:00Z",
  "allocated_by": "claude-code",
  "status": "in-use",
  "notes": "Main application server"
}
```

### Tunnel Registration Record

```json
{
  "tunnel_id": "tunnel_20251228_001",
  "tunnel_name": "myapp",
  "project": "my-app",
  "hostname": "myapp.your-domain.com",
  "target_service": "http://localhost:3000",
  "target_port": 3000,
  "vps_server": "prod",
  "config_path": "/home/your_user/.cloudflared/config-myapp.yml",
  "credentials_file": "/home/your_user/.cloudflared/<tunnel-id>.json",
  "systemd_service": "cloudflared-myapp.service",
  "registered_at": "2025-12-28T10:15:00Z",
  "status": "active",
  "dns_configured": true
}
```

### VPS Server Configuration

```yaml
servers:
  prod:
    hostname: prod.your-domain.com
    ip: YOUR_SERVER_IP
    location: Germany
    provider: your-provider
    plan: RS 1000 G12
    specs:
      cpu: AMD EPYC 9645 (4 cores)
      ram: 7.8GB
      disk: 256GB NVMe
      network: 1Gbps
    os: Debian 13 (trixie)
    ssh:
      user: your_user
      port: 22
      key_path: ~/.ssh/id_ed25519
    capabilities:
      - flask_app
      - nodejs_app
      - static_site
      - cloudflared_tunnel
    port_range:
      start: 3000
      end: 9999
    status: active
```

See [`Data-Models.md`](./Data-Models.md) for detailed data model definitions.

---

## 🔧 MCP Tools Specification

### 1. allocate_port

**Purpose**: Allocate an available port for a project service

**Input parameters**:
```json
{
  "project": "string (required)",
  "service": "string (required)",
  "preferred_port": "number (optional)"
}
```

**Output**:
```json
{
  "success": true,
  "allocated_port": 3000,
  "allocation_id": "alloc_20251228_001",
  "message": "Port 3000 allocated to my-app/web-server"
}
```

**Usage example**:
```
<user>: My project needs a port to run a web server
<claude>: Using allocate_port tool
  project: "my-app"
  service: "web-server"
  preferred_port: 3000
<result>: Port 3000 allocated to my-app/web-server
```

### 2. register_tunnel

**Purpose**: Register a Cloudflare Tunnel configuration

**Input parameters**:
```json
{
  "project": "string (required)",
  "tunnel_name": "string (required)",
  "hostname": "string (required)",
  "target_port": "number (required)",
  "vps_server": "string (default: prod)"
}
```

**Output**:
```json
{
  "success": true,
  "tunnel_id": "tunnel_20251228_001",
  "hostname": "myapp.your-domain.com",
  "config_path": "/home/your_user/.cloudflared/config-myapp.yml",
  "dns_instructions": "CNAME record created: myapp.your-domain.com -> <tunnel-id>.cfargotunnel.com",
  "message": "Tunnel myapp registered successfully"
}
```

### 3. deploy_tunnel

**Purpose**: Deploy a Cloudflare Tunnel to a VPS server

**Input parameters**:
```json
{
  "tunnel_name": "string (required, must be registered first)",
  "server": "string (default: prod)"
}
```

**Output**:
```json
{
  "success": true,
  "tunnel_name": "myapp",
  "server": "prod",
  "service_name": "cloudflared-myapp.service",
  "status": "running",
  "hostname": "myapp.your-domain.com",
  "connections": 4,
  "message": "Tunnel deployed and started successfully"
}
```

### 4. list_resources

**Purpose**: List all resource usage

**Input parameters**:
```json
{
  "resource_type": "all|port|tunnel|deployment (default: all)",
  "project": "string (optional, filter by project)",
  "server": "string (optional, filter by server)"
}
```

**Output**:
```json
{
  "success": true,
  "resources": {
    "ports": [
      {
        "port": 3000,
        "project": "my-app",
        "service": "web-server",
        "status": "in-use"
      }
    ],
    "tunnels": [
      {
        "name": "myapp",
        "hostname": "myapp.your-domain.com",
        "project": "my-app",
        "status": "active"
      }
    ],
    "deployments": [
      {
        "project": "my-app",
        "server": "prod",
        "service": "myapp-web.service",
        "status": "running"
      }
    ]
  },
  "summary": {
    "total_ports_allocated": 1,
    "total_tunnels_active": 1,
    "total_deployments": 1
  }
}
```

See [`MCP-API.md`](./MCP-API.md) for the complete API specification.

---

## 🔐 Security Considerations

### Authentication & Authorization

**Phase 1** (current design):
- MCP Server runs locally and only accepts requests from Claude Desktop
- SSH key-based authentication to VPS servers
- Cloudflare API token stored in environment variables

**Phase 2** (future improvements):
- Multi-user support (team members)
- Role-based access control (RBAC)
- Audit logs for all resource operations

### Secrets Management

- SSH private keys: `~/.ssh/id_ed25519`
- Cloudflare API token: environment variable `CLOUDFLARE_API_TOKEN`
- VPS sudo password: environment variable (prod has NOPASSWD sudo, not needed currently)
- Future: consider HashiCorp Vault or 1Password CLI

### Network Security

- All VPS servers only open SSH port 22
- All web traffic goes through Cloudflare Tunnel (Zero Trust)
- Tunnel credential file permissions set to 600 (owner read/write only)

---

## 🚀 Deployment Strategy

### Development Environment

```bash
# Local machine
cd ~/infra-mcp/
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set environment variables
export CLOUDFLARE_API_TOKEN="your_token_here"

# Start MCP server
python main/mcp_server.py
```

### Production Environment

**MCP Server location**: Local development machine (Mac)
- Reason: MCP Server needs to integrate with Claude Desktop
- Database: Local JSON file (Phase 1) or SQLite (Phase 2)

**Resource deployment target**: VPS servers (prod, etc.)
- Remote deployment via SSH
- systemd manages service lifecycle

**Future considerations**:
- MCP Server can be deployed to the cloud (for remote team support)
- Protect with HTTPS and authentication tokens

---

## 📈 Scalability Plan

### Multi-VPS Support

```yaml
servers:
  prod:
    # ... existing config

  server2:
    hostname: server2.your-domain.com
    # ... new server config

  server3:
    hostname: server3.your-domain.com
    # ... new server config
```

Resource Manager will automatically:
- Select the server with the lowest load
- Or let the user specify the target server

### Multiple Cloudflare Accounts

```yaml
cloudflare_accounts:
  primary:
    email: your@email.com
    api_token: ${CLOUDFLARE_API_TOKEN}
    domains:
      - your-domain.com

  client_a:
    email: client@example.com
    api_token: ${CLIENT_A_CF_TOKEN}
    domains:
      - client-domain.com
```

### Port Pool Expansion

When a single server runs low on ports:
- Automatically allocate on other VPS servers
- Or prompt the user to add more servers

---

## 🎯 Success Metrics

### Phase 1 Completion Criteria

- ✅ Successfully allocate at least 5 ports via MCP tools
- ✅ Successfully register at least 3 Cloudflare Tunnels
- ✅ Successfully deploy at least 2 applications to prod
- ✅ Zero port conflicts, zero subdomain collisions
- ✅ Full resource usage records (traceable)

### Phase 2 Goals

- 📊 Support at least 3 VPS servers
- 📊 Manage 20+ active tunnels
- 📊 Resource usage dashboard (Web UI)
- 📊 Automated resource reclamation

### Phase 3 Vision

- 💡 Support an entire organization (10+ team members)
- 💡 CI/CD pipeline integration
- 💡 Cost tracking and optimization recommendations
- 💡 Disaster recovery and high availability

---

## 📚 References

- [Model Context Protocol (MCP) Documentation](https://modelcontextprotocol.io/)
- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [systemd Service Management](https://www.freedesktop.org/software/systemd/man/systemd.service.html)

---

**Document maintenance**: Updated as the project evolves
**Next review**: 2025-01-15
**Maintainer**: Infrastructure Team
