# Copyright 2026 Google LLC All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the reporting, admin, Measurement Protocol and generic tools added in this fork."""

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from analytics_mcp import coordinator
from mcp import Client
from analytics_mcp.tools import generic, measurement_protocol as mp
from analytics_mcp.tools.admin import config, manage
from analytics_mcp.tools.reporting import extra
from google.analytics import admin_v1beta, data_v1beta


class TestReportingTools(unittest.IsolatedAsyncioTestCase):

    @patch("analytics_mcp.tools.reporting.extra.create_data_api_client")
    async def test_run_pivot_report(self, mock_client):
        mock_client.return_value.run_pivot_report.return_value = (
            data_v1beta.RunPivotReportResponse()
        )

        await extra.run_pivot_report(
            property_id=123,
            date_ranges=[{"start_date": "7daysAgo", "end_date": "yesterday"}],
            dimensions=["country", "deviceCategory"],
            metrics=["sessions"],
            pivots=[{"field_names": ["country"], "limit": 5}],
        )

        request = mock_client.return_value.run_pivot_report.call_args.args[0]
        self.assertEqual(request.property, "properties/123")
        self.assertEqual(list(request.pivots[0].field_names), ["country"])
        self.assertEqual(request.pivots[0].limit, 5)

    @patch("analytics_mcp.tools.reporting.extra.create_data_api_client")
    async def test_get_dimensions_and_metrics_search(self, mock_client):
        mock_client.return_value.get_metadata.return_value = (
            data_v1beta.Metadata(
                dimensions=[
                    {"api_name": "itemName", "ui_name": "Item name"},
                    {"api_name": "country", "ui_name": "Country"},
                ],
                metrics=[
                    {"api_name": "itemRevenue", "ui_name": "Item revenue"},
                    {"api_name": "sessions", "ui_name": "Sessions"},
                ],
            )
        )

        result = await extra.get_dimensions_and_metrics(123, search="item")

        self.assertEqual(
            [d["api_name"] for d in result["dimensions"]], ["itemName"]
        )
        self.assertEqual(
            [m["api_name"] for m in result["metrics"]], ["itemRevenue"]
        )


