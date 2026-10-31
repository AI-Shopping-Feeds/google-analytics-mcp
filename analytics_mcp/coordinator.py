# Copyright 2025 Google LLC All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Builds the Google Analytics MCP server.

Tools are registered on the MCP SDK's MCPServer, which derives each tool's
input schema from the function signature. create_server returns the
MCPServer, which server.py runs over stdio.
"""

import functools
import importlib.metadata
import inspect
from typing import Any, Callable, Iterable

import google.auth.exceptions
import httpx
from google.api_core import exceptions as google_exceptions
from mcp import types as mcp_types
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from analytics_mcp.tools.admin.info import (
    get_account_summaries,
    list_google_ads_links,
    get_property_details,
    list_property_annotations,
    create_property_annotation,
)
from analytics_mcp.tools.admin.config import (
    get_property_settings,
    list_audiences,
    list_data_streams,
    list_key_events,
    run_access_report,
    search_change_history,
)
from analytics_mcp.tools.admin.manage import (
    archive_custom_definition,
    create_custom_dimension,
    create_custom_metric,
    create_google_ads_link,
    create_key_event,
    create_measurement_protocol_secret,
    delete_key_event,
    update_data_retention,
)
from analytics_mcp.tools.client import set_allow_write
from analytics_mcp.tools.generic import call_api, list_api_methods
from analytics_mcp.tools.measurement_protocol import (
    send_measurement_protocol_events,
    validate_measurement_protocol_events,
)
from analytics_mcp.tools.reporting.extra import (
    check_compatibility,
    get_dimensions_and_metrics,
    get_property_quotas_snapshot,
    run_pivot_report,
)
from analytics_mcp.tools.reporting.core import (
    run_report,
    _run_report_description,
)
from analytics_mcp.tools.reporting.realtime import (
    run_realtime_report,
    _run_realtime_report_description,
)
from analytics_mcp.tools.reporting.metadata import (
    get_custom_dimensions_and_metrics,
)
from analytics_mcp.tools.reporting.funnel import (
    run_funnel_report,
    _run_funnel_report_description,
)
from analytics_mcp.tools.reporting.conversions import (
    run_conversions_report,
    _run_conversions_report_description,
)

SERVER_NAME = "Google Analytics MCP Server"


def _package_version() -> str:
    try:
        return importlib.metadata.version("analytics-mcp")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0+unknown"


SERVER_VERSION = _package_version()

SERVER_INSTRUCTIONS = """\
Google Analytics 4: Data API reports, Admin API configuration and Measurement Protocol events.
Start with get_account_summaries to find account and property IDs.
Before a report, look up field names with get_dimensions_and_metrics; don't guess them.
Write tools need --allow-write and the analytics.edit OAuth scope.
send_measurement_protocol_events can't be undone: run validate_measurement_protocol_events first.
For anything without a dedicated tool, use call_api (a write tool); list_api_methods shows what it can call.
Limit tools to groups with --tools or GOOGLE_ANALYTICS_MCP_TOOL_GROUPS: reports, properties, measurement_protocol, api."""

# Tool groups that --tools / GOOGLE_ANALYTICS_MCP_TOOL_GROUPS can select.
TOOL_GROUPS = ("reports", "properties", "measurement_protocol", "api")

# Every tool: (function, title, group, description override). A group of None
# means the tool is always registered. A description of None uses the
# function's docstring.
_READ_ONLY_TOOLS: list[
    tuple[Callable[..., Any], str, str | None, str | None]
] = [
    (get_account_summaries, "Get account summaries", None, None),
    (list_google_ads_links, "List Google Ads links", "properties", None),
    (get_property_details, "Get property details", "properties", None),
    (
        list_property_annotations,
        "List property annotations",
        "properties",
        None,
    ),
    (
        get_custom_dimensions_and_metrics,
        "Get custom dimensions and metrics",
        "reports",
        None,
    ),
    (run_report, "Run a report", "reports", _run_report_description()),
    (
        run_realtime_report,
        "Run a realtime report",
        "reports",
        _run_realtime_report_description(),
    ),
    (
        run_funnel_report,
        "Run a funnel report",
        "reports",
        _run_funnel_report_description(),
    ),
    (
        run_conversions_report,
        "Run a conversions report",
        "reports",
        _run_conversions_report_description(),
    ),
    (run_pivot_report, "Run a pivot report", "reports", None),
    (
        check_compatibility,
        "Check dimension and metric compatibility",
        "reports",
        None,
    ),
    (
        get_dimensions_and_metrics,
        "Get dimensions and metrics",
        "reports",
        None,
    ),
    (
        get_property_quotas_snapshot,
        "Get property quotas snapshot",
        "reports",
        None,
    ),
    (list_data_streams, "List data streams", "properties", None),
    (list_key_events, "List key events", "properties", None),
    (list_audiences, "List audiences", "properties", None),
    (search_change_history, "Search change history", "properties", None),
    (get_property_settings, "Get property settings", "properties", None),
    (run_access_report, "Run a data access report", "properties", None),
    (list_api_methods, "List API methods", "api", None),
    (
        validate_measurement_protocol_events,
        "Validate Measurement Protocol events",
        "measurement_protocol",
        None,
    ),
]

# Only registered when the server runs with --allow-write.
_WRITE_TOOLS: list[tuple[Callable[..., Any], str, str | None, str | None]] = [
    (
        create_property_annotation,
        "Create a property annotation",
        "properties",
        None,
    ),
    (create_custom_dimension, "Create a custom dimension", "properties", None),
    (create_custom_metric, "Create a custom metric", "properties", None),
    (
        archive_custom_definition,
        "Archive a custom dimension or metric",
        "properties",
        None,
    ),
    (create_key_event, "Create a key event", "properties", None),
    (delete_key_event, "Delete a key event", "properties", None),
    (update_data_retention, "Update data retention", "properties", None),
    (create_google_ads_link, "Create a Google Ads link", "properties", None),
    (
        create_measurement_protocol_secret,
        "Create a Measurement Protocol secret",
        "measurement_protocol",
        None,
    ),
    (
        send_measurement_protocol_events,
        "Send Measurement Protocol events",
        "measurement_protocol",
        None,
    ),
    (call_api, "Call any Analytics API method", "api", None),
]

# Write tools whose effects can't be undone, marked destructive for MCP hosts.
# Shortening data retention deletes event data older than the new period.
_DESTRUCTIVE_TOOL_NAMES = {
    "archive_custom_definition",
    "delete_key_event",
    "update_data_retention",
    "send_measurement_protocol_events",
    "call_api",
}

# Write tools that have no further effect when repeated with the same
# arguments.
_IDEMPOTENT_TOOL_NAMES = {
    "archive_custom_definition",
    "delete_key_event",
    "update_data_retention",
}

_READ_ONLY_TOOL_NAMES = {t[0].__name__ for t in _READ_ONLY_TOOLS}
_WRITE_TOOL_NAMES = {t[0].__name__ for t in _WRITE_TOOLS}
_TOOL_GROUP_OF = {t[0].__name__: t[2] for t in _READ_ONLY_TOOLS + _WRITE_TOOLS}


def parse_tool_groups(value: str | Iterable[str] | None) -> frozenset[str]:
    """Parses a comma-separated list of tool groups.

    An empty or missing value selects every group.

    Raises:
        ValueError: If a group isn't one of TOOL_GROUPS.
    """
    if value is None:
        return frozenset(TOOL_GROUPS)
    items = value.split(",") if isinstance(value, str) else value
    groups = {item.strip().lower() for item in items if item.strip()}
    if not groups:
        return frozenset(TOOL_GROUPS)
    unknown = sorted(groups - set(TOOL_GROUPS))
    if unknown:
        raise ValueError(
            f"Unknown tool group(s): {', '.join(unknown)}."
            f" Valid groups: {', '.join(TOOL_GROUPS)}."
        )
    return frozenset(groups)


_WRITE_PERMISSION_DENIED_HINT = (
    " Hint: Write tools require the"
    " 'https://www.googleapis.com/auth/analytics.edit' OAuth scope and at least"
    " the Marketer or Editor role on the Google Analytics property. If using"
    " Application Default Credentials (ADC), re-authenticate with: gcloud auth"
    " application-default login --scopes="
    "https://www.googleapis.com/auth/analytics.readonly,"
    "https://www.googleapis.com/auth/analytics.edit,"
    "https://www.googleapis.com/auth/cloud-platform"
    " --client-id-file=YOUR_CLIENT_JSON_FILE"
)

# Errors whose message helps the agent fix the call. MCP SDK 2 hides the text
# of any exception that isn't a ToolError.
_EXPECTED_ERRORS = (
    ValueError,
    RuntimeError,
    PermissionError,
    FileNotFoundError,
    google.auth.exceptions.GoogleAuthError,
    google_exceptions.GoogleAPICallError,
    httpx.HTTPError,
)


def sanitize_mcp_schema_properties(node: dict) -> None:
    """Ensure additionalProperties is a boolean value to satisfy certain MCP clients.

    This addresses issues with clients like Claude Desktop that fail when
    additionalProperties is a schema object instead of a boolean.
    """
    if not isinstance(node, dict):
        return

    if "additionalProperties" in node:
        if not isinstance(node["additionalProperties"], bool):
            node["additionalProperties"] = True

    for child in node.values():
        if isinstance(child, dict):
            sanitize_mcp_schema_properties(child)
        elif isinstance(child, list):
            for element in child:
                if isinstance(element, dict):
                    sanitize_mcp_schema_properties(element)


def _report_errors(fn: Callable[..., Any], is_write: bool):
    """Re-raises expected errors as ToolError so clients see the message."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except _EXPECTED_ERRORS as exc:
            message = f"Failed to execute tool '{fn.__name__}': {exc}"
            if is_write and isinstance(exc, google_exceptions.Forbidden):
                message += _WRITE_PERMISSION_DENIED_HINT
            raise ToolError(message) from exc

    return wrapper


