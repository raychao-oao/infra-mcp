"""Delete a Gitea repository."""
import os
from typing import Dict, Any
from .base import GiteaClient


async def delete_gitea_repo(
    owner: str,
    repo: str,
    danger_token: str
) -> Dict[str, Any]:
    """
    Delete a repository from Gitea.

    WARNING: This operation is IRREVERSIBLE. All repository data,
    including issues, pull requests, and wiki, will be permanently deleted.

    SECURITY: Requires a special danger token to prevent accidental deletion.

    Args:
        owner: Repository owner username
        repo: Repository name
        danger_token: Special token for dangerous operations (required)

    Returns:
        Dict containing:
        - success: True if deleted successfully
        - message: Confirmation message
        - deleted_repo: Full repository name that was deleted
        - error: Error message if failed
    """
    try:
        # Verify danger token
        expected_token = os.getenv("GITEA_DANGER_TOKEN")

        if not expected_token:
            return {
                "success": False,
                "error": "GITEA_DANGER_TOKEN not configured on server. Please contact administrator."
            }

        if danger_token != expected_token:
            return {
                "success": False,
                "error": "Invalid danger token. Access denied. This incident will be logged."
            }

        # Additional protection: Check for protected repositories
        protected_repos = ["oao-infra", "services"]
        if repo in protected_repos:
            return {
                "success": False,
                "error": f"Repository '{repo}' is protected and cannot be deleted."
            }

        client = GiteaClient()

        # Delete repository
        await client.delete(f"repos/{owner}/{repo}")

        return {
            "success": True,
            "message": "Repository deleted successfully",
            "deleted_repo": f"{owner}/{repo}"
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}"
        }
