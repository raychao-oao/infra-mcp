"""Get Gitea repository information."""
from typing import Dict, Any
from .base import GiteaClient


async def get_gitea_repo(
    owner: str,
    repo: str
) -> Dict[str, Any]:
    """
    Get detailed information about a specific repository.

    Args:
        owner: Repository owner username
        repo: Repository name

    Returns:
        Dict containing:
        - success: True if retrieved successfully
        - repo: Repository information
          - id: Repository ID
          - name: Repository name
          - full_name: Full repository name (owner/repo)
          - description: Repository description
          - private: Whether the repository is private
          - html_url: Repository web URL
          - ssh_url: SSH clone URL
          - clone_url: HTTPS clone URL
          - default_branch: Default branch name
          - language: Primary programming language
          - size: Repository size in KB
          - stars_count: Number of stars
          - forks_count: Number of forks
          - watchers_count: Number of watchers
          - open_issues_count: Number of open issues
          - open_pr_counter: Number of open pull requests
          - created_at: Creation timestamp
          - updated_at: Last update timestamp
          - permissions: User permissions (admin, push, pull)
          - has_issues: Whether issues are enabled
          - has_wiki: Whether wiki is enabled
          - has_pull_requests: Whether PRs are enabled
        - error: Error message if failed
    """
    try:
        client = GiteaClient()

        # Get repository info
        repo_info = await client.get(f"repos/{owner}/{repo}")

        return {
            "success": True,
            "repo": {
                "id": repo_info["id"],
                "name": repo_info["name"],
                "full_name": repo_info["full_name"],
                "description": repo_info.get("description", ""),
                "private": repo_info["private"],
                "html_url": repo_info["html_url"],
                "ssh_url": repo_info["ssh_url"],
                "clone_url": repo_info["clone_url"],
                "default_branch": repo_info["default_branch"],
                "language": repo_info.get("language", ""),
                "size": repo_info["size"],
                "stars_count": repo_info["stars_count"],
                "forks_count": repo_info["forks_count"],
                "watchers_count": repo_info["watchers_count"],
                "open_issues_count": repo_info["open_issues_count"],
                "open_pr_counter": repo_info["open_pr_counter"],
                "created_at": repo_info["created_at"],
                "updated_at": repo_info["updated_at"],
                "permissions": repo_info.get("permissions", {}),
                "has_issues": repo_info["has_issues"],
                "has_wiki": repo_info["has_wiki"],
                "has_pull_requests": repo_info["has_pull_requests"]
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}"
        }
