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

"""Read-only tools for a property's configuration."""

import asyncio
from typing import Any, Dict, List

from analytics_mcp.tools.client import (
    create_admin_alpha_api_client,
    create_admin_api_client,
)
from analytics_mcp.tools.utils import construct_property_rn, proto_to_dict
from google.analytics import admin_v1alpha, admin_v1beta
from google.api_core import exceptions as google_exceptions


async def list_data_streams(property_id: int | str) -> List[Dict[str, Any]]:
    """Lists a property's data streams (web, iOS and Android).

    Web streams include the measurement ID (G-...) used by gtag.js, Google
    Tag Manager and the Measurement Protocol.

    Args:
        property_id: The Google Analytics property ID.
    """
    request = admin_v1beta.ListDataStreamsRequest(
        parent=construct_property_rn(property_id)
    )
    return await asyncio.to_thread(
        lambda: [
            proto_to_dict(s)
            for s in create_admin_api_client().list_data_streams(request)
        ]
    )


async def list_key_events(property_id: int | str) -> List[Dict[str, Any]]:
    """Lists the property's key events (formerly called conversions).

    Args:
        property_id: The Google Analytics property ID.
    """
    request = admin_v1beta.ListKeyEventsRequest(
        parent=construct_property_rn(property_id)
    )
    return await asyncio.to_thread(
        lambda: [
            proto_to_dict(e)
            for e in create_admin_api_client().list_key_events(request)
        ]
    )


async def list_audiences(property_id: int | str) -> List[Dict[str, Any]]:
    """Lists the property's audiences with their membership rules. Uses Admin API v1alpha.

    Args:
        property_id: The Google Analytics property ID.
    """
    request = admin_v1alpha.ListAudiencesRequest(
        parent=construct_property_rn(property_id)
    )
    return await asyncio.to_thread(
        lambda: [
            proto_to_dict(a)
            for a in create_admin_alpha_api_client().list_audiences(request)
        ]
    )


async def search_change_history(
    account_id: int | str,
    property_id: int | str = None,
    earliest_change_time: str = None,
    latest_change_time: str = None,
    resource_types: List[str] = None,
    actions: List[str] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """Searches the account's change history: who changed what, and when.

    Args:
        account_id: The Google Analytics account ID (a number or
          'accounts/<number>'). Find it with get_account_summaries.
        property_id: Optional property to limit results to.
        earliest_change_time: Optional RFC 3339 timestamp, e.g.
          "2026-10-01T00:00:00Z".
        latest_change_time: Optional RFC 3339 timestamp.
        resource_types: Optional ChangeHistoryResourceType names, e.g.
          ["PROPERTY", "CUSTOM_DIMENSION", "KEY_EVENT", "DATA_STREAM"].
        actions: Optional ActionType names: "CREATED", "UPDATED", "DELETED".
        page_size: Maximum number of change events to return.
    """
    account = str(account_id).strip()
    if not account.startswith("accounts/"):
        account = f"accounts/{account}"
    request = admin_v1beta.SearchChangeHistoryEventsRequest(
        account=account,
        resource_type=resource_types or [],
        action=actions or [],
        page_size=page_size,
    )
    if property_id:
        request.property = construct_property_rn(property_id)
    if earliest_change_time:
        request.earliest_change_time = earliest_change_time
    if latest_change_time:
        request.latest_change_time = latest_change_time

    def _sync_call():
        events = []
        for event in create_admin_api_client().search_change_history_events(
            request
        ):
            events.append(proto_to_dict(event))
            if len(events) >= page_size:
                break
        return events

    return await asyncio.to_thread(_sync_call)


async def get_property_settings(property_id: int | str) -> Dict[str, Any]:
    """Returns a property's data retention, attribution and Google signals settings.

    Settings that can't be read (for example, without permission) are
    reported under `errors` instead of failing the call.

    Args:
        property_id: The Google Analytics property ID.
    """
    prop = construct_property_rn(property_id)

    def _sync_call():
        beta = create_admin_api_client()
        alpha = create_admin_alpha_api_client()
        calls = {
            "data_retention": lambda: beta.get_data_retention_settings(
                name=f"{prop}/dataRetentionSettings"
            ),
            "attribution": lambda: alpha.get_attribution_settings(
                name=f"{prop}/attributionSettings"
            ),
            "google_signals": lambda: alpha.get_google_signals_settings(
                name=f"{prop}/googleSignalsSettings"
            ),
        }
        result: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        for key, call in calls.items():
            try:
                result[key] = proto_to_dict(call())
            except google_exceptions.GoogleAPICallError as ex:
                errors[key] = str(ex)
        if errors:
            result["errors"] = errors
        return result

    return await asyncio.to_thread(_sync_call)


async def run_access_report(
    property_id: int | str,
    date_ranges: List[Dict[str, Any]],
    dimensions: List[str],
    metrics: List[str],
    limit: int = 100,
) -> Dict[str, Any]:
    """Reports who has read the property's data, and when (data access records).

    Requires an administrator role on the property.

    Args:
        property_id: The Google Analytics property ID.
        date_ranges: e.g. [{"start_date": "30daysAgo", "end_date": "today"}].
        dimensions: Access dimensions, e.g. ["epochTimeMicros", "userEmail",
          "accessMechanism", "reportType"]
          (https://developers.google.com/analytics/devguides/config/admin/v1/access-api-schema).
        metrics: Access metrics, e.g. ["accessCount"].
        limit: Maximum rows to return.
    """
    request = admin_v1beta.RunAccessReportRequest(
        entity=construct_property_rn(property_id),
        date_ranges=[admin_v1beta.AccessDateRange(dr) for dr in date_ranges],
        dimensions=[
            admin_v1beta.AccessDimension(dimension_name=d) for d in dimensions
        ],
        metrics=[admin_v1beta.AccessMetric(metric_name=m) for m in metrics],
        limit=limit,
    )
    response = await asyncio.to_thread(
        lambda: create_admin_api_client().run_access_report(request)
    )
    return proto_to_dict(response)
