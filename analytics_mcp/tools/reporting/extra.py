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

"""Pivot reports, compatibility checks, full metadata and quota snapshots."""

import asyncio
from typing import Any, Dict, List

from analytics_mcp.tools.client import (
    create_data_api_alpha_client,
    create_data_api_client,
)
from analytics_mcp.tools.utils import construct_property_rn, proto_to_dict
from google.analytics import data_v1alpha, data_v1beta


async def run_pivot_report(
    property_id: int | str,
    date_ranges: List[Dict[str, Any]],
    dimensions: List[str],
    metrics: List[str],
    pivots: List[Dict[str, Any]],
    dimension_filter: Dict[str, Any] = None,
    metric_filter: Dict[str, Any] = None,
    currency_code: str = None,
) -> Dict[str, Any]:
    """Runs a Google Analytics pivot report (a cross-tab of dimensions).

    Every dimension used in a pivot must also be in `dimensions`. Field names
    are snake_case.

    Args:
        property_id: The Google Analytics property ID (a number or
          'properties/<number>').
        date_ranges: Date ranges, e.g. [{"start_date": "28daysAgo",
          "end_date": "yesterday"}].
        dimensions: Dimension names, e.g. ["country", "deviceCategory"].
        metrics: Metric names, e.g. ["sessions"].
        pivots: Pivot definitions
          (https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/Pivot),
          e.g. [{"field_names": ["country"], "limit": 5},
          {"field_names": ["deviceCategory"], "limit": 3}].
        dimension_filter: Optional FilterExpression on dimensions.
        metric_filter: Optional FilterExpression on metrics.
        currency_code: Optional ISO 4217 currency code.
    """
    request = data_v1beta.RunPivotReportRequest(
        property=construct_property_rn(property_id),
        date_ranges=[data_v1beta.DateRange(dr) for dr in date_ranges],
        dimensions=[data_v1beta.Dimension(name=d) for d in dimensions],
        metrics=[data_v1beta.Metric(name=m) for m in metrics],
        pivots=[data_v1beta.Pivot(p) for p in pivots],
    )
    if dimension_filter:
        request.dimension_filter = data_v1beta.FilterExpression(
            dimension_filter
        )
    if metric_filter:
        request.metric_filter = data_v1beta.FilterExpression(metric_filter)
    if currency_code:
        request.currency_code = currency_code

    response = await asyncio.to_thread(
        lambda: create_data_api_client().run_pivot_report(request)
    )
    return proto_to_dict(response)


async def check_compatibility(
    property_id: int | str,
    dimensions: List[str] = None,
    metrics: List[str] = None,
) -> Dict[str, Any]:
    """Checks which dimensions and metrics can be used together in a report.

    Use it when a report fails with an incompatibility error, or before
    combining unusual fields. Returns each field with
    COMPATIBLE or INCOMPATIBLE.

    Args:
        property_id: The Google Analytics property ID.
        dimensions: Dimension names to check.
        metrics: Metric names to check.
    """
    request = data_v1beta.CheckCompatibilityRequest(
        property=construct_property_rn(property_id),
        dimensions=[data_v1beta.Dimension(name=d) for d in dimensions or []],
        metrics=[data_v1beta.Metric(name=m) for m in metrics or []],
    )
    response = await asyncio.to_thread(
        lambda: create_data_api_client().check_compatibility(request)
    )
    return proto_to_dict(response)


async def get_dimensions_and_metrics(
    property_id: int | str,
    search: str = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Lists every dimension and metric available for a property, standard and custom.

    Each item has its API name, UI name, description and category. Use the
    `api_name` values in reports.

    Args:
        property_id: The Google Analytics property ID.
        search: Optional case-insensitive text to filter by API name, UI name
          or description, e.g. "purchase" or "item".
    """
    metadata = await asyncio.to_thread(
        lambda: create_data_api_client().get_metadata(
            name=f"{construct_property_rn(property_id)}/metadata"
        )
    )

    def _keep(item) -> bool:
        if not search:
            return True
        text = f"{item.api_name} {item.ui_name} {item.description}".lower()
        return search.lower() in text

    def _summary(item) -> Dict[str, Any]:
        return {
            "api_name": item.api_name,
            "ui_name": item.ui_name,
            "description": item.description,
            "category": item.category,
            "custom": item.custom_definition,
        }

    return {
        "dimensions": [_summary(d) for d in metadata.dimensions if _keep(d)],
        "metrics": [_summary(m) for m in metadata.metrics if _keep(m)],
    }


async def get_property_quotas_snapshot(
    property_id: int | str,
) -> Dict[str, Any]:
    """Returns how much of the property's Data API quota has been used.

    Covers core, realtime and funnel token quotas per day and hour, and
    concurrent requests. Uses the Data API v1alpha.

    Args:
        property_id: The Google Analytics property ID.
    """
    request = data_v1alpha.GetPropertyQuotasSnapshotRequest(
        name=f"{construct_property_rn(property_id)}/propertyQuotasSnapshot"
    )
    response = await asyncio.to_thread(
        lambda: create_data_api_alpha_client().get_property_quotas_snapshot(
            request
        )
    )
    return proto_to_dict(response)
