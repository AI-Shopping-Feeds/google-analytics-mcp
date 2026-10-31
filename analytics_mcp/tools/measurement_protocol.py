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

"""GA4 Measurement Protocol: validate and send events from a server.

https://developers.google.com/analytics/devguides/collection/protocol/ga4
"""

import os
from typing import Any, Dict, List

import httpx

# Lets the API secret come from the environment instead of a tool argument.
API_SECRET_ENV_VAR = "GA_MEASUREMENT_PROTOCOL_API_SECRET"

_HOSTS = {
    "global": "https://www.google-analytics.com",
    "eu": "https://region1.google-analytics.com",
}
_MAX_EVENTS = 25


def _build(
    events: List[Dict[str, Any]],
    measurement_id: str,
    client_id: str,
    firebase_app_id: str,
    app_instance_id: str,
    api_secret: str,
    user_id: str,
    user_properties: Dict[str, Any],
    consent: Dict[str, str],
    timestamp_micros: int,
) -> tuple[Dict[str, str], Dict[str, Any]]:
    """Returns the query parameters and JSON body for a Measurement Protocol request."""
    secret = api_secret or os.environ.get(API_SECRET_ENV_VAR)
    if not secret:
        raise ValueError(
            f"An API secret is required: pass api_secret or set {API_SECRET_ENV_VAR}."
        )
    if not events or len(events) > _MAX_EVENTS:
        raise ValueError(
            f"Send between 1 and {_MAX_EVENTS} events per request."
        )
    for event in events:
        if not isinstance(event, dict) or not event.get("name"):
            raise ValueError('Every event needs a "name".')

    if (
        measurement_id
        and client_id
        and not (firebase_app_id or app_instance_id)
    ):
        params = {"measurement_id": measurement_id, "api_secret": secret}
        body: Dict[str, Any] = {"client_id": client_id}
    elif (
        firebase_app_id
        and app_instance_id
        and not (measurement_id or client_id)
    ):
        params = {"firebase_app_id": firebase_app_id, "api_secret": secret}
        body = {"app_instance_id": app_instance_id}
    else:
        raise ValueError(
            "Give measurement_id + client_id for a web stream, or "
            "firebase_app_id + app_instance_id for an app stream."
        )

    body["events"] = events
    if user_id:
        body["user_id"] = user_id
    if user_properties:
        body["user_properties"] = {
            k: v if isinstance(v, dict) and "value" in v else {"value": v}
            for k, v in user_properties.items()
        }
    if consent:
        body["consent"] = consent
    if timestamp_micros:
        body["timestamp_micros"] = timestamp_micros
    return params, body


def _host(region: str) -> str:
    if region not in _HOSTS:
        raise ValueError(f"region must be one of: {', '.join(_HOSTS)}.")
    return _HOSTS[region]


async def _post(url: str, params: Dict[str, str], body: Dict[str, Any]):
    async with httpx.AsyncClient(timeout=30) as client:
        return await client.post(url, params=params, json=body)


async def validate_measurement_protocol_events(
    events: List[Dict[str, Any]],
    measurement_id: str = None,
    client_id: str = None,
    firebase_app_id: str = None,
    app_instance_id: str = None,
    api_secret: str = None,
    user_id: str = None,
    user_properties: Dict[str, Any] = None,
    consent: Dict[str, str] = None,
    timestamp_micros: int = None,
    region: str = "global",
) -> Dict[str, Any]:
    """Checks Measurement Protocol events against Google's validation server. Nothing is recorded.

    Returns `valid` and Google's `validation_messages` (field path, code and
    description) for anything wrong with the payload. Note that the
    validation server doesn't check the API secret or measurement ID.

    Args:
        events: Up to 25 events, e.g. [{"name": "purchase", "params": {
          "transaction_id": "T1", "value": 49.99, "currency": "GBP",
          "items": [{"item_id": "SKU1", "price": 49.99, "quantity": 1}]}}].
        measurement_id: Web stream measurement ID (G-...), with client_id.
        client_id: The web client ID, e.g. from the _ga cookie.
        firebase_app_id: App stream Firebase app ID, with app_instance_id.
        app_instance_id: The app instance ID.
        api_secret: Measurement Protocol API secret. Prefer setting the
          GA_MEASUREMENT_PROTOCOL_API_SECRET environment variable.
        user_id: Optional user ID.
        user_properties: Optional {name: value} user properties.
        consent: Optional, e.g. {"ad_user_data": "GRANTED",
          "ad_personalization": "DENIED"}.
        timestamp_micros: Optional event time in Unix microseconds (up to 72
          hours in the past).
        region: "global" (default) or "eu" to use the EU endpoint.
    """
    params, body = _build(
        events,
        measurement_id,
        client_id,
        firebase_app_id,
        app_instance_id,
        api_secret,
        user_id,
        user_properties,
        consent,
        timestamp_micros,
    )
    response = await _post(f"{_host(region)}/debug/mp/collect", params, body)
    response.raise_for_status()
    messages = response.json().get("validationMessages", [])
    return {"valid": not messages, "validation_messages": messages}


async def send_measurement_protocol_events(
    events: List[Dict[str, Any]],
    measurement_id: str = None,
    client_id: str = None,
    firebase_app_id: str = None,
    app_instance_id: str = None,
    api_secret: str = None,
    user_id: str = None,
    user_properties: Dict[str, Any] = None,
    consent: Dict[str, str] = None,
    timestamp_micros: int = None,
    region: str = "global",
    skip_validation: bool = False,
) -> Dict[str, Any]:
    """Sends events to a GA4 property with the Measurement Protocol, e.g. offline purchases or refunds.

    The events are validated first, and nothing is sent if validation finds
    problems. Sent events show up in reports after normal processing (up to
    24-48 hours; DebugView and realtime sooner) and cannot be deleted, so
    confirm with the person before sending.

    Args:
        events: Up to 25 events; see validate_measurement_protocol_events.
        measurement_id: Web stream measurement ID (G-...), with client_id.
        client_id: The web client ID.
        firebase_app_id: App stream Firebase app ID, with app_instance_id.
        app_instance_id: The app instance ID.
        api_secret: Measurement Protocol API secret. Prefer setting the
          GA_MEASUREMENT_PROTOCOL_API_SECRET environment variable.
        user_id: Optional user ID.
        user_properties: Optional {name: value} user properties.
        consent: Optional consent settings.
        timestamp_micros: Optional event time in Unix microseconds.
        region: "global" (default) or "eu".
        skip_validation: Send without validating first. Not recommended.
    """
    params, body = _build(
        events,
        measurement_id,
        client_id,
        firebase_app_id,
        app_instance_id,
        api_secret,
        user_id,
        user_properties,
        consent,
        timestamp_micros,
    )
    host = _host(region)
    if not skip_validation:
        check = await _post(f"{host}/debug/mp/collect", params, body)
        check.raise_for_status()
        messages = check.json().get("validationMessages", [])
        if messages:
            return {
                "sent": False,
                "reason": "validation failed",
                "validation_messages": messages,
            }
    response = await _post(f"{host}/mp/collect", params, body)
    response.raise_for_status()
    return {
        "sent": True,
        "events": len(events),
        "status_code": response.status_code,
    }
