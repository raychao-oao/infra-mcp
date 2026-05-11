"""Base Gitea API client."""
import os
import httpx
from typing import Optional, Dict, Any


class GiteaClient:
    """Gitea API client for repository management."""

    def __init__(self):
        """Initialize Gitea client with environment variables."""
        self.api_url = os.getenv("GITEA_API_URL", "")
        self.api_token = os.getenv("GITEA_API_TOKEN")
        self.base_url = os.getenv("GITEA_BASE_URL", "")

        if not self.api_url:
            raise ValueError("GITEA_API_URL environment variable is required")
        if not self.api_token:
            raise ValueError("GITEA_API_TOKEN environment variable is required")

    @property
    def headers(self) -> Dict[str, str]:
        """Get API request headers."""
        return {
            "Authorization": f"token {self.api_token}",
            "Content-Type": "application/json"
        }

    async def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make GET request to Gitea API."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/{endpoint}",
                headers=self.headers,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make POST request to Gitea API."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/{endpoint}",
                headers=self.headers,
                json=data,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def patch(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make PATCH request to Gitea API."""
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.api_url}/{endpoint}",
                headers=self.headers,
                json=data,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def delete(self, endpoint: str) -> None:
        """Make DELETE request to Gitea API."""
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.api_url}/{endpoint}",
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
