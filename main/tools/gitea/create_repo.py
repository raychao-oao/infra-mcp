"""Create a new Gitea repository."""
from typing import Dict, Any
from .base import GiteaClient


async def create_gitea_repo(
    name: str,
    description: str = "",
    private: bool = False,
    auto_init: bool = True,
    gitignores: str = "",
    license: str = "",
    readme: str = "Default",
    default_branch: str = "main"
) -> Dict[str, Any]:
    """
    Create a new repository in Gitea.

    Args:
        name: Repository name (required)
        description: Repository description (optional)
        private: Whether the repository is private (default: False)
        auto_init: Initialize repository with README (default: True)
        gitignores: Gitignore template name (optional)
        license: License template name (optional)
        readme: README template (default: "Default")
        default_branch: Default branch name (default: "main")

    Returns:
        Dict containing:
        - success: True if created successfully
        - repo_id: Repository ID
        - full_name: Full repository name (owner/repo)
        - html_url: Repository web URL
        - ssh_url: SSH clone URL
        - clone_url: HTTPS clone URL
        - error: Error message if failed
    """
    try:
        client = GiteaClient()

        # Prepare repository data
        repo_data = {
            "name": name,
            "description": description,
            "private": private,
            "auto_init": auto_init,
            "default_branch": default_branch
        }

        # Add optional fields if provided
        if gitignores:
            repo_data["gitignores"] = gitignores
        if license:
            repo_data["license"] = license
        if readme:
            repo_data["readme"] = readme

        # Create repository
        result = await client.post("user/repos", repo_data)

        return {
            "success": True,
            "repo_id": result["id"],
            "full_name": result["full_name"],
            "html_url": result["html_url"],
            "ssh_url": result["ssh_url"],
            "clone_url": result["clone_url"],
            "private": result["private"],
            "default_branch": result["default_branch"],
            "created_at": result["created_at"]
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}"
        }