class TestAdminTools(unittest.IsolatedAsyncioTestCase):

    @patch("analytics_mcp.tools.admin.manage.create_admin_api_client")
    async def test_create_custom_dimension(self, mock_client):
        mock_client.return_value.create_custom_dimension.return_value = (
            admin_v1beta.CustomDimension(name="properties/1/customDimensions/2")
        )

        result = await manage.create_custom_dimension(
            property_id="properties/1",
            parameter_name="plan_type",
            display_name="Plan type",
            scope="user",
        )

        request = (
            mock_client.return_value.create_custom_dimension.call_args.args[0]
        )
        self.assertEqual(request.parent, "properties/1")
        self.assertEqual(request.custom_dimension.scope.name, "USER")
        self.assertEqual(result["name"], "properties/1/customDimensions/2")

    async def test_create_custom_dimension_rejects_bad_scope(self):
        with self.assertRaises(ValueError):
            await manage.create_custom_dimension(1, "a", "A", scope="SESSION")

    @patch("analytics_mcp.tools.admin.manage.create_admin_api_client")
    async def test_archive_custom_definition_routes_by_name(self, mock_client):
        await manage.archive_custom_definition("properties/1/customMetrics/9")
        mock_client.return_value.archive_custom_metric.assert_called_once_with(
            name="properties/1/customMetrics/9"
        )
        with self.assertRaises(ValueError):
            await manage.archive_custom_definition("properties/1/keyEvents/9")

    @patch("analytics_mcp.tools.admin.manage.create_admin_api_client")
    async def test_create_key_event_with_default_value(self, mock_client):
        mock_client.return_value.create_key_event.return_value = (
            admin_v1beta.KeyEvent()
        )

        await manage.create_key_event(
            1, "generate_lead", default_value=25.0, currency_code="GBP"
        )

        key_event = mock_client.return_value.create_key_event.call_args.args[
            0
        ].key_event
        self.assertEqual(key_event.counting_method.name, "ONCE_PER_EVENT")
        self.assertEqual(key_event.default_value.currency_code, "GBP")

    async def test_create_key_event_value_needs_currency(self):
        with self.assertRaises(ValueError):
            await manage.create_key_event(1, "lead", default_value=5.0)

    @patch("analytics_mcp.tools.admin.manage.create_admin_api_client")
    async def test_update_data_retention_mask(self, mock_client):
        mock_client.return_value.update_data_retention_settings.return_value = (
            admin_v1beta.DataRetentionSettings()
        )

        await manage.update_data_retention(
            1, "fourteen_months", reset_user_data_on_new_activity=True
        )

        request = mock_client.return_value.update_data_retention_settings.call_args.args[
            0
        ]
        self.assertEqual(
            list(request.update_mask.paths),
            ["event_data_retention", "reset_user_data_on_new_activity"],
        )
        self.assertEqual(
            request.data_retention_settings.name,
            "properties/1/dataRetentionSettings",
        )

    @patch("analytics_mcp.tools.admin.manage.create_admin_api_client")
    async def test_create_google_ads_link_strips_dashes(self, mock_client):
        mock_client.return_value.create_google_ads_link.return_value = (
            admin_v1beta.GoogleAdsLink()
        )

        await manage.create_google_ads_link(1, "123-456-7890")

        link = mock_client.return_value.create_google_ads_link.call_args.args[
            0
        ].google_ads_link
        self.assertEqual(link.customer_id, "1234567890")

    @patch("analytics_mcp.tools.admin.config.create_admin_alpha_api_client")
    @patch("analytics_mcp.tools.admin.config.create_admin_api_client")
    async def test_get_property_settings_reports_errors(self, beta, alpha):
        from google.api_core import exceptions

        beta.return_value.get_data_retention_settings.return_value = (
            admin_v1beta.DataRetentionSettings(
                event_data_retention="TWO_MONTHS"
            )
        )
        alpha.return_value.get_attribution_settings.side_effect = (
            exceptions.Forbidden("no access")
        )
        alpha.return_value.get_google_signals_settings.return_value = (
            MagicMock()
        )

        with patch(
            "analytics_mcp.tools.admin.config.proto_to_dict",
            side_effect=lambda m: (
                {"event_data_retention": "TWO_MONTHS"}
                if isinstance(m, admin_v1beta.DataRetentionSettings)
                else {}
            ),
        ):
            result = await config.get_property_settings(1)

        self.assertEqual(
            result["data_retention"]["event_data_retention"], "TWO_MONTHS"
        )
        self.assertIn("attribution", result["errors"])

    @patch("analytics_mcp.tools.admin.config.create_admin_api_client")
    async def test_search_change_history(self, mock_client):
        mock_client.return_value.search_change_history_events.return_value = [
            admin_v1beta.ChangeHistoryEvent(id="1"),
            admin_v1beta.ChangeHistoryEvent(id="2"),
        ]

        result = await config.search_change_history(
            "999", property_id=1, actions=["CREATED"], page_size=1
        )

        request = mock_client.return_value.search_change_history_events.call_args.args[
            0
        ]
        self.assertEqual(request.account, "accounts/999")
        self.assertEqual(request.property, "properties/1")
        self.assertEqual(len(result), 1)


class TestMeasurementProtocol(unittest.IsolatedAsyncioTestCase):

    EVENTS = [{"name": "purchase", "params": {"value": 10, "currency": "GBP"}}]

    def _response(self, json_body):
        response = MagicMock()
        response.json.return_value = json_body
        response.status_code = 204
        return response

    async def test_validate_web_stream(self):
        with patch.object(
            mp, "_post", AsyncMock(return_value=self._response({}))
        ) as post:
            result = await mp.validate_measurement_protocol_events(
                self.EVENTS,
                measurement_id="G-ABC",
                client_id="123.456",
                api_secret="s",
                user_properties={"tier": "gold"},
            )

        url, params, body = post.call_args.args
        self.assertEqual(
            url, "https://www.google-analytics.com/debug/mp/collect"
        )
        self.assertEqual(params, {"measurement_id": "G-ABC", "api_secret": "s"})
        self.assertEqual(body["client_id"], "123.456")
        self.assertEqual(body["user_properties"], {"tier": {"value": "gold"}})
        self.assertTrue(result["valid"])

    async def test_secret_from_environment_and_eu_region(self):
        with patch.dict(os.environ, {mp.API_SECRET_ENV_VAR: "env-secret"}):
            with patch.object(
                mp, "_post", AsyncMock(return_value=self._response({}))
            ) as post:
                await mp.validate_measurement_protocol_events(
                    self.EVENTS,
                    firebase_app_id="1:2:ios:3",
                    app_instance_id="abc",
                    region="eu",
                )

        url, params, body = post.call_args.args
        self.assertTrue(url.startswith("https://region1.google-analytics.com"))
        self.assertEqual(params["api_secret"], "env-secret")
        self.assertEqual(body["app_instance_id"], "abc")

    async def test_rejects_mixed_identifiers(self):
        with self.assertRaises(ValueError):
            await mp.validate_measurement_protocol_events(
                self.EVENTS,
                measurement_id="G-ABC",
                client_id="1",
                app_instance_id="x",
                api_secret="s",
            )

    async def test_send_stops_on_validation_errors(self):
        invalid = self._response(
            {
                "validationMessages": [
                    {"fieldPath": "events", "description": "bad"}
                ]
            }
        )
        with patch.object(mp, "_post", AsyncMock(return_value=invalid)) as post:
            result = await mp.send_measurement_protocol_events(
                self.EVENTS, measurement_id="G-A", client_id="1", api_secret="s"
            )

        self.assertFalse(result["sent"])
        self.assertEqual(post.call_count, 1)  # only the debug call

    async def test_send_validates_then_sends(self):
        with patch.object(
            mp, "_post", AsyncMock(return_value=self._response({}))
        ) as post:
            result = await mp.send_measurement_protocol_events(
                self.EVENTS, measurement_id="G-A", client_id="1", api_secret="s"
            )

        urls = [c.args[0] for c in post.call_args_list]
        self.assertEqual(
            urls,
            [
                "https://www.google-analytics.com/debug/mp/collect",
                "https://www.google-analytics.com/mp/collect",
            ],
        )
        self.assertTrue(result["sent"])


