"""
Infrastructure MCP Client

簡單的 Python 客戶端，用於與 Infrastructure MCP Server 互動。

使用方式:
    from infra_client import InfrastructureMCPClient

    client = InfrastructureMCPClient(
        client_id=os.getenv("CF_ACCESS_CLIENT_ID"),
        client_secret=os.getenv("CF_ACCESS_CLIENT_SECRET")
    )

    # 分配 port
    result = await client.allocate_port("my-app", "web-server")
"""

import asyncio
import os
from typing import Optional, Dict, Any
import httpx


class InfrastructureMCPClient:
    """Infrastructure MCP Server 客戶端"""

    def __init__(
        self,
        base_url: str = "https://infra.nowhere.tw/mcp",
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        timeout: int = 30
    ):
        """
        初始化 MCP 客戶端

        Args:
            base_url: MCP Server URL
            client_id: Cloudflare Access Service Token Client ID
            client_secret: Cloudflare Access Service Token Client Secret
            timeout: 請求超時時間（秒）
        """
        self.base_url = base_url
        self.timeout = timeout
        self.headers = {
            "Content-Type": "application/json"
        }

        # 加入 Cloudflare Access Service Token
        if client_id and client_secret:
            self.headers["CF-Access-Client-Id"] = client_id
            self.headers["CF-Access-Client-Secret"] = client_secret

    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict:
        """
        呼叫 MCP tool

        Args:
            tool_name: 工具名稱
            arguments: 工具參數

        Returns:
            MCP 回應

        Raises:
            httpx.HTTPError: HTTP 請求失敗
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
        分配 port 給專案服務

        Args:
            project: 專案名稱
            service: 服務名稱
            preferred_port: 偏好的 port (可選)

        Returns:
            分配結果，包含 port 號碼

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
        註冊 Cloudflare Tunnel

        Args:
            project: 專案名稱
            tunnel_name: Tunnel 名稱
            hostname: 公開 hostname (e.g., myapp.nowhere.tw)
            target_port: 目標 port

        Returns:
            註冊結果

        Example:
            >>> result = await client.register_tunnel(
            ...     "my-app",
            ...     "my-app-tunnel",
            ...     "myapp.nowhere.tw",
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
        部署 Tunnel 到 VPS

        Args:
            project: 專案名稱
            server: VPS 伺服器名稱 (e.g., "asablue")
            tunnel_name: Tunnel 名稱
            service_port: 服務 port

        Returns:
            部署結果

        Example:
            >>> result = await client.deploy_tunnel(
            ...     "my-app",
            ...     "asablue",
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
        列出所有已分配的資源

        Returns:
            資源列表，包含 ports 和 tunnels

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
        檢查 MCP Server 健康狀態

        Returns:
            True 如果 server 正常運作

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


# 便利函數
async def setup_project_infrastructure(
    project_name: str,
    service_name: str,
    hostname: str,
    preferred_port: Optional[int] = None,
    deploy_server: Optional[str] = None
) -> Dict[str, Any]:
    """
    一站式設定專案基礎設施

    Args:
        project_name: 專案名稱
        service_name: 服務名稱
        hostname: 公開 hostname
        preferred_port: 偏好的 port (可選)
        deploy_server: 部署伺服器 (可選，如 "asablue")

    Returns:
        設定結果，包含分配的 port 和 tunnel 資訊

    Example:
        >>> result = await setup_project_infrastructure(
        ...     "my-blog",
        ...     "nextjs",
        ...     "blog.nowhere.tw",
        ...     preferred_port=3000,
        ...     deploy_server="asablue"
        ... )
        >>> print(f"Your app is ready at https://{result['hostname']}")
    """
    client = InfrastructureMCPClient(
        client_id=os.getenv("CF_ACCESS_CLIENT_ID"),
        client_secret=os.getenv("CF_ACCESS_CLIENT_SECRET")
    )

    # 1. 分配 port
    port_result = await client.allocate_port(
        project_name,
        service_name,
        preferred_port
    )

    # 從回應中解析 port
    port_text = port_result["result"]["content"][0]["text"]
    allocated_port = int(port_text.split()[-1])

    # 2. 註冊 tunnel
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

    # 3. 如果指定了伺服器，部署 tunnel
    if deploy_server:
        await client.deploy_tunnel(
            project_name,
            deploy_server,
            tunnel_name,
            allocated_port
        )
        result["deployed_to"] = deploy_server

    return result


# 範例使用
async def example_usage():
    """示範如何使用 InfrastructureMCPClient"""

    # 方法 1: 手動步驟
    print("=== 方法 1: 手動步驟 ===")
    client = InfrastructureMCPClient(
        client_id=os.getenv("CF_ACCESS_CLIENT_ID"),
        client_secret=os.getenv("CF_ACCESS_CLIENT_SECRET")
    )

    # 檢查健康狀態
    if await client.health_check():
        print("✅ MCP Server is healthy")
    else:
        print("❌ MCP Server is down")
        return

    # 分配 port
    port_result = await client.allocate_port(
        project="example-app",
        service="web-server",
        preferred_port=5000
    )
    print(f"Port allocated: {port_result}")

    # 註冊 tunnel
    tunnel_result = await client.register_tunnel(
        project="example-app",
        tunnel_name="example-app",
        hostname="example.nowhere.tw",
        target_port=5000
    )
    print(f"Tunnel registered: {tunnel_result}")

    # 列出資源
    resources = await client.list_resources()
    print(f"All resources: {resources}")

    # 方法 2: 一站式設定
    print("\n=== 方法 2: 一站式設定 ===")
    result = await setup_project_infrastructure(
        project_name="my-blog",
        service_name="nextjs",
        hostname="blog.nowhere.tw",
        preferred_port=3000
    )
    print(f"✅ Infrastructure ready!")
    print(f"   Project: {result['project']}")
    print(f"   Port: {result['port']}")
    print(f"   URL: https://{result['hostname']}")


if __name__ == "__main__":
    # 執行範例
    asyncio.run(example_usage())
