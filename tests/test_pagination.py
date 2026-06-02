"""Tests for the pagination logic in PowerBIClient.paginate_get.

Verifies that:
  1. Multiple pages are fetched and yielded correctly.
  2. The continuationUri from the API response is NEVER followed — only
     continuationToken is used to rebuild the request against the original path.
  3. A single-page (no token) response terminates immediately.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from pbi_ptw_auditor.api_client import PowerBIClient

_PTW_URL = "https://api.powerbi.com/v1.0/myorg/admin/widelySharedArtifacts/publishedToWeb"
_WRONG_URL = "https://api.powerbi.com/v1.0/myorg/admin/widelySharedArtifacts/linksSharedToWholeOrganization"


@respx.mock
def test_pagination_single_page() -> None:
    """No continuationToken → only one request is made."""
    respx.get(_PTW_URL).mock(
        return_value=httpx.Response(
            200,
            json={"value": [{"artifactId": "r1", "displayName": "Report 1"}]},
        )
    )

    client = PowerBIClient("fake-token")
    pages = list(client.paginate_get("admin/widelySharedArtifacts/publishedToWeb"))
    client.close()

    assert len(pages) == 1
    assert pages[0][0]["artifactId"] == "r1"
    assert len(respx.calls) == 1


@respx.mock
def test_pagination_two_pages() -> None:
    """Two pages: first response carries continuationToken, second does not."""
    responses = [
        httpx.Response(
            200,
            json={
                "value": [{"artifactId": "r1", "displayName": "Report 1"}],
                "continuationToken": "tok_abc",
                # continuationUri deliberately points at the sibling endpoint.
                "continuationUri": f"{_WRONG_URL}?continuationToken=tok_abc",
            },
        ),
        httpx.Response(
            200,
            json={"value": [{"artifactId": "r2", "displayName": "Report 2"}]},
        ),
    ]
    respx.get(_PTW_URL).mock(side_effect=responses)

    client = PowerBIClient("fake-token")
    pages = list(client.paginate_get("admin/widelySharedArtifacts/publishedToWeb"))
    client.close()

    assert len(pages) == 2
    all_items = [item for page in pages for item in page]
    assert len(all_items) == 2
    assert all_items[0]["artifactId"] == "r1"
    assert all_items[1]["artifactId"] == "r2"


@respx.mock
def test_pagination_does_not_follow_continuation_uri() -> None:
    """The sibling linksSharedToWholeOrganization endpoint must never be called."""
    responses = [
        httpx.Response(
            200,
            json={
                "value": [{"artifactId": "r1", "displayName": "Report 1"}],
                "continuationToken": "tok_xyz",
                "continuationUri": f"{_WRONG_URL}?continuationToken=tok_xyz",
            },
        ),
        httpx.Response(200, json={"value": []}),
    ]
    respx.get(_PTW_URL).mock(side_effect=responses)

    client = PowerBIClient("fake-token")
    list(client.paginate_get("admin/widelySharedArtifacts/publishedToWeb"))
    client.close()

    for call in respx.calls:
        assert "linksSharedToWholeOrganization" not in str(call.request.url), (
            "paginate_get followed continuationUri instead of staying on the publishedToWeb path"
        )
        assert "publishedToWeb" in str(call.request.url)


@respx.mock
def test_pagination_three_pages() -> None:
    """Three-page scenario: each page's continuationToken drives the next request."""
    responses = [
        httpx.Response(200, json={"value": [{"artifactId": "r1"}], "continuationToken": "t1",
                                  "continuationUri": f"{_WRONG_URL}?continuationToken=t1"}),
        httpx.Response(200, json={"value": [{"artifactId": "r2"}], "continuationToken": "t2",
                                  "continuationUri": f"{_WRONG_URL}?continuationToken=t2"}),
        httpx.Response(200, json={"value": [{"artifactId": "r3"}]}),
    ]
    respx.get(_PTW_URL).mock(side_effect=responses)

    client = PowerBIClient("fake-token")
    pages = list(client.paginate_get("admin/widelySharedArtifacts/publishedToWeb"))
    client.close()

    assert len(pages) == 3
    ids = [item["artifactId"] for page in pages for item in page]
    assert ids == ["r1", "r2", "r3"]
    assert len(respx.calls) == 3


@respx.mock
def test_read_only_guard_blocks_arbitrary_post() -> None:
    """Non-GET requests to non-allowlisted paths must raise PermissionError."""
    client = PowerBIClient("fake-token")
    with pytest.raises(PermissionError, match="(?i)read-only guard"):
        client.post("admin/reports/someAction", json={})
    client.close()


@respx.mock
def test_401_raises_permission_error() -> None:
    """A 401 response must raise PermissionError with an actionable message."""
    respx.get(_PTW_URL).mock(return_value=httpx.Response(401, json={"error": "Unauthorized"}))

    client = PowerBIClient("fake-token")
    with pytest.raises(PermissionError, match="401"):
        client.get("admin/widelySharedArtifacts/publishedToWeb")
    client.close()


@respx.mock
def test_403_raises_permission_error() -> None:
    """A 403 response must raise PermissionError with an actionable message."""
    respx.get(_PTW_URL).mock(return_value=httpx.Response(403, json={"error": "Forbidden"}))

    client = PowerBIClient("fake-token")
    with pytest.raises(PermissionError, match="403"):
        client.get("admin/widelySharedArtifacts/publishedToWeb")
    client.close()
