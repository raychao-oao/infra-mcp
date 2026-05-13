# MCP Client Setup Guide

Infrastructure MCP Server client configuration guide

## 📋 Table of Contents

- [Claude Desktop Setup](#claude-desktop-setup)
- [Cloudflare Access Authentication](#cloudflare-access-authentication)
- [Python SDK Integration](#python-sdk-integration)
- [Direct HTTP Calls](#direct-http-calls)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)

---

## Claude Desktop Setup

### 1. Find the Config File

Edit the Claude Desktop MCP config file for your OS:

```bash
# macOS
~/Library/Application Support/Claude/claude_desktop_config.json

# Windows
%APPDATA%\Claude\claude_desktop_config.json

# Linux
~/.config/Claude/claude_desktop_config.json
```

### 2. Basic Configuration (No Auth, for Testing)

If you have temporarily removed Cloudflare Access protection:

```json
{
  "mcpServers": {
    "infrastructure": {
      "type": "http",
      "url": "https://infra.your-domain.com/mcp",
      "headers": {
        "Content-Type": "application/json"
      }
    }
  }
}
```

### 3. Production Configuration (With Service Token)

**Recommended for production**:

```json
{
  "mcpServers": {
    "infrastructure": {
      "type": "http",
      "url": "https://infra.your-domain.com/mcp",
      "headers": {
        "Content-Type": "application/json",
        "CF-Access-Client-Id": "YOUR_SERVICE_TOKEN_CLIENT_ID",
        "CF-Access-Client-Secret": "YOUR_SERVICE_TOKEN_CLIENT_SECRET"
      }
    }
  }
}
```

### 4. Restart Claude Desktop

After configuring, restart Claude Desktop for the changes to take effect.

---

## Cloudflare Access Authentication

### Option A: Service Token (Recommended)

**Best for**: Automated tools, MCP clients, CI/CD

**Steps**:

1. **Log in to Cloudflare Zero Trust Dashboard**
   - Go to https://one.dash.cloudflare.com/
   - Select your account

2. **Create a Service Token**
   ```
   Access → Service Auth → Create Service Token

   Name: MCP Client - [project name]
   Token Duration: 1 year (or as needed)
   ```

3. **Copy the Token**
   - Client ID (a long string)
   - Client Secret (shown only once — save it immediately)

4. **Update the Access Policy**

   Update the Infrastructure MCP Server's Access policy to allow the Service Token:

   ```bash
   # Via Dashboard:
   Access → Applications → Infrastructure MCP Server → Edit

   Add a "Service Auth" rule to the Policy:
   Include:
     - Service Token: [select the token you created]
   ```

5. **Update the Client Configuration**

   Add the Client ID and Secret to your MCP client config (as shown above)

### Option B: User Authentication (Manual)

**Best for**: Manual testing, browser access

**Steps**:

1. Visit https://infra.your-domain.com in a browser
2. Log in with an allowed email address
3. Get the session cookie
4. Include the cookie in API requests

**Not recommended for automation** as sessions expire.

### Option C: Remove Access Protection (Dev/Test Only)

**Warning**: This exposes the MCP Server publicly on the internet

```bash
# SSH to prod
ssh your_user@prod.your-domain.com

# Remove policy via Cloudflare API (not recommended)
# Or temporarily disable the Access Application in Dashboard
```

**Strongly recommended**: Use only during development/testing and restore protection immediately.

---

## Python SDK Integration

### Install MCP SDK

```bash
pip install mcp anthropic-mcp
```

### Basic Usage Example

```python
# infra_client.py
import asyncio
import os
from typing import Optional
import httpx

class InfrastructureMCPClient:
    """Infrastructure MCP Server client"""

    def __init__(
        self,
        base_url: str = "https://infra.your-domain.com/mcp",
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ):
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json"
        }

        # Add Cloudflare Access Service Token
        if client_id and client_secret:
            self.headers["CF-Access-Client-Id"] = client_id
            self.headers["CF-Access-Client-Secret"] = client_secret

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.base_url,
                headers=self.headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments
                    }
                }
            )
            response.raise_for_status()
            return response.json()

    async def allocate_port(
        self,
        project: str,
        service: str,
        preferred_port: Optional[int] = None
    ) -> dict:
        """Allocate a port"""
        return await self.call_tool("allocate_port", {
            "project": project,
            "service": service,
            "preferred_port": preferred_port
        })

    async def register_tunnel(
        self,
        project: str,
        tunnel_name: str,
        hostname: str,
        target_port: int
    ) -> dict:
        """Register a Cloudflare Tunnel"""
        return await self.call_tool("register_tunnel", {
            "project": project,
            "tunnel_name": tunnel_name,
            "hostname": hostname,
            "target_port": target_port
        })

    async def list_resources(self) -> dict:
        """List all resources"""
        return await self.call_tool("list_resources", {})

# Usage example
async def main():
    # Read credentials from environment variables
    client = InfrastructureMCPClient(
        client_id=os.getenv("CF_ACCESS_CLIENT_ID"),
        client_secret=os.getenv("CF_ACCESS_CLIENT_SECRET")
    )

    # Allocate port
    result = await client.allocate_port(
        project="my-app",
        service="web-server",
        preferred_port=5000
    )
    print(f"Allocated: {result}")

    # Register tunnel
    tunnel_result = await client.register_tunnel(
        project="my-app",
        tunnel_name="my-app",
        hostname="myapp.your-domain.com",
        target_port=5000
    )
    print(f"Tunnel registered: {tunnel_result}")

    # List resources
    resources = await client.list_resources()
    print(f"All resources: {resources}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Using in a Project

```python
# your_project/setup.py
from infra_client import InfrastructureMCPClient
import asyncio
import os

async def setup_infrastructure():
    """Set up project infrastructure"""
    client = InfrastructureMCPClient(
        client_id=os.getenv("CF_ACCESS_CLIENT_ID"),
        client_secret=os.getenv("CF_ACCESS_CLIENT_SECRET")
    )

    # 1. Allocate port
    port_result = await client.allocate_port(
        project="user-dashboard",
        service="flask-app"
    )
    port = port_result["result"]["content"][0]["text"].split()[-1]

    # 2. Register tunnel
    await client.register_tunnel(
        project="user-dashboard",
        tunnel_name="user-dashboard",
        hostname="dashboard.your-domain.com",
        target_port=int(port)
    )

    print(f"✅ Infrastructure setup complete!")
    print(f"   Port: {port}")
    print(f"   URL: https://dashboard.your-domain.com")

if __name__ == "__main__":
    asyncio.run(setup_infrastructure())
```

---

## Direct HTTP Calls

### Using curl

```bash
# Set auth variables
export CF_CLIENT_ID="your_client_id"
export CF_CLIENT_SECRET="your_client_secret"

# Allocate port
curl -X POST https://infra.your-domain.com/mcp \
  -H "Content-Type: application/json" \
  -H "CF-Access-Client-Id: $CF_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_CLIENT_SECRET" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "allocate_port",
      "arguments": {
        "project": "my-app",
        "service": "web-server",
        "preferred_port": 5000
      }
    }
  }'

# List resources
curl -X POST https://infra.your-domain.com/mcp \
  -H "Content-Type: application/json" \
  -H "CF-Access-Client-Id: $CF_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_CLIENT_SECRET" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "list_resources",
      "arguments": {}
    }
  }'
