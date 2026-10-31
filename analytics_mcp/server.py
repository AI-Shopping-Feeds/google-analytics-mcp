#!/usr/bin/env python

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

"""Entry point for the Google Analytics MCP server."""

import argparse
import os
import sys
from typing import Sequence

import analytics_mcp.coordinator as coordinator

TOOL_GROUPS_ENV_VAR = "GOOGLE_ANALYTICS_MCP_TOOL_GROUPS"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Google Analytics MCP Server",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {coordinator.SERVER_VERSION}",
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help=(
            "Enable tools that create or modify Google Analytics resources "
            "(requires https://www.googleapis.com/auth/analytics.edit scope)."
        ),
    )
    parser.add_argument(
        "--tools",
        metavar="GROUPS",
        default=None,
        help=(
            "Comma-separated tool groups to register: "
            f"{', '.join(coordinator.TOOL_GROUPS)}. Defaults to all groups, "
            f"or to ${TOOL_GROUPS_ENV_VAR} when set. get_account_summaries "
            "is always registered."
        ),
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parses command-line arguments for the MCP server.

    Resolves `tool_groups` from --tools, falling back to the
    GOOGLE_ANALYTICS_MCP_TOOL_GROUPS environment variable. Exits with a usage
    error if a group is unknown.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.tools is not None:
        source, value = "--tools", args.tools
    else:
        source, value = TOOL_GROUPS_ENV_VAR, os.environ.get(TOOL_GROUPS_ENV_VAR)
    try:
        args.tool_groups = coordinator.parse_tool_groups(value)
    except ValueError as exc:
        parser.error(f"{source}: {exc}")
    return args


def run_server(argv: Sequence[str] | None = None):
    """Runs the MCP server over standard I/O."""
    args = parse_args(argv)
    app = coordinator.create_server(
        allow_write=args.allow_write, tool_groups=args.tool_groups
    )
    print(
        f"Starting MCP Stdio Server: {app.name} {app.version}"
        f" (tool groups: {', '.join(sorted(args.tool_groups))};"
        f" write tools {'on' if args.allow_write else 'off'})",
        file=sys.stderr,
    )
    app.run("stdio")


if __name__ == "__main__":
    try:
        run_server()
    except KeyboardInterrupt:
        print("\nMCP Server (stdio) stopped by user.", file=sys.stderr)
    except Exception:
        import traceback

        print("MCP Server (stdio) encountered an error:", file=sys.stderr)
        traceback.print_exc()
    finally:
        print("MCP Server (stdio) process exiting.", file=sys.stderr)