def _annotations(name: str, is_write: bool) -> mcp_types.ToolAnnotations:
    if not is_write:
        return mcp_types.ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            open_world_hint=True,
        )
    return mcp_types.ToolAnnotations(
        read_only_hint=False,
        destructive_hint=name in _DESTRUCTIVE_TOOL_NAMES,
        idempotent_hint=name in _IDEMPOTENT_TOOL_NAMES,
        open_world_hint=True,
    )


class AnalyticsMCPServer(MCPServer):
    """MCPServer that explains why a known but unregistered tool is missing."""

    def __init__(self, allow_write: bool, tool_groups: frozenset[str]):
        super().__init__(
            name=SERVER_NAME,
            version=SERVER_VERSION,
            instructions=SERVER_INSTRUCTIONS,
        )
        self._allow_write = allow_write
        self._tool_groups = tool_groups

    async def call_tool(
        self, name: str, arguments: dict[str, Any], context=None
    ):
        if name in _WRITE_TOOL_NAMES and not self._allow_write:
            raise ToolError(
                f"Tool '{name}' is a write tool and is disabled by default."
                " Start the server with the --allow-write flag to enable write"
                " tools."
            )
        group = _TOOL_GROUP_OF.get(name)
        if group is not None and group not in self._tool_groups:
            raise ToolError(
                f"Tool '{name}' is in the '{group}' tool group, which this"
                " server wasn't started with. Add it to --tools or"
                " GOOGLE_ANALYTICS_MCP_TOOL_GROUPS to enable it."
            )
        return await super().call_tool(name, arguments, context)


