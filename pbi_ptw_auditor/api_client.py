"""HTTP client for the Power BI Admin REST API.

Responsibilities:
  - Enforce the read-only contract (only GET + one allowlisted scanner POST).
  - Retry on 429 with Retry-After back-off; exponential back-off on transient errors.
  - Translate 401/403 into actionable error messages.
  - Paginate using continuationToken, always rebuilding against the original path
    (never blindly following continuationUri, which can point at a sibling endpoint).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.powerbi.com/v1.0/myorg/"

# The only POST the tool is permitted to make (metadata scanner — read-only).
_ALLOWLISTED_POST_PATHS = {"admin/workspaces/getInfo"}

_MAX_RETRIES = 5
_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 60.0


class PowerBIClient:
    """Thin, read-only wrapper around the Power BI Admin REST API."""

    def __init__(self, token: str, timeout: float = 60.0) -> None:
        self._client = httpx.Client(
            base_url=_BASE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Internal request machinery
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, str]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        upper = method.upper()
        if upper not in ("GET",) and path not in _ALLOWLISTED_POST_PATHS:
            raise PermissionError(
                f"Read-only guard: '{method} {path}' is not allowed. "
                "Only GET requests and the scanner POST are permitted."
            )

        backoff = _INITIAL_BACKOFF
        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.request(method, path, params=params, json=json)

                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", backoff))
                    logger.warning("Rate limited (429). Waiting %.0fs before retry.", retry_after)
                    time.sleep(retry_after)
                    backoff = min(backoff * 2, _MAX_BACKOFF)
                    continue

                if resp.status_code == 401:
                    raise PermissionError(
                        "Authentication failed (401 Unauthorized). "
                        "Ensure your token is valid and targets the Power BI API scope "
                        "(https://analysis.windows.net/powerbi/api/.default)."
                    )

                if resp.status_code == 403:
                    raise PermissionError(
                        "Authorization failed (403 Forbidden). "
                        "The account must be a Power BI Admin, Fabric Admin, or Global Admin. "
                        "For service principals: the SP must belong to a security group enabled "
                        "under 'Service principals can use read-only Power BI admin APIs' in the "
                        "Power BI tenant settings."
                    )

                resp.raise_for_status()
                return resp.json()

            except PermissionError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    logger.warning(
                        "Request %s %s failed (attempt %d/%d): %s. Retrying in %.0fs.",
                        method,
                        path,
                        attempt + 1,
                        _MAX_RETRIES,
                        exc,
                        backoff,
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, _MAX_BACKOFF)

        raise RuntimeError(f"Request failed after {_MAX_RETRIES} attempts: {last_exc}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self, path: str, params: Optional[dict[str, str]] = None
    ) -> dict[str, Any]:
        """Issue a GET request and return the parsed JSON body."""
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        """Issue an allowlisted POST request and return the parsed JSON body."""
        return self._request("POST", path, json=json)

    def paginate_get(
        self, path: str, items_key: str = "value"
    ) -> Generator[list[dict[str, Any]], None, None]:
        """Yield pages from a paginated GET endpoint.

        Pagination uses the ``continuationToken`` field only. The
        ``continuationUri`` returned by the API is intentionally ignored:
        it can reference a sibling endpoint (e.g. linksSharedToWholeOrganization)
        instead of the original path, which would silently mix data from two
        different artifact categories.
        """
        params: Optional[dict[str, str]] = None

        while True:
            data = self.get(path, params=params)
            items: list[dict[str, Any]] = data.get(items_key, [])
            yield items

            token: Optional[str] = data.get("continuationToken")
            if not token:
                break

            # Rebuild the next request against *this* path, not continuationUri.
            params = {"continuationToken": token}
            logger.debug("Fetching next page for '%s' with continuationToken.", path)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PowerBIClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
