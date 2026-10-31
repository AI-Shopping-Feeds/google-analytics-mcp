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

"""Write tools that change a property's configuration.

They are only exposed when the server runs with --allow-write.
"""

import asyncio
from typing import Any, Dict

from analytics_mcp.tools.client import create_admin_api_client
from analytics_mcp.tools.utils import construct_property_rn, proto_to_dict
from google.analytics import admin_v1beta
from google.protobuf import field_mask_pb2

_DIMENSION_SCOPES = ("EVENT", "USER", "ITEM")
_METRIC_UNITS = (
    "STANDARD",
    "CURRENCY",
    "FEET",
    "METERS",
    "KILOMETERS",
    "MILES",
    "MILLISECONDS",
    "SECONDS",
    "MINUTES",
    "HOURS",
)
_RETENTION_VALUES = (
    "TWO_MONTHS",
    "FOURTEEN_MONTHS",
    "TWENTY_SIX_MONTHS",
    "THIRTY_EIGHT_MONTHS",
    "FIFTY_MONTHS",
)


def _choice(name: str, value: str, allowed) -> str:
    normalized = (value or "").strip().upper()
    if normalized not in allowed:
        raise ValueError(
            f"Invalid {name} '{value}'. Valid values: {', '.join(allowed)}."
        )
    return normalized


async def create_custom_dimension(
    property_id: int | str,
    parameter_name: str,
    display_name: str,
    scope: str = "EVENT",
    description: str = None,
) -> Dict[str, Any]:
    """Creates a custom dimension from an event, user or item parameter.

    Properties have limited custom dimension slots (50 event-scoped and 25
    user-scoped on standard properties), and the parameter name can't be
    changed later.

    Args:
        property_id: The Google Analytics property ID.
        parameter_name: The event parameter or user property to register,
          e.g. "plan_type". Letters, numbers and underscores, starting with a
          letter. For item scope, the item parameter name.
        display_name: Name shown in reports, e.g. "Plan type".
        scope: "EVENT" (default), "USER" or "ITEM".
        description: Optional description.
    """
    dimension = admin_v1beta.CustomDimension(
        parameter_name=parameter_name,
        display_name=display_name,
        scope=_choice("scope", scope, _DIMENSION_SCOPES),
        description=description or "",
    )
    request = admin_v1beta.CreateCustomDimensionRequest(
        parent=construct_property_rn(property_id), custom_dimension=dimension
    )
    response = await asyncio.to_thread(
        lambda: create_admin_api_client().create_custom_dimension(request)
    )
    return proto_to_dict(response)


async def create_custom_metric(
    property_id: int | str,
    parameter_name: str,
    display_name: str,
    measurement_unit: str = "STANDARD",
    description: str = None,
) -> Dict[str, Any]:
    """Creates an event-scoped custom metric from a numeric event parameter.

    Args:
        property_id: The Google Analytics property ID.
        parameter_name: The numeric event parameter, e.g. "items_viewed".
        display_name: Name shown in reports.
        measurement_unit: One of STANDARD (default), CURRENCY, FEET, METERS,
          KILOMETERS, MILES, MILLISECONDS, SECONDS, MINUTES, HOURS.
        description: Optional description.
    """
    metric = admin_v1beta.CustomMetric(
        parameter_name=parameter_name,
        display_name=display_name,
        measurement_unit=_choice(
            "measurement_unit", measurement_unit, _METRIC_UNITS
        ),
        scope="EVENT",
        description=description or "",
    )
    request = admin_v1beta.CreateCustomMetricRequest(
        parent=construct_property_rn(property_id), custom_metric=metric
    )
    response = await asyncio.to_thread(
        lambda: create_admin_api_client().create_custom_metric(request)
    )
    return proto_to_dict(response)


async def archive_custom_definition(resource_name: str) -> Dict[str, Any]:
    """Archives a custom dimension or custom metric, freeing its slot.

    Archived definitions stop collecting data and can't be restored.

    Args:
        resource_name: e.g. "properties/123/customDimensions/456" or
          "properties/123/customMetrics/789". Find these with
          get_custom_dimensions_and_metrics or call_api.
    """
    client = create_admin_api_client()
    if "/customDimensions/" in resource_name:
        call = lambda: client.archive_custom_dimension(name=resource_name)
    elif "/customMetrics/" in resource_name:
        call = lambda: client.archive_custom_metric(name=resource_name)
    else:
        raise ValueError(
            "resource_name must be a customDimensions or customMetrics name."
        )
    await asyncio.to_thread(call)
    return {"archived": resource_name}


