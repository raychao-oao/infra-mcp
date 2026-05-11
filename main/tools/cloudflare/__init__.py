"""
Cloudflare management tools for Infrastructure MCP Server.

Modules:
- dns: DNS record management
- access: Cloudflare Access application management
- tunnel: Cloudflare Tunnel API management
"""

from main.tools.cloudflare.dns import (
    create_dns_record,
    update_dns_record,
    delete_dns_record,
    list_dns_records,
    validate_create_dns_record_input,
    validate_update_dns_record_input,
    validate_delete_dns_record_input,
    validate_list_dns_records_input,
)

from main.tools.cloudflare.access import (
    create_access_application,
    delete_access_application,
    list_access_applications,
    list_access_policies,
    validate_create_access_application_input,
    validate_delete_access_application_input,
    validate_list_access_applications_input,
    validate_list_access_policies_input,
)

from main.tools.cloudflare.tunnel import (
    create_cloudflare_tunnel,
    delete_cloudflare_tunnel,
    list_cloudflare_tunnels,
    get_tunnel_token,
    validate_create_cloudflare_tunnel_input,
    validate_delete_cloudflare_tunnel_input,
    validate_list_cloudflare_tunnels_input,
    validate_get_tunnel_token_input,
)

__all__ = [
    # DNS
    "create_dns_record",
    "update_dns_record",
    "delete_dns_record",
    "list_dns_records",
    "validate_create_dns_record_input",
    "validate_update_dns_record_input",
    "validate_delete_dns_record_input",
    "validate_list_dns_records_input",
    # Access
    "create_access_application",
    "delete_access_application",
    "list_access_applications",
    "list_access_policies",
    "validate_create_access_application_input",
    "validate_delete_access_application_input",
    "validate_list_access_applications_input",
    "validate_list_access_policies_input",
    # Tunnel
    "create_cloudflare_tunnel",
    "delete_cloudflare_tunnel",
    "list_cloudflare_tunnels",
    "get_tunnel_token",
    "validate_create_cloudflare_tunnel_input",
    "validate_delete_cloudflare_tunnel_input",
    "validate_list_cloudflare_tunnels_input",
    "validate_get_tunnel_token_input",
]
