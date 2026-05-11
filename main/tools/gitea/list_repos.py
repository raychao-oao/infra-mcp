"""List Gitea repositories."""
from typing import Dict, Any, List
from .base import GiteaClient


async def list_gitea_repos(
    limit: int = 50,
    page: int = 1
) -> Dict[str, Any]:
    """
    List all repositories for the authenticated user.

    Args:
        limit: Maximum number of repositories to return (default: 50, max: 100)
        page: Page number for pagination (default: 1)

    Returns:
        Dict containing:
        - success: True if retrieved successfully
        - total: Total number of repositories
        - repos: List of repository information
          - id: Repository ID
          - name: Repository name
          - full_name: Full repository name (owner/repo)
          - description: Repository description
          - private: Whether the repository is private
          - html_url: Repository web URL
          - ssh_url: SSH clone URL
          - clone_url: HTTPS clone URL
          - default_branch: Default branch name
          - created_at: Creation timestamp
          - updated_at: Last update timestamp
        - error: Error message if failed
    """
    try:
        client = GiteaClient()

        # Get repositories
        repos = await client.get("user/repos", params={
            "limit": min(limit, 100),
            "page": page
        })

        # Format repository list
        repo_list = [
            {
                "id": repo["id"],
                "name": repo["name"],
                "full_name": repo["full_name"],
                "description": repo.get("description", ""),
                "private": repo["private"],
                "html_url": repo["html_url"],
                "ssh_url": repo["ssh_url"],
                "clone_url": repo["clone_url"],
                "default_branch": repo["default_branch"],
                "language": repo.get("language", ""),
                "size": repo["size"],
                "stars_count": repo["stars_count"],
                "forks_count": repo["forks_count"],
                "created_at": repo["created_at"],
                "updated_at": repo["updated_at"]
            }
            for repo in repos
        ]

        return {
            "success": True,
            "total": len(repo_list),
            "repos": repo_list
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}"
        }
