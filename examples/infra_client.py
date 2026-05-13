"""
Infrastructure MCP Client

A simple Python client for interacting with the Infrastructure MCP Server.

Usage:
    from infra_client import InfrastructureMCPClient

    client = InfrastructureMCPClient(
        client_id=os.getenv("CF_ACCESS_CLIENT_ID"),
        client_secret=os.getenv("CF_ACCESS_CLIENT_SECRET")
    )

    # Allocate a port
    result = await client.allocate_port("my-app", "web-server")
"""

import asyncio
import os
from typing import Optional, Dict, Any
import httpx


class InfrastructureMCPClient:
    """Client for the Infrastructure MCP Server"""

    def __init__(
        self,
        base_url: str = "https://infra.your-domain.com/mcp",
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        timeout: int = 30
    ):
        """
        Initialize the MCP client.

        Args:
            base_url: MCP Server URL
            client_id: Cloudflare Access Service Token Client ID
            client_secret: Cloudflare Access Service Token Client Secret
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.timeout = timeout
        self.headers = {
            "Content-Type": "application/json"
        }

        # Add Cloudflare Access Service Token headers if provided
        if client_id and client_secret:
            self.headers["CF-Access-Client-Id"] = client_id
            self.headers["CF-Access-Client-Secret"] = client_secret

    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict:
        """
        Call an MCP tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            MCP response dict

        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
    ) -> Dict:
        """
        Allocate a port for a project service.

        Args:
            project: Project name
            service: Service name
            preferred_port: Preferred port number (optional)

        Returns:
            Allocation result containing the assigned port number

        Example:
            >>> result = await client.allocate_port("my-app", "web-server", 5000)
            >>> print(result)
            {
                "result": {
                    "content": [{
                        "type": "text",
                        "text": "Port 5000 allocated to my-app/web-server"
                    }]
                }
            }
        """
        return await self._call_tool("allocate_port", {
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
    ) -> Dict:
        """
        Register a Cloudflare Tunnel.

        Args:
            project: Project name
            tunnel_name: Tunnel name
            hostname: Public hostname (e.g., myapp.your-domain.com)
            target_port: Target port number

        Returns:
            Registration result

        Example:
            >>> result = await client.register_tunnel(
            ...     "my-app",
            ...     "my-app-tunnel",
            ...     "myapp.your-domain.com",
            ...     5000
            ... )
        """
        return await self._call_tool("register_tunnel", {
            "project": project,
            "tunnel_name": tunnel_name,
            "hostname": hostname,
            "target_port": target_port
        })

    async def deploy_tunnel(
        self,
        project: str,
        server: str,
        tunnel_name: str,
        service_port: int
    ) -> Dict:
        """
        Deploy a tunnel to a VPS server.

        Args:
            project: Project name
            server: VPS server name (e.g., "prod")
            tunnel_name: Tunnel name
            service_port: Service port number

        Returns:
            Deployment result

        Example:
            >>> result = await client.deploy_tunnel(
            ...     "my-app",
            ...     "prod",
            ...     "my-app-tunnel",
            ...     5000
            ... )
        """
        return await self._call_tool("deploy_tunnel", {
            "project": project,
            "server": server,
            "tunnel_name": tunnel_name,
            "service_port": service_port
        })

    async def list_resources(self) -> Dict:
        """
        List all allocated resources.

        Returns:
            Resource list containing ports and tunnels

        Example:
            >>> resources = await client.list_resources()
            >>> print(resources)
            {
                "result": {
                    "content": [{
                        "type": "text",
                        "text": "Allocated Ports:\\n- my-app/web: 5000\\n\\nTunnels:\\n- my-app-tunnel"
                    }]
                }
            }
        """
        return await self._call_tool("list_resources", {})

    async def health_check(self) -> bool:
        """
        Check MCP Server health status.

        Returns:
            True if the server is running normally

        Example:
            >>> is_healthy = await client.health_check()
            >>> print(f"Server healthy: {is_healthy}")
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.base_url.replace("/mcp", "/health"),
                    headers=self.headers
                )
                return response.status_code == 200
        except Exception:
            return False


# Convenience function
async def setup_project_infrastructure(
    project_name: str,
    service_name: str,
    hostname: str,
    preferred_port: Optional[int] = None,
    deploy_server: Optional[str] = None
) -> Dict[str, Any]:
    """
    One-shot project infrastructure setup.

    Args:
        project_name: Project name
        service_name: Service name
        hostname: Public hostname
        preferred_port: Preferred port number (optional)
        deploy_server: Deployment server name (optional, e.g. "prod")

    Returns:
        Setup result containing the allocated port and tunnel info

    Example:
        >>> result = await setup_project_infrastructure(
        ...     "my-blog",
        ...     "nextjs",
        ...     "blog.your-domain.com",
        ...     preferred_port=3000,
        ...     deploy_server="prod"
        ... )
        >>> print(f"Your app is ready at https://{result['hostname']}")
    """
    client = InfrastructureMCPClient(
        client_id=os.getenv("CF_ACCESS_CLIENT_ID"),
        client_secret=os.getenv("CF_ACCESS_CLIENT_SECRET")
    )

    # 1. Allocate port
    port_result = await client.allocate_port(
        project_name,
        service_name,
        preferred_port
    )

    # Parse the allocated port from the response
    port_text = port_result["result"]["content"][0]["text"]
    allocated_port = int(port_text.split()[-1])

    # 2. Register tunnel
    tunnel_name = f"{project_name}-{service_name}"
    await client.register_tunnel(
        project_name,
        tunnel_name,
        hostname,
        allocated_port
    )

    result = {
        "project": project_name,
        "service": service_name,
        "port": allocated_port,
        "tunnel": tunnel_name,
        "hostname": hostname
    }

    # 3. Deploy tunnel if a server was specified
    if deploy_server:
        await client.deploy_tunnel(
            project_name,
            deploy_server,
            tunnel_name,
            allocated_port
        )
        result["deployed_to"] = deploy_server

    return result


# Example usage
async def example_usage():
    """Demonstrates how to use InfrastructureMCPClient."""

    # Method 1: Manual step-by-step
    print("=== Method 1: Manual steps ===")
    client = InfrastructureMCPClient(
        client_id=os.getenv("CF_ACCESS_CLIENT_ID"),
        client_secret=os.getenv("CF_ACCESS_CLIENT_SECRET")
    )

    # Check health
    if await client.health_check():
        print("✅ MCP Server is healthy")
    else:
        print("❌ MCP Server is down")
        return

    # Allocate port
    port_result = await client.allocate_port(
        project="example-app",
        service="web-server",
        preferred_port=5000
    )
    print(f"Port allocated: {port_result}")

    # Register tunnel
    tunnel_result = await client.register_tunnel(
        project="example-app",
        tunnel_name="example-app",
        hostname="example.your-domain.com",
        target_port=5000
    )
    print(f"Tunnel registered: {tunnel_result}")

    # List resources
    resources = await client.list_resources()
    print(f"All resources: {resources}")

    # Method 2: One-shot setup
    print("\n=== Method 2: One-shot setup ===")
    result = await setup_project_infrastructure(
        project_name="my-blog",
        service_name="nextjs",
        hostname="blog.your-domain.com",
        preferred_port=3000
    )
    print(f"✅ Infrastructure ready!")
    print(f"   Project: {result['project']}")
    print(f"   Port: {result['port']}")
    print(f"   URL: https://{result['hostname']}")


if __name__ == "__main__":
    asyncio.run(example_usage())
