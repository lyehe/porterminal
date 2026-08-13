"""Contract tests for the manual MCP driver URL boundary."""

import pytest

from scripts.agent_drive import parse_args, validate_mcp_url

ACCESS_CODE = "AgentDriveCode_123456"


@pytest.mark.parametrize(
    "url",
    [
        f"http://127.0.0.1:8077/{ACCESS_CODE}/mcp",
        f"https://example.trycloudflare.com/{ACCESS_CODE}/mcp",
        f"https://proxy.example.test/porterminal/{ACCESS_CODE}/mcp",
    ],
)
def test_validate_mcp_url_accepts_complete_protected_urls(url):
    assert validate_mcp_url(url) == url
    assert parse_args([url]).url == url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8077/mcp",
        "javascript:alert(1)",
        f"https://user:password@example.test/{ACCESS_CODE}/mcp",
        f"https://example.test/{ACCESS_CODE}/mcp?redirect=evil",
        f"https://example.test/{ACCESS_CODE}/mcp#fragment",
        "https://example.test/short/mcp",
        f"https://example.test/{ACCESS_CODE}/mcp/",
        f"https://example.test/{ACCESS_CODE}\\mcp",
    ],
)
def test_validate_mcp_url_rejects_bare_or_malformed_urls(url):
    with pytest.raises(ValueError, match="MCP URL"):
        validate_mcp_url(url)


def test_agent_driver_requires_the_url_argument():
    with pytest.raises(SystemExit) as error:
        parse_args([])

    assert error.value.code == 2
