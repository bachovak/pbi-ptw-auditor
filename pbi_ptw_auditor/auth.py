"""Token acquisition for the Power BI Admin REST API.

Supports two flows:
  - Service principal (client-credentials) — default, non-interactive.
  - Device code — interactive, for admins who want a one-off run.

Tokens and secrets are never logged.
"""

from __future__ import annotations

import logging

import msal

logger = logging.getLogger(__name__)

_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]


def get_token_service_principal(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Acquire an access token via the client-credentials flow.

    Args:
        tenant_id: Entra tenant GUID.
        client_id: App registration client ID.
        client_secret: App registration client secret.

    Returns:
        Bearer token string.

    Raises:
        RuntimeError: If MSAL fails to return a token.
    """
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=_SCOPE)
    if "access_token" not in result:
        error = result.get("error_description") or result.get("error") or "unknown error"
        raise RuntimeError(f"Service principal token acquisition failed: {error}")
    logger.debug("Service principal token acquired.")
    return result["access_token"]


def get_token_device_code(tenant_id: str, client_id: str) -> str:
    """Acquire an access token via the device-code flow (interactive).

    Prints instructions for the user to authenticate in a browser.

    Args:
        tenant_id: Entra tenant GUID.
        client_id: App registration client ID (must allow public client flows).

    Returns:
        Bearer token string.

    Raises:
        RuntimeError: If the flow cannot be initiated or the token is denied.
    """
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.PublicClientApplication(client_id, authority=authority)

    flow = app.initiate_device_flow(scopes=_SCOPE)
    if "user_code" not in flow:
        error = flow.get("error_description") or flow.get("error") or "unknown error"
        raise RuntimeError(f"Device flow initiation failed: {error}")

    # Print the sign-in instructions (MSAL provides a human-readable message)
    print(flow["message"], flush=True)

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        error = result.get("error_description") or result.get("error") or "unknown error"
        raise RuntimeError(f"Device code token acquisition failed: {error}")

    logger.debug("Device code token acquired.")
    return result["access_token"]