```

### Using Postman/Insomnia

1. **Set up the Request**
   - Method: POST
   - URL: https://infra.your-domain.com/mcp

2. **Set Headers**
   ```
   Content-Type: application/json
   CF-Access-Client-Id: YOUR_CLIENT_ID
   CF-Access-Client-Secret: YOUR_CLIENT_SECRET
   ```

3. **Set Body** (JSON)
   ```json
   {
     "jsonrpc": "2.0",
     "id": 1,
     "method": "tools/call",
     "params": {
       "name": "allocate_port",
       "arguments": {
         "project": "test-project",
         "service": "api-server",
         "preferred_port": 8080
       }
     }
   }
   ```

---

## Usage Examples

### Example 1: New Project Initialization

```bash
# 1. Create project
mkdir my-new-app
cd my-new-app

# 2. Set up infrastructure client
cat > setup_infra.py <<'EOF'
import asyncio
from infra_client import InfrastructureMCPClient
import os

async def main():
    client = InfrastructureMCPClient(
        client_id=os.getenv("CF_ACCESS_CLIENT_ID"),
        client_secret=os.getenv("CF_ACCESS_CLIENT_SECRET")
    )

    # Allocate port
    port = await client.allocate_port(
        project="my-new-app",
        service="web"
    )

    # Register tunnel
    tunnel = await client.register_tunnel(
        project="my-new-app",
        tunnel_name="my-new-app",
        hostname="my-new-app.your-domain.com",
        target_port=int(port)
    )

    print("✅ Infrastructure ready!")

