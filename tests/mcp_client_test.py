# Copyright 2026 Google LLC All Rights Reserved.
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

"""End-to-end tests through an in-memory mcp.Client against the real server."""

import contextlib
import importlib.metadata
import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from analytics_mcp import coordinator, server
from analytics_mcp.tools import client as ga_client
from google.analytics import admin_v1beta
from mcp import Client

# Expected (read, write) tool counts per group, excluding
# get_account_summaries, which every configuration registers.
_GROUP_COUNTS = {
    "reports": (9, 0),
    "properties": (9, 8),
    "measurement_protocol": (1, 2),
    "api": (1, 1),
}


async def _list_tools(**kwargs):
    async with Client(coordinator.create_server(**kwargs)) as client:
        return (await client.list_tools()).tools


class TestServerMetadata(unittest.IsolatedAsyncioTestCase):

    def tearDown(self):
        ga_client.set_allow_write(False)

    async def test_version_name_and_instructions(self):
        async with Client(coordinator.create_server()) as client:
            self.assertEqual(
                client.server_info.version,
                importlib.metadata.version("analytics-mcp"),
            )
            self.assertEqual(
                client.server_info.name, "Google Analytics MCP Server"
            )
            instructions = client.instructions
        self.assertTrue(instructions)
        lines = instructions.splitlines()
        self.assertTrue(4 <= len(lines) <= 8, lines)
        for expected in (
            "get_account_summaries",
            "get_dimensions_and_metrics",
            "--allow-write",
            "analytics.edit",
            "validate_measurement_protocol_events",
            "call_api",
            "--tools",
            "GOOGLE_ANALYTICS_MCP_TOOL_GROUPS",
        ):
            self.assertIn(expected, instructions)

    async def test_every_tool_has_a_title_and_annotations(self):
        tools = await _list_tools(allow_write=True)
        self.assertEqual(len(tools), 32)
        titles = [t.title for t in tools]
        self.assertEqual(len(set(titles)), len(titles), "titles are unique")
        for tool in tools:
            with self.subTest(tool=tool.name):
                self.assertTrue(tool.title)
                self.assertTrue(tool.title[0].isupper())
                self.assertIsNotNone(tool.annotations)
                self.assertIsNotNone(tool.annotations.read_only_hint)
                self.assertIsNotNone(tool.annotations.destructive_hint)
                self.assertTrue(tool.annotations.open_world_hint)
                self.assertEqual(
                    tool.annotations.read_only_hint,
                    tool.name in coordinator._READ_ONLY_TOOL_NAMES,
                )
                self.assertTrue(tool.description)
                self.assertIsNone(tool.output_schema)

    async def test_tool_counts_with_and_without_allow_write(self):
        read = {t.name for t in await _list_tools()}
        everything = {t.name for t in await _list_tools(allow_write=True)}
        self.assertEqual(len(read), 21)
        self.assertEqual(len(everything), 32)
        self.assertEqual(everything - read, coordinator._WRITE_TOOL_NAMES)


