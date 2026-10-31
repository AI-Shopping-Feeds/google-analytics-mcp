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
input schema from the function signature. create_server returns its low-level
Server, which server.py runs over stdio.
"""

import functools
import inspect
from typing import Any, Callable

import google.auth.exceptions
import httpx
from google.api_core import exceptions as google_exceptions
from mcp import types as mcp_types
from mcp.server.lowlevel import Server
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

# (function, description override). None uses the function's docstring.
_READ_ONLY_TOOLS: list[tuple[Callable[..., Any], str | None]] = [
    (get_account_summaries, None),
    (list_google_ads_links, None),
    (get_property_details, None),
    (list_property_annotations, None),
    (get_custom_dimensions_and_metrics, None),
    (run_report, _run_report_description()),
    (run_realtime_report, _run_realtime_report_description()),
    (run_funnel_report, _run_funnel_report_description()),
    (run_conversions_report, _run_conversions_report_description()),
    (run_pivot_report, None),
    (check_compatibility, None),
    (get_dimensions_and_metrics, None),
    (get_property_quotas_snapshot, None),
    (list_data_streams, None),
    (list_key_events, None),
    (list_audiences, None),
    (search_change_history, None),
    (get_property_settings, None),
    (run_access_report, None),
    (list_api_methods, None),
    (validate_measurement_protocol_events, None),
]

# Only registered when the server runs with --allow-write.
_WRITE_TOOLS: list[tuple[Callable[..., Any], str | None]] = [
    (create_property_annotation, None),
    (create_custom_dimension, None),
    (create_custom_metric, None),
    (archive_custom_definition, None),
    (create_key_event, None),
    (delete_key_event, None),
    (update_data_retention, None),
    (create_google_ads_link, None),
    (create_measurement_protocol_secret, None),
    (send_measurement_protocol_events, None),
    (call_api, None),
]

# Write tools whose effects can't be undone, marked destructive for MCP hosts.
_DESTRUCTIVE_TOOL_NAMES = {
    "archive_custom_definition",
    "delete_key_event",
    "send_measurement_protocol_events",
    "call_api",
}

_READ_ONLY_TOOL_NAMES = {fn.__name__ for fn, _ in _READ_ONLY_TOOLS}
_WRITE_TOOL_NAMES = {fn.__name__ for fn, _ in _WRITE_TOOLS}

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
        idempotent_hint=False,
        open_world_hint=True,
    )


class AnalyticsMCPServer(MCPServer):
    """MCPServer that explains how to enable write tools when one is called."""

    def __init__(self, allow_write: bool):
        super().__init__(name="Google Analytics MCP Server")
        self._allow_write = allow_write

    async def call_tool(
        self, name: str, arguments: dict[str, Any], context=None
    ):
        if name in _WRITE_TOOL_NAMES and not self._allow_write:
            raise ToolError(
                f"Tool '{name}' is a write tool and is disabled by default."
                " Start the server with the --allow-write flag to enable write"
                " tools."
            )
        return await super().call_tool(name, arguments, context)


def create_server(allow_write: bool = False) -> Server:
    """Creates the MCP server and returns its low-level Server."""
    set_allow_write(allow_write)
    mcp = AnalyticsMCPServer(allow_write)
    tools = [(fn, desc, False) for fn, desc in _READ_ONLY_TOOLS]
    if allow_write:
        tools += [(fn, desc, True) for fn, desc in _WRITE_TOOLS]
    for fn, description, is_write in tools:
        mcp.add_tool(
            _report_errors(fn, is_write),
            name=fn.__name__,
            description=description or inspect.cleandoc(fn.__doc__ or ""),
            annotations=_annotations(fn.__name__, is_write),
            structured_output=False,
        )
    for tool in mcp._tool_manager.list_tools():
        sanitize_mcp_schema_properties(tool.parameters)
    return mcp._lowlevel_server