async def create_key_event(
    property_id: int | str,
    event_name: str,
    counting_method: str = "ONCE_PER_EVENT",
    default_value: float = None,
    currency_code: str = None,
) -> Dict[str, Any]:
    """Marks an event as a key event (formerly called a conversion).

    Args:
        property_id: The Google Analytics property ID.
        event_name: The event name, e.g. "purchase" or "generate_lead".
        counting_method: "ONCE_PER_EVENT" (default) or "ONCE_PER_SESSION".
        default_value: Optional value to use when the event has no value.
        currency_code: Required with default_value, e.g. "GBP".
    """
    key_event = admin_v1beta.KeyEvent(
        event_name=event_name,
        counting_method=_choice(
            "counting_method",
            counting_method,
            ("ONCE_PER_EVENT", "ONCE_PER_SESSION"),
        ),
    )
    if default_value is not None:
        if not currency_code:
            raise ValueError("currency_code is required with default_value.")
        key_event.default_value = admin_v1beta.KeyEvent.DefaultValue(
            numeric_value=default_value, currency_code=currency_code
        )
    request = admin_v1beta.CreateKeyEventRequest(
        parent=construct_property_rn(property_id), key_event=key_event
    )
    response = await asyncio.to_thread(
        lambda: create_admin_api_client().create_key_event(request)
    )
    return proto_to_dict(response)


async def delete_key_event(resource_name: str) -> Dict[str, Any]:
    """Stops treating an event as a key event. The event itself is kept.

    Args:
        resource_name: e.g. "properties/123/keyEvents/456". Find it with
          list_key_events.
    """
    if "/keyEvents/" not in resource_name:
        raise ValueError("resource_name must be a keyEvents resource name.")
    await asyncio.to_thread(
        lambda: create_admin_api_client().delete_key_event(name=resource_name)
    )
    return {"deleted": resource_name}


async def update_data_retention(
    property_id: int | str,
    event_data_retention: str,
    reset_user_data_on_new_activity: bool = None,
) -> Dict[str, Any]:
    """Sets how long GA keeps event-level data used in explorations.

    Standard properties allow TWO_MONTHS or FOURTEEN_MONTHS; longer periods
    need Google Analytics 360.

    Args:
        property_id: The Google Analytics property ID.
        event_data_retention: TWO_MONTHS, FOURTEEN_MONTHS, TWENTY_SIX_MONTHS,
          THIRTY_EIGHT_MONTHS or FIFTY_MONTHS.
        reset_user_data_on_new_activity: Optional. Whether to restart the
          retention period when a user is active again.
    """
    settings = admin_v1beta.DataRetentionSettings(
        name=f"{construct_property_rn(property_id)}/dataRetentionSettings",
        event_data_retention=_choice(
            "event_data_retention", event_data_retention, _RETENTION_VALUES
        ),
    )
    paths = ["event_data_retention"]
    if reset_user_data_on_new_activity is not None:
        settings.reset_user_data_on_new_activity = (
            reset_user_data_on_new_activity
        )
        paths.append("reset_user_data_on_new_activity")
    request = admin_v1beta.UpdateDataRetentionSettingsRequest(
        data_retention_settings=settings,
        update_mask=field_mask_pb2.FieldMask(paths=paths),
    )
    response = await asyncio.to_thread(
        lambda: create_admin_api_client().update_data_retention_settings(
            request
        )
    )
    return proto_to_dict(response)


async def create_google_ads_link(
    property_id: int | str,
    google_ads_customer_id: str,
    ads_personalization_enabled: bool = True,
) -> Dict[str, Any]:
    """Links a Google Ads account to the property, to import key events and audiences into Google Ads.

    The person needs edit access to the property and admin access to the
    Google Ads account.

    Args:
        property_id: The Google Analytics property ID.
        google_ads_customer_id: The Google Ads customer ID, e.g. "1234567890"
          (dashes are removed).
        ads_personalization_enabled: Whether to allow personalised advertising
          features with this link.
    """
    link = admin_v1beta.GoogleAdsLink(
        customer_id="".join(c for c in google_ads_customer_id if c.isdigit()),
        ads_personalization_enabled=ads_personalization_enabled,
    )
    request = admin_v1beta.CreateGoogleAdsLinkRequest(
        parent=construct_property_rn(property_id), google_ads_link=link
    )
    response = await asyncio.to_thread(
        lambda: create_admin_api_client().create_google_ads_link(request)
    )
    return proto_to_dict(response)


async def create_measurement_protocol_secret(
    data_stream_name: str,
    display_name: str,
) -> Dict[str, Any]:
    """Creates a Measurement Protocol API secret for a data stream.

    Needed to send events with send_measurement_protocol_events. The person
    must have acknowledged the user data collection terms for the property in
    the Google Analytics UI first. Treat the returned `secret_value` like a
    password.

    Args:
        data_stream_name: e.g. "properties/123/dataStreams/456". Find it with
          list_data_streams.
        display_name: A label, e.g. "Server-side purchases".
    """
    if "/dataStreams/" not in data_stream_name:
        raise ValueError(
            "data_stream_name must be a dataStreams resource name."
        )
    request = admin_v1beta.CreateMeasurementProtocolSecretRequest(
        parent=data_stream_name,
        measurement_protocol_secret=admin_v1beta.MeasurementProtocolSecret(
            display_name=display_name
        ),
    )
    response = await asyncio.to_thread(
        lambda: create_admin_api_client().create_measurement_protocol_secret(
            request
        )
    )
    return proto_to_dict(response)