class TestGenericTools(unittest.IsolatedAsyncioTestCase):

    async def test_list_api_methods(self):
        result = await generic.list_api_methods()
        self.assertIn("create_audience", result["admin_v1alpha"])
        self.assertIn("run_pivot_report", result["data_v1beta"])

        detail = await generic.list_api_methods(
            "admin", "v1beta", "update_custom_dimension"
        )
        self.assertIn("update_mask", detail["request_fields"])

    async def test_call_api_unknown_method(self):
        with self.assertRaises(ValueError):
            await generic.call_api("admin", "v1beta", "drop_everything", {})
        with self.assertRaises(ValueError):
            await generic.call_api("ads", "v1beta", "get_property", {})

    async def test_call_api_runs_method_and_formats(self):
        fake = MagicMock()
        fake.get_property.return_value = admin_v1beta.Property(
            name="properties/1", display_name="Shop"
        )
        with patch.dict(
            generic._CLIENTS,
            {
                ("admin", "v1beta"): (
                    admin_v1beta.AnalyticsAdminServiceClient,
                    lambda: fake,
                )
            },
        ):
            result = await generic.call_api(
                "admin", "v1beta", "get_property", {"name": "properties/1"}
            )

        self.assertEqual(result["display_name"], "Shop")
        fake.get_property.assert_called_once_with(
            request={"name": "properties/1"}
        )


class TestToolRegistration(unittest.IsolatedAsyncioTestCase):

    async def _tools(self, allow_write):
        server = coordinator.create_server(allow_write=allow_write)
        return {t.name: t for t in await server.list_tools()}

    async def test_tool_counts_and_annotations(self):
        read = await self._tools(False)
        everything = await self._tools(True)
        write = {n: t for n, t in everything.items() if n not in read}
        self.assertEqual(len(read), 21)
        self.assertEqual(len(write), 11)
        self.assertEqual(set(write), coordinator._WRITE_TOOL_NAMES)
        self.assertFalse(set(read) & set(write))
        self.assertTrue(
            read[
                "validate_measurement_protocol_events"
            ].annotations.read_only_hint
        )
        self.assertTrue(write["call_api"].annotations.destructive_hint)
        self.assertFalse(write["create_key_event"].annotations.destructive_hint)

    async def test_expected_errors_reach_the_client(self):
        server = coordinator.create_server(allow_write=False)
        async with Client(server) as client:
            result = await client.call_tool(
                "get_property_details", {"property_id": "nope"}
            )
        self.assertTrue(result.is_error)
        self.assertIn("Invalid property ID", result.content[0].text)

    @patch("analytics_mcp.tools.client.google.auth.default")
    async def test_missing_credentials_message_reaches_the_client(
        self, mock_default
    ):
        import google.auth.exceptions

        mock_default.side_effect = (
            google.auth.exceptions.DefaultCredentialsError(
                "Your default credentials were not found."
            )
        )
        server = coordinator.create_server(allow_write=False)
        async with Client(server) as client:
            result = await client.call_tool("get_account_summaries", {})
        self.assertTrue(result.is_error)
        self.assertIn(
            "default credentials were not found", result.content[0].text
        )


if __name__ == "__main__":
    unittest.main()