def create_server(
    allow_write: bool = False,
    tool_groups: str | Iterable[str] | None = None,
) -> AnalyticsMCPServer:
    """Creates the MCP server.

    Args:
        allow_write: Registers the write tools too.
        tool_groups: Tool groups to register (see TOOL_GROUPS), as an iterable
          or a comma-separated string. None or empty registers every group.
          get_account_summaries is always registered.

    Raises:
        ValueError: If tool_groups names an unknown group.
    """
    groups = parse_tool_groups(tool_groups)
    set_allow_write(allow_write)
    mcp = AnalyticsMCPServer(allow_write, groups)
    tools = [(*t, False) for t in _READ_ONLY_TOOLS]
    if allow_write:
        tools += [(*t, True) for t in _WRITE_TOOLS]
    for fn, title, group, description, is_write in tools:
        if group is not None and group not in groups:
            continue
        mcp.add_tool(
            _report_errors(fn, is_write),
            name=fn.__name__,
            title=title,
            description=description or inspect.cleandoc(fn.__doc__ or ""),
            annotations=_annotations(fn.__name__, is_write),
            # The return annotations (Dict[str, Any], List[...]) would only
            # publish a generic object schema, wrapped in {"result": ...}.
            structured_output=False,
        )
    for tool in mcp._tool_manager.list_tools():
        sanitize_mcp_schema_properties(tool.parameters)
    return mcp
