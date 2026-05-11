"""
Cloudflare API base client and utilities.

Provides shared functionality for all Cloudflare tools.
"""

import os
import httpx
from typing import Any, Optional
from functools import lru_cache


class CloudflareAPIError(Exception):
    """Exception raised for Cloudflare API errors."""

    def __init__(self, message: str, errors: list = None, status_code: int = None):
        self.message = message
        self.errors = errors or []
        self.status_code = status_code
        super().__init__(self.message)


class CloudflareClient:
    """Cloudflare API client."""

    BASE_URL = "https://api.cloudflare.com/client/v4"

    def __init__(
        self,
        api_token: Optional[str] = None,
        account_id: Optional[str] = None,
    ):
        self.api_token = api_token or os.getenv("CLOUDFLARE_API_TOKEN")
        self.account_id = account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID")

        if not self.api_token:
            raise CloudflareAPIError("CLOUDFLARE_API_TOKEN is required")
        if not self.account_id:
            raise CloudflareAPIError("CLOUDFLARE_ACCOUNT_ID is required")

        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        json_data: dict = None,
    ) -> dict:
        """Make an API request to Cloudflare."""
        url = f"{self.BASE_URL}{endpoint}"

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self.headers,
                params=params,
                json=json_data,
                timeout=30.0,
            )

            data = response.json()

            if not data.get("success", False):
                errors = data.get("errors", [])
                error_messages = [e.get("message", str(e)) for e in errors]
                raise CloudflareAPIError(
                    message="; ".join(error_messages) or "Unknown Cloudflare API error",
                    errors=errors,
                    status_code=response.status_code,
                )

            return data

    async def get(self, endpoint: str, params: dict = None) -> dict:
        """GET request."""
        return await self._request("GET", endpoint, params=params)

    async def post(self, endpoint: str, json_data: dict = None) -> dict:
        """POST request."""
        return await self._request("POST", endpoint, json_data=json_data)

    async def put(self, endpoint: str, json_data: dict = None) -> dict:
        """PUT request."""
        return await self._request("PUT", endpoint, json_data=json_data)

    async def patch(self, endpoint: str, json_data: dict = None) -> dict:
        """PATCH request."""
        return await self._request("PATCH", endpoint, json_data=json_data)

    async def delete(self, endpoint: str) -> dict:
        """DELETE request."""
        return await self._request("DELETE", endpoint)

    # Zone helpers
    async def get_zone_id(self, domain: str) -> str:
        """Get zone ID for a domain.

        Tries 2-level root first (example.com), then 3-level (example.co.uk)
        to handle ccTLD public suffixes like .co.uk, .com.tw, .com.au.
        """
        parts = domain.split(".")
        candidates = []
        if len(parts) >= 2:
            candidates.append(".".join(parts[-2:]))
        if len(parts) >= 3:
            candidates.append(".".join(parts[-3:]))

        for candidate in candidates:
            data = await self.get("/zones", params={"name": candidate})
            zones = data.get("result", [])
            if zones:
                return zones[0]["id"]

        raise CloudflareAPIError(f"Zone not found for domain: {domain}")

    async def list_zones(self) -> list:
        """List all zones in the account."""
        data = await self.get("/zones", params={"per_page": 50})
        return data.get("result", [])


def get_client(
    api_token: Optional[str] = None,
    account_id: Optional[str] = None,
) -> CloudflareClient:
    """Get a Cloudflare client instance."""
    return CloudflareClient(api_token=api_token, account_id=account_id)