asyncio.run(main())
EOF

# 3. Run setup
python setup_infra.py
```

### Example 2: Using from Claude Desktop

In a Claude Desktop conversation:

```
User: I want to build a new blog system. Set up the infrastructure for me.

Claude: I'll request resources from the Infrastructure MCP Server.

[Using allocate_port]
project: "blog-system"
service: "nextjs-app"
preferred_port: 3000

Result: ✅ Port 3000 allocated

[Using register_tunnel]
project: "blog-system"
tunnel_name: "blog"
hostname: "blog.your-domain.com"
target_port: 3000

Result: ✅ Tunnel registered

Your blog system infrastructure is ready:
- Port: 3000
- Public URL: https://blog.your-domain.com
- Ready to start development!
```

### Example 3: CI/CD Integration

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  setup-infrastructure:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Infrastructure
        env:
          CF_ACCESS_CLIENT_ID: ${{ secrets.CF_ACCESS_CLIENT_ID }}
          CF_ACCESS_CLIENT_SECRET: ${{ secrets.CF_ACCESS_CLIENT_SECRET }}
        run: |
          curl -X POST https://infra.your-domain.com/mcp \
            -H "Content-Type: application/json" \
            -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
            -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
            -d '{
              "jsonrpc": "2.0",
              "id": 1,
              "method": "tools/call",
              "params": {
                "name": "allocate_port",
                "arguments": {
                  "project": "'"$GITHUB_REPOSITORY"'",
                  "service": "production"
                }
              }
            }'
```

---

## Troubleshooting

### Issue 1: Connection Refused (403 Forbidden)

**Cause**: Cloudflare Access authentication failed

**Resolution**:
1. Verify the Service Token is correct
2. Confirm the Access Policy includes your Service Token
3. Check that the headers are formatted correctly

```bash
# Test Service Token
curl -I https://infra.your-domain.com/health \
  -H "CF-Access-Client-Id: YOUR_ID" \
  -H "CF-Access-Client-Secret: YOUR_SECRET"

# Should return 200, not 302 or 403
```

### Issue 2: Tool Call Fails

**Cause**: Malformed MCP request

**Resolution**:
Check the JSON-RPC format:
```json
{
  "jsonrpc": "2.0",         // must be "2.0"
  "id": 1,                  // any number
  "method": "tools/call",   // always "tools/call"
  "params": {
    "name": "tool_name",    // tool name
    "arguments": {          // tool parameters
      // ...
    }
  }
}
```

### Issue 3: Claude Desktop Can't See the MCP Server

**Cause**: Config file has wrong format or wrong location

**Resolution**:
1. Confirm the config file location is correct
2. Validate JSON syntax (use JSONLint.com)
3. Restart Claude Desktop
4. Check Claude Desktop logs

```bash
# macOS logs
~/Library/Logs/Claude/

# Look for MCP-related errors
```

### Issue 4: Port Conflict

**Cause**: The requested port is already used by another project

**Resolution**:
1. Don't specify `preferred_port` — let the system auto-allocate
2. Use `list_resources` to see allocated ports
3. Choose a different unused port

### Issue 5: Can't Create Tunnel

**Cause**: Hostname already exists or Cloudflare configuration issue

**Resolution**:
1. Use `list_resources` to see registered tunnels
2. Choose a different hostname
3. Check Cloudflare DNS settings

---

## Security Best Practices

### 1. Protect the Service Token

```bash
# Use environment variables, never hardcode in code
export CF_ACCESS_CLIENT_ID="..."
export CF_ACCESS_CLIENT_SECRET="..."

# Or use a .env file (add to .gitignore)
echo "CF_ACCESS_CLIENT_ID=..." >> .env
echo "CF_ACCESS_CLIENT_SECRET=..." >> .env

# Load in code
from dotenv import load_dotenv
load_dotenv()
```

### 2. Rotate Tokens Regularly

- Rotate Service Tokens every 3-6 months
- Test the new token before deleting the old one
- Record the creation date and purpose of each token

### 3. Principle of Least Privilege

- Use different Service Tokens for different projects
- Restrict token scope in the Access Policy
- Monitor token usage

---

## Support

If you have issues:
1. Check the Troubleshooting section of this document
2. Review [MCP Server logs](https://infra.your-domain.com/health)
3. Contact the project maintainer

---

**Last updated**: 2025-12-28
**Version**: v1.0
