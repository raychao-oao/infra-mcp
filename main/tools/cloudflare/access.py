"""
Cloudflare Access application management tools.

Provides tools for managing Cloudflare Access applications and policies.
"""

from typing import Any, Optional
from main.tools.cloudflare.base import get_client, CloudflareAPIError


def validate_create_access_application_input(arguments: dict) -> dict:
    """Validate input for create_access_application."""
    errors = []

    if not arguments.get("name"):
        errors.append("name is required")

    if not arguments.get("domain"):
        errors.append("domain is required (e.g., 'app.your-domain.com')")

    if errors:
        return {"valid": False, "errors": errors}

    return {"valid": True}


def validate_delete_access_application_input(arguments: dict) -> dict:
    """Validate input for delete_access_application."""
    errors = []

    if not arguments.get("app_id") and not arguments.get("domain"):
        errors.append("Either app_id or domain is required")

    if errors:
        return {"valid": False, "errors": errors}

    return {"valid": True}


def validate_list_access_applications_input(arguments: dict) -> dict:
    """Validate input for list_access_applications."""
    # No required parameters
    return {"valid": True}


def validate_list_access_policies_input(arguments: dict) -> dict:
    """Validate input for list_access_policies."""
    # No required parameters
    return {"valid": True}


async def create_access_application(
    name: str,
    domain: str,
    session_duration: str = "24h",
    policy_name: Optional[str] = None,
    policy_emails: Optional[list] = None,
    policy_id: Optional[str] = None,
    auto_redirect_to_identity: bool = True,
    **kwargs,
) -> dict:
    """
    Create a Cloudflare Access application.

    Args:
        name: Application name (e.g., 'Grafana Dashboard')
        domain: Protected domain (e.g., 'metrics.your-domain.com')
        session_duration: Session duration (e.g., '24h', '168h')
        policy_name: Name for new policy (if creating)
        policy_emails: List of allowed emails for the policy
        policy_id: Existing policy ID to attach
        auto_redirect_to_identity: Auto redirect to identity provider

    Returns:
        dict with created application details
    """
    client = get_client()
    zone_id = await client.get_zone_id(domain)

    # Create application
    app_data = {
        "name": name,
        "domain": domain,
        "type": "self_hosted",
        "session_duration": session_duration,
        "auto_redirect_to_identity": auto_redirect_to_identity,
    }

    data = await client.post(
        f"/zones/{zone_id}/access/apps",
        json_data=app_data,
    )
    app = data.get("result", {})
    app_id = app.get("id")

    result = {
        "success": True,
        "message": f"Access application created: {name}",
        "application": {
            "id": app_id,
            "name": app.get("name"),
            "domain": app.get("domain"),
            "aud": app.get("aud"),
            "session_duration": app.get("session_duration"),
        },
        "policy": None,
    }

    # Create policy if emails provided
    if policy_emails and not policy_id:
        policy_data = {
            "name": policy_name or f"{name} Policy",
            "decision": "allow",
            "include": [
                {
                    "email": {"email": email}
                }
                for email in policy_emails
            ],
        }

        policy_response = await client.post(
            f"/zones/{zone_id}/access/apps/{app_id}/policies",
            json_data=policy_data,
        )
        policy = policy_response.get("result", {})
        result["policy"] = {
            "id": policy.get("id"),
            "name": policy.get("name"),
            "decision": policy.get("decision"),
        }
        result["message"] += f" with policy '{policy.get('name')}'"

    return result


async def delete_access_application(
    app_id: Optional[str] = None,
    domain: Optional[str] = None,
    zone_id: Optional[str] = None,
    **kwargs,
) -> dict:
    """
    Delete a Cloudflare Access application.

    Args:
        app_id: Application ID to delete
        domain: Domain to find application (if app_id not provided)
        zone_id: Zone ID (optional)

    Returns:
        dict with deletion confirmation
    """
    client = get_client()

    # Get zone_id and find app if needed
    if not zone_id:
        if domain:
            zone_id = await client.get_zone_id(domain)
        else:
            raise CloudflareAPIError("Either zone_id or domain is required")

    # Find app by domain if app_id not provided
    if not app_id:
        if not domain:
            raise CloudflareAPIError("domain is required when app_id not provided")

        data = await client.get(f"/zones/{zone_id}/access/apps")
        apps = data.get("result", [])

        matching_app = None
        for app in apps:
            if app.get("domain") == domain:
                matching_app = app
                break

        if not matching_app:
            raise CloudflareAPIError(f"No Access application found for domain: {domain}")

        app_id = matching_app["id"]
        app_name = matching_app.get("name")
    else:
        app_name = app_id

    # Delete the application
    await client.delete(f"/zones/{zone_id}/access/apps/{app_id}")

    return {
        "success": True,
        "message": f"Access application deleted: {app_name}",
        "deleted_app_id": app_id,
    }


