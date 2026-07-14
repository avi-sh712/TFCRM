"""Secure LangChain adapter for TalentForge's read-only Postgres MCP server.

The module intentionally keeps the MCP boundary separate from the application's
SQLAlchemy connection. The remote MCP server must use a database credential that
is restricted to ``app_readonly`` (or an equivalently constrained role); this
adapter also fails closed when discovering tool names that look mutating.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool
    from langchain_mcp_adapters.client import MultiServerMCPClient


logger = logging.getLogger("talentforge.mcp.postgres")

POSTGRES_MCP_SERVER_NAME: Final = "postgres"
POSTGRES_MCP_URL_ENV: Final = "POSTGRES_MCP_URL"
POSTGRES_MCP_TRANSPORT_ENV: Final = "POSTGRES_MCP_TRANSPORT"
POSTGRES_MCP_AUTH_TOKEN_ENV: Final = "POSTGRES_MCP_AUTH_TOKEN"
POSTGRES_MCP_HEADERS_ENV: Final = "POSTGRES_MCP_HEADERS_JSON"
POSTGRES_MCP_ALLOWED_TOOLS_ENV: Final = "POSTGRES_MCP_ALLOWED_TOOLS"
POSTGRES_MCP_ALLOW_ANONYMOUS_ENV: Final = "POSTGRES_MCP_ALLOW_ANONYMOUS"
POSTGRES_MCP_REQUEST_TIMEOUT_ENV: Final = "POSTGRES_MCP_REQUEST_TIMEOUT_SECONDS"
POSTGRES_MCP_SSE_READ_TIMEOUT_ENV: Final = "POSTGRES_MCP_SSE_READ_TIMEOUT_SECONDS"

DEFAULT_REQUEST_TIMEOUT_SECONDS: Final = 10.0
DEFAULT_SSE_READ_TIMEOUT_SECONDS: Final = 300.0
SUPPORTED_TRANSPORTS: Final = frozenset({"http", "streamable_http", "sse"})
SAFE_TOOL_PREFIXES: Final = (
    "count_",
    "describe_",
    "explain_",
    "find_",
    "get_",
    "health_",
    "list_",
    "metrics_",
    "read_",
    "search_",
    "show_",
)
MUTATING_TOOL_TOKENS: Final = frozenset(
    {
        "alter",
        "create",
        "delete",
        "drop",
        "execute",
        "grant",
        "insert",
        "migrate",
        "revoke",
        "truncate",
        "update",
        "upsert",
        "write",
    }
)
SENSITIVE_KEY_PATTERN: Final = re.compile(
    r"(?:api[_-]?key|authorization|credential|password|secret|token)",
    re.IGNORECASE,
)
PROHIBITED_HEADER_NAMES: Final = frozenset(
    {"connection", "content-length", "host", "transfer-encoding"}
)


class PostgresMCPConfigurationError(RuntimeError):
    """Raised when the local Postgres MCP configuration is unsafe or incomplete."""


class PostgresMCPConnectionError(RuntimeError):
    """Raised without upstream details when a Postgres MCP session cannot be used."""


class PostgresMCPDependencyError(RuntimeError):
    """Raised when the optional LangChain MCP adapter dependency is unavailable."""


@dataclass(frozen=True, slots=True)
class PostgresMCPSettings:
    """Validated runtime configuration for the remote, read-only MCP endpoint."""

    url: str = field(repr=False)
    transport: Literal["http", "streamable_http", "sse"]
    headers: Mapping[str, str] = field(repr=False)
    allowed_tools: frozenset[str]
    request_timeout_seconds: float
    sse_read_timeout_seconds: float

    @property
    def safe_endpoint(self) -> str:
        """Return a log-safe endpoint identifier with credentials and query removed."""
        parsed = urlsplit(self.url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    @classmethod
    def from_environment(cls) -> PostgresMCPSettings:
        """Read, validate, and normalize the MCP configuration on each invocation."""
        url = _required_environment_value(POSTGRES_MCP_URL_ENV)
        _validate_mcp_url(url)

        transport = os.getenv(POSTGRES_MCP_TRANSPORT_ENV, "http").strip().lower()
        if transport == "streamable-http":
            transport = "streamable_http"
        if transport not in SUPPORTED_TRANSPORTS:
            raise PostgresMCPConfigurationError(
                f"{POSTGRES_MCP_TRANSPORT_ENV} must be one of: "
                f"{', '.join(sorted(SUPPORTED_TRANSPORTS))}."
            )

        headers = _load_headers_from_environment()
        token = os.getenv(POSTGRES_MCP_AUTH_TOKEN_ENV, "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif "Authorization" not in headers and not _environment_is_true(
            POSTGRES_MCP_ALLOW_ANONYMOUS_ENV
        ):
            raise PostgresMCPConfigurationError(
                f"{POSTGRES_MCP_AUTH_TOKEN_ENV} is required unless "
                f"{POSTGRES_MCP_ALLOW_ANONYMOUS_ENV}=true."
            )

        return cls(
            url=url,
            transport=transport,  # type: ignore[arg-type]
            headers=headers,
            allowed_tools=_load_allowed_tools(),
            request_timeout_seconds=_load_positive_float(
                POSTGRES_MCP_REQUEST_TIMEOUT_ENV,
                DEFAULT_REQUEST_TIMEOUT_SECONDS,
            ),
            sse_read_timeout_seconds=_load_positive_float(
                POSTGRES_MCP_SSE_READ_TIMEOUT_ENV,
                DEFAULT_SSE_READ_TIMEOUT_SECONDS,
            ),
        )

    def connection_configuration(self) -> dict[str, Any]:
        """Build the adapter connection mapping without ever logging its contents."""
        return {
            "transport": self.transport,
            "url": self.url,
            "headers": dict(self.headers),
            "timeout": self.request_timeout_seconds,
            "sse_read_timeout": self.sse_read_timeout_seconds,
        }


class PostgresMCPAdapter:
    """Loads the approved Postgres MCP tools as LangChain/LangGraph tools."""

    def __init__(self, settings: PostgresMCPSettings | None = None) -> None:
        self._settings = settings

    @property
    def settings(self) -> PostgresMCPSettings:
        """Resolve environment configuration lazily so rotated credentials take effect."""
        return self._settings or PostgresMCPSettings.from_environment()

    def _build_client(self) -> MultiServerMCPClient:
        """Create the official adapter client for one named remote server."""
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError:
            raise PostgresMCPDependencyError(
                "langchain-mcp-adapters is required for Postgres MCP integration."
            ) from None

        return MultiServerMCPClient(
            {POSTGRES_MCP_SERVER_NAME: self.settings.connection_configuration()},
            handle_tool_errors=True,
        )

    async def get_tools(self) -> list[BaseTool]:
        """
        Return approved tools using a fresh MCP session per individual tool call.

        This is suited to short-lived graph invocations and automatically recovers
        from a dead remote session on the next tool execution.
        """
        client = self._build_client()
        try:
            tools = await client.get_tools(server_name=POSTGRES_MCP_SERVER_NAME)
            return self._select_readonly_tools(tools)
        except PostgresMCPConfigurationError:
            raise
        except Exception:
            self._log_connection_failure("tool_discovery")
            raise PostgresMCPConnectionError(
                "Postgres MCP tool discovery failed; no infrastructure details were logged."
            ) from None

    @asynccontextmanager
    async def session(self) -> AsyncIterator[list[BaseTool]]:
        """
        Yield tools bound to one initialized MCP session.

        Keep this context open for the full LangGraph invocation. The adapter closes
        the remote session even if a graph node raises an exception.
        """
        try:
            from langchain_mcp_adapters.tools import load_mcp_tools
        except ImportError:
            raise PostgresMCPDependencyError(
                "langchain-mcp-adapters is required for Postgres MCP integration."
            ) from None

        client = self._build_client()
        try:
            async with client.session(POSTGRES_MCP_SERVER_NAME) as mcp_session:
                tools = await load_mcp_tools(mcp_session, handle_tool_errors=True)
                yield self._select_readonly_tools(tools)
        except PostgresMCPConfigurationError:
            raise
        except Exception:
            self._log_connection_failure("session")
            raise PostgresMCPConnectionError(
                "Postgres MCP session failed; no infrastructure details were logged."
            ) from None

    def _select_readonly_tools(self, tools: list[BaseTool]) -> list[BaseTool]:
        selected: list[BaseTool] = []
        rejected: list[str] = []

        for tool in tools:
            tool_name = tool.name.strip()
            if _is_approved_readonly_tool(tool_name, self.settings.allowed_tools):
                selected.append(tool)
            else:
                rejected.append(tool_name)

        if rejected:
            logger.warning(
                "postgres_mcp_tools_rejected server=%s rejected=%s",
                POSTGRES_MCP_SERVER_NAME,
                sorted(rejected),
            )
        if not selected:
            raise PostgresMCPConfigurationError(
                "Postgres MCP exposed no approved read-only tools. "
                f"Configure {POSTGRES_MCP_ALLOWED_TOOLS_ENV} with exact approved names."
            )
        return selected

    def _log_connection_failure(self, operation: str) -> None:
        """Log only non-sensitive context; never attach the upstream exception trace."""
        settings = self.settings
        logger.error(
            "postgres_mcp_%s_failed server=%s transport=%s endpoint=%s",
            operation,
            POSTGRES_MCP_SERVER_NAME,
            settings.transport,
            settings.safe_endpoint,
        )


def get_postgres_mcp_adapter() -> PostgresMCPAdapter:
    """Create an adapter that resolves environment configuration at use time."""
    return PostgresMCPAdapter()


async def get_postgres_tracking_tools() -> list[BaseTool]:
    """Return a standard LangChain tool list suitable for a LangGraph ``ToolNode``."""
    return await get_postgres_mcp_adapter().get_tools()


@asynccontextmanager
async def postgres_mcp_tool_session() -> AsyncIterator[list[BaseTool]]:
    """Convenience context manager for a persistent, initialized LangGraph tool set."""
    async with get_postgres_mcp_adapter().session() as tools:
        yield tools


def _required_environment_value(variable_name: str) -> str:
    value = os.getenv(variable_name, "").strip()
    if not value:
        raise PostgresMCPConfigurationError(f"{variable_name} must be configured.")
    return value


def _environment_is_true(variable_name: str) -> bool:
    return os.getenv(variable_name, "").strip().lower() in {"1", "true", "yes"}


def _validate_mcp_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise PostgresMCPConfigurationError(
            f"{POSTGRES_MCP_URL_ENV} must be an absolute HTTP(S) URL."
        )
    if parsed.username or parsed.password:
        raise PostgresMCPConfigurationError(
            f"{POSTGRES_MCP_URL_ENV} must not embed credentials; use HTTP headers."
        )
    if parsed.scheme == "http" and parsed.hostname not in {
        "127.0.0.1",
        "::1",
        "localhost",
    }:
        raise PostgresMCPConfigurationError(
            f"{POSTGRES_MCP_URL_ENV} must use HTTPS outside a local development host."
        )
    if any(SENSITIVE_KEY_PATTERN.search(key) for key in _query_parameter_names(url)):
        raise PostgresMCPConfigurationError(
            f"{POSTGRES_MCP_URL_ENV} must not contain secrets in its query string."
        )


def _query_parameter_names(url: str) -> list[str]:
    query = urlsplit(url).query
    return [part.partition("=")[0] for part in query.split("&") if part]


def _load_headers_from_environment() -> dict[str, str]:
    raw_headers = os.getenv(POSTGRES_MCP_HEADERS_ENV, "").strip()
    if not raw_headers:
        return {}
    try:
        decoded = json.loads(raw_headers)
    except json.JSONDecodeError:
        raise PostgresMCPConfigurationError(
            f"{POSTGRES_MCP_HEADERS_ENV} must contain a JSON object."
        ) from None

    if not isinstance(decoded, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in decoded.items()
    ):
        raise PostgresMCPConfigurationError(
            f"{POSTGRES_MCP_HEADERS_ENV} must contain string header names and values."
        )

    headers: dict[str, str] = {}
    for name, value in decoded.items():
        normalized_name = name.strip()
        if not normalized_name or normalized_name.lower() in PROHIBITED_HEADER_NAMES:
            raise PostgresMCPConfigurationError(
                f"{POSTGRES_MCP_HEADERS_ENV} contains a prohibited HTTP header."
            )
        if "\r" in value or "\n" in value:
            raise PostgresMCPConfigurationError(
                f"{POSTGRES_MCP_HEADERS_ENV} contains an invalid HTTP header value."
            )
        headers[normalized_name] = value
    return headers


def _load_allowed_tools() -> frozenset[str]:
    raw_value = os.getenv(POSTGRES_MCP_ALLOWED_TOOLS_ENV, "")
    return frozenset(
        name.strip() for name in raw_value.split(",") if name.strip()
    )


def _load_positive_float(variable_name: str, default: float) -> float:
    raw_value = os.getenv(variable_name, "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        raise PostgresMCPConfigurationError(
            f"{variable_name} must be a positive number."
        ) from None
    if value <= 0:
        raise PostgresMCPConfigurationError(
            f"{variable_name} must be a positive number."
        )
    return value


def _is_approved_readonly_tool(
    tool_name: str,
    allowed_tools: frozenset[str],
) -> bool:
    normalized_name = tool_name.lower()
    if any(token in normalized_name for token in MUTATING_TOOL_TOKENS):
        return False
    if allowed_tools:
        return tool_name in allowed_tools
    return normalized_name.startswith(SAFE_TOOL_PREFIXES)