class TestToolGroups(unittest.IsolatedAsyncioTestCase):

    def tearDown(self):
        ga_client.set_allow_write(False)

    async def test_each_group_alone(self):
        for group, (read_count, write_count) in _GROUP_COUNTS.items():
            with self.subTest(group=group):
                read = {t.name for t in await _list_tools(tool_groups=group)}
                rw = {
                    t.name
                    for t in await _list_tools(
                        tool_groups=group, allow_write=True
                    )
                }
                self.assertIn("get_account_summaries", read)
                self.assertEqual(len(read), 1 + read_count)
                self.assertEqual(len(rw), 1 + read_count + write_count)
                for name in rw - {"get_account_summaries"}:
                    self.assertEqual(coordinator._TOOL_GROUP_OF[name], group)

    async def test_groups_cover_every_tool(self):
        self.assertEqual(
            sum(r + w for r, w in _GROUP_COUNTS.values()) + 1,
            len(coordinator._TOOL_GROUP_OF),
        )
        self.assertEqual(set(_GROUP_COUNTS), set(coordinator.TOOL_GROUPS))

    async def test_multiple_groups_and_whitespace(self):
        names = {
            t.name for t in await _list_tools(tool_groups=" Reports , api ,")
        }
        self.assertIn("run_report", names)
        self.assertIn("list_api_methods", names)
        self.assertNotIn("list_data_streams", names)
        self.assertNotIn("validate_measurement_protocol_events", names)
        self.assertEqual(len(names), 1 + 9 + 1)

    async def test_empty_selects_every_group(self):
        self.assertEqual(len(await _list_tools(tool_groups="")), 21)
        self.assertEqual(len(await _list_tools(tool_groups=None)), 21)

    def test_unknown_group_fails_in_create_server(self):
        with self.assertRaisesRegex(
            ValueError, "Unknown tool group\\(s\\): bogus. Valid groups:"
        ):
            coordinator.create_server(tool_groups="reports,bogus")

    def test_unknown_group_fails_at_startup(self):
        stderr = io.StringIO()
        with (
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            server.run_server(["--tools", "reports,bogus"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            "--tools: Unknown tool group(s): bogus", stderr.getvalue()
        )

    def test_unknown_group_in_env_var_fails_at_startup(self):
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {server.TOOL_GROUPS_ENV_VAR: "nope"}),
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit),
        ):
            server.parse_args([])
        self.assertIn(
            "GOOGLE_ANALYTICS_MCP_TOOL_GROUPS: Unknown tool group(s): nope",
            stderr.getvalue(),
        )

    def test_flag_overrides_env_var(self):
        with patch.dict(os.environ, {server.TOOL_GROUPS_ENV_VAR: "api"}):
            self.assertEqual(server.parse_args([]).tool_groups, {"api"})
            self.assertEqual(
                server.parse_args(["--tools", "reports"]).tool_groups,
                {"reports"},
            )
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                server.parse_args([]).tool_groups,
                set(coordinator.TOOL_GROUPS),
            )

    async def test_calling_a_tool_from_a_disabled_group_explains(self):
        app = coordinator.create_server(tool_groups="api")
        async with Client(app) as client:
            result = await client.call_tool(
                "run_report",
                {
                    "property_id": 1,
                    "date_ranges": [],
                    "dimensions": [],
                    "metrics": [],
                },
            )
        self.assertTrue(result.is_error)
        self.assertIn("'reports' tool group", result.content[0].text)


class TestToolCalls(unittest.IsolatedAsyncioTestCase):

    def tearDown(self):
        ga_client.set_allow_write(False)

    @patch("analytics_mcp.tools.admin.info.create_admin_api_client")
    async def test_read_tool_returns_data(self, mock_create_client):
        mock_create_client.return_value.list_account_summaries.return_value = [
            admin_v1beta.AccountSummary(
                name="accountSummaries/1",
                account="accounts/1",
                display_name="Shop",
                property_summaries=[
                    admin_v1beta.PropertySummary(
                        property="properties/123", display_name="Shop GA4"
                    )
                ],
            )
        ]
        async with Client(coordinator.create_server()) as client:
            result = await client.call_tool("get_account_summaries", {})
        self.assertFalse(result.is_error)
        self.assertIsNone(result.structured_content)
        data = json.loads(result.content[0].text)
        self.assertEqual(data["account"], "accounts/1")
        self.assertEqual(
            data["property_summaries"][0]["property"], "properties/123"
        )

    async def test_expected_error_reaches_the_client(self):
        async with Client(coordinator.create_server()) as client:
            result = await client.call_tool(
                "get_property_details", {"property_id": "nope"}
            )
        self.assertTrue(result.is_error)
        self.assertIn("Invalid property ID: nope", result.content[0].text)

    async def test_write_tool_without_allow_write_explains(self):
        async with Client(coordinator.create_server()) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            self.assertNotIn("create_key_event", names)
            result = await client.call_tool(
                "create_key_event",
                {"property_id": 1, "event_name": "purchase"},
            )
        self.assertTrue(result.is_error)
        self.assertIn("is a write tool", result.content[0].text)
        self.assertIn("--allow-write", result.content[0].text)


if __name__ == "__main__":
    unittest.main()
