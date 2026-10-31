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

"""Generic access to every Google Analytics Data API and Admin API method.

The available methods are discovered from the installed client libraries, so
upgrading them exposes new methods without code changes.
"""

import asyncio
import inspect
from typing import Any, Dict, List

import proto

from analytics_mcp.tools import client as clients
from analytics_mcp.tools.utils import proto_to_dict
from google.analytics import (
    admin_v1alpha,
    admin_v1beta,
    data_v1alpha,
    data_v1beta,
)

# (api, version) -> (client class, factory that returns a configured client)
_CLIENTS = {
    ("data", "v1beta"): (
        data_v1beta.BetaAnalyticsDataClient,
        clients.create_data_api_client,
    ),
    ("data", "v1alpha"): (
        data_v1alpha.AlphaAnalyticsDataClient,
        clients.create_data_api_alpha_client,
    ),
    ("admin", "v1beta"): (
        admin_v1beta.AnalyticsAdminServiceClient,
        clients.create_admin_api_client,
    ),
    ("admin", "v1alpha"): (
        admin_v1alpha.AnalyticsAdminServiceClient,
        clients.create_admin_alpha_api_client,
    ),
}


def _methods(client_cls) -> List[str]:
    return sorted(
        name
        for name, fn in inspect.getmembers(client_cls, inspect.isfunction)
        if not name.startswith("_")
        and "request" in inspect.signature(fn).parameters
    )


def _request_fields(client_cls, method: str) -> List[str]:
    annotation = (
        inspect.signature(getattr(client_cls, method))
        .parameters["request"]
        .annotation
    )
    for arg in getattr(annotation, "__args__", ()):
        if hasattr(arg, "meta"):
            return list(arg.meta.fields)
    return []


def _lookup(api: str, version: str):
    key = (api, version)
    if key not in _CLIENTS:
        raise ValueError(
            "api must be 'data' or 'admin', and version 'v1beta' or 'v1alpha'."
        )
    return _CLIENTS[key]


async def list_api_methods(
    api: str = None, version: str = None, method: str = None
) -> Dict[str, Any]:
    """Lists every Google Analytics Data API and Admin API method that call_api can run.

    With no arguments, returns all methods for each API and version. With
    api, version and method, also returns that method's request fields.
    Prefer v1beta; v1alpha methods may change.

    Args:
        api: "data" or "admin".
        version: "v1beta" or "v1alpha".
        method: A snake_case method name, e.g. "create_audience".
    """
    if method:
        client_cls, _ = _lookup(api, version)
        if method not in _methods(client_cls):
            raise ValueError(f"{api} {version} has no method '{method}'.")
        return {
            "api": api,
            "version": version,
            "method": method,
            "request_fields": _request_fields(client_cls, method),
        }
    return {
        f"{a}_{v}": _methods(cls)
        for (a, v), (cls, _) in _CLIENTS.items()
        if (api is None or a == api) and (version is None or v == version)
    }


async def call_api(
    api: str,
    version: str,
    method: str,
    request: Dict[str, Any],
    max_results: int = 200,
) -> Any:
    """Calls any Google Analytics Data API or Admin API method with a raw request.

    Use it only when no dedicated tool fits, for example:
    - Admin: create_audience, update_custom_dimension,
      create_data_stream, create_big_query_link, update_enhanced_measurement_settings,
      create_channel_group, create_calculated_metric, update_attribution_settings
    - Data: create_audience_export, batch_run_reports, create_report_task

    This can change or delete configuration, which is why it's only available
    with --allow-write. Call list_api_methods with the method name first to see
    its request fields.

    Args:
        api: "data" or "admin".
        version: "v1beta" or "v1alpha".
        method: snake_case method name, e.g. "update_custom_dimension".
        request: The request message as a dict with snake_case field names and
          enum values as strings, e.g. {"custom_dimension": {"name":
          "properties/1/customDimensions/2", "display_name": "Plan"},
          "update_mask": {"paths": ["display_name"]}}.
        max_results: For list and search methods, the maximum items to return.
    """
    client_cls, factory = _lookup(api, version)
    if method not in _methods(client_cls):
        raise ValueError(
            f"{api} {version} has no method '{method}'. Use list_api_methods."
        )

    def _sync_call():
        response = getattr(factory(), method)(request=request)
        if response is None:
            return {"ok": True}
        if isinstance(response, proto.Message):
            return proto_to_dict(response)
        # Pagers yield items; return up to max_results of them.
        items = []
        for item in response:
            items.append(
                proto_to_dict(item) if isinstance(item, proto.Message) else item
            )
            if len(items) >= max_results:
                break
        return items

    return await asyncio.to_thread(_sync_call)