async def list_access_applications(
    domain: Optional[str] = None,
    zone_id: Optional[str] = None,
    **kwargs,
) -> dict:
    """
    List Cloudflare Access applications.

    Args:
        domain: Domain to derive zone from
        zone_id: Zone ID (optional if domain provided)

    Returns:
        dict with list of Access applications
    """
    client = get_client()

    # If no zone specified, list all zones first
    if not zone_id and not domain:
        zones = await client.list_zones()

        all_apps = []
        for zone in zones:
            try:
                data = await client.get(f"/zones/{zone['id']}/access/apps")
                apps = data.get("result", [])
                for app in apps:
                    app["zone_name"] = zone["name"]
                    all_apps.append(app)
            except CloudflareAPIError:
                continue

        formatted_apps = [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "domain": a.get("domain"),
                "zone": a.get("zone_name"),
                "type": a.get("type"),
                "session_duration": a.get("session_duration"),
            }
            for a in all_apps
        ]

        return {
            "success": True,
            "message": f"Found {len(formatted_apps)} Access applications across all zones",
            "applications": formatted_apps,
        }

    # Get zone_id
    if not zone_id:
        zone_id = await client.get_zone_id(domain)

    # Get applications
    data = await client.get(f"/zones/{zone_id}/access/apps")
    apps = data.get("result", [])

    formatted_apps = [
        {
            "id": a.get("id"),
            "name": a.get("name"),
            "domain": a.get("domain"),
            "type": a.get("type"),
            "session_duration": a.get("session_duration"),
            "aud": a.get("aud"),
        }
        for a in apps
    ]

    return {
        "success": True,
        "message": f"Found {len(formatted_apps)} Access applications",
        "zone_id": zone_id,
        "applications": formatted_apps,
    }


async def list_access_policies(
    domain: Optional[str] = None,
    zone_id: Optional[str] = None,
    app_id: Optional[str] = None,
    **kwargs,
) -> dict:
    """
    List Cloudflare Access policies.

    Args:
        domain: Domain to derive zone from
        zone_id: Zone ID (optional if domain provided)
        app_id: Application ID to list policies for (optional)

    Returns:
        dict with list of Access policies
    """
    client = get_client()

    # Get zone_id
    if not zone_id:
        if domain:
            zone_id = await client.get_zone_id(domain)
        else:
            raise CloudflareAPIError("Either zone_id or domain is required")

    # If app_id provided, get policies for that app
    if app_id:
        data = await client.get(f"/zones/{zone_id}/access/apps/{app_id}/policies")
        policies = data.get("result", [])

        formatted_policies = [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "decision": p.get("decision"),
                "include": p.get("include"),
                "exclude": p.get("exclude"),
                "require": p.get("require"),
            }
            for p in policies
        ]

        return {
            "success": True,
            "message": f"Found {len(formatted_policies)} policies for app {app_id}",
            "app_id": app_id,
            "policies": formatted_policies,
        }

    # Otherwise, get all apps and their policies
    apps_data = await client.get(f"/zones/{zone_id}/access/apps")
    apps = apps_data.get("result", [])

    all_policies = []
    for app in apps:
        try:
            data = await client.get(f"/zones/{zone_id}/access/apps/{app['id']}/policies")
            policies = data.get("result", [])
            for policy in policies:
                policy["app_name"] = app.get("name")
                policy["app_id"] = app.get("id")
                all_policies.append(policy)
        except CloudflareAPIError:
            continue

    formatted_policies = [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "app_name": p.get("app_name"),
            "app_id": p.get("app_id"),
            "decision": p.get("decision"),
        }
        for p in all_policies
    ]

    return {
        "success": True,
        "message": f"Found {len(formatted_policies)} policies across {len(apps)} applications",
        "zone_id": zone_id,
        "policies": formatted_policies,
    }
