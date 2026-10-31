# Google Analytics MCP Server (GA4, read + write)

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/) [![Fork of googleanalytics/google-analytics-mcp](https://img.shields.io/badge/fork%20of-googleanalytics%2Fgoogle--analytics--mcp-lightgrey.svg)](https://github.com/googleanalytics/google-analytics-mcp)

An [MCP](https://modelcontextprotocol.io) server for
[Google Analytics 4](https://support.google.com/analytics), using the
[Data API](https://developers.google.com/analytics/devguides/reporting/data/v1),
[Admin API](https://developers.google.com/analytics/devguides/config/admin/v1) and
[Measurement Protocol](https://developers.google.com/analytics/devguides/collection/protocol/ga4).
Use it from Claude, ChatGPT, Cursor, Codex, Gemini or any MCP client to run reports,
audit and change property configuration, and send server-side events.

This is a fork of [googleanalytics/google-analytics-mcp](https://github.com/googleanalytics/google-analytics-mcp), maintained by [AI Shopping Feeds](https://github.com/AI-Shopping-Feeds). Upstream covers reports, a few account lookups and annotations. This fork adds:

- **reports**: pivot reports, a field compatibility checker, a searchable list of every dimension and metric, and quota usage
- **property configuration**: data streams, key events, audiences, change history, data retention, attribution and Google signals, and data access reports
- **write tools** (with `--allow-write`): custom dimensions and metrics, key events, data retention, Google Ads links and Measurement Protocol secrets
- the **Measurement Protocol**: validate events, then send them from a server, for example offline purchases
- **every other Data and Admin API method** (about 240) through `call_api`

Part of the AI Shopping Feeds MCP family: [Google Ads](https://github.com/AI-Shopping-Feeds/google-ads-mcp) · [Google Merchant Centre](https://github.com/AI-Shopping-Feeds/google-merchant-centre-mcp) · **Google Analytics** · [YouTube Studio](https://github.com/AI-Shopping-Feeds/youtube-studio-mcp).

## Let your agent set it up

Paste this into Claude Code, Codex, Cursor or any agent that can read web pages and edit files:

```text
Set up the Google Analytics MCP server for me by following https://raw.githubusercontent.com/AI-Shopping-Feeds/google-analytics-mcp/main/skills/google-analytics-mcp/SKILL.md
```

The agent checks whether it's already connected, installs the runner if you
agree, walks you through Google sign-in, adds the server to your
client's config without touching your other servers, and checks it works by
calling `get_account_summaries`.

The same file is an [Agent Skill](https://agentskills.io), so your agent can keep it as a guide to using the tools well. For Claude Code, copy the folder into your skills:

```bash
git clone --depth 1 https://github.com/AI-Shopping-Feeds/google-analytics-mcp.git /tmp/google-analytics-mcp
cp -r /tmp/google-analytics-mcp/skills/google-analytics-mcp ~/.claude/skills/
```

Other agents that support skills load the same `skills/google-analytics-mcp` folder from their own skills directory.

## What it can do

32 tools: 21 read tools, plus 11 write tools when the server runs with `--allow-write`.

### Read

| Area | Tools |
|---|---|
| Reports | `run_report`, `run_realtime_report`, `run_funnel_report`, `run_conversions_report`, `run_pivot_report` |
| Fields | `get_dimensions_and_metrics` (searchable, standard and custom), `get_custom_dimensions_and_metrics`, `check_compatibility` |
| Properties | `get_account_summaries`, `get_property_details`, `get_property_settings`, `list_data_streams`, `list_key_events`, `list_audiences`, `list_google_ads_links`, `list_property_annotations` |
| Auditing | `search_change_history`, `run_access_report`, `get_property_quotas_snapshot` |
| Measurement Protocol | `validate_measurement_protocol_events` (checks events without recording them) |
| API | `list_api_methods`: every Data and Admin API method, with request fields |

### Write

Only listed when the server starts with `--allow-write`.

| Area | Tools |
|---|---|
| Custom definitions | `create_custom_dimension`, `create_custom_metric`, `archive_custom_definition` |
| Key events | `create_key_event`, `delete_key_event` |
| Settings and links | `update_data_retention`, `create_google_ads_link`, `create_property_annotation` |
| Measurement Protocol | `create_measurement_protocol_secret`, `send_measurement_protocol_events` |
| Any method | `call_api`: audiences, BigQuery links, channel groups, enhanced measurement and the rest |

### Safety

- Write tools are off unless the server starts with `--allow-write`. They also need the `analytics.edit` scope and the Editor (or Marketer) role.
- Tools carry MCP titles and annotations; archiving, deleting, shortening data retention, sending events and `call_api` are marked destructive so clients can ask first.
- `send_measurement_protocol_events` validates events with Google first and sends nothing if there are problems. Sent events can't be deleted.
- Set the Measurement Protocol secret in `GA_MEASUREMENT_PROTOCOL_API_SECRET` instead of passing it to the tool.

## Supported clients

| Client | Works? | How |
|---|---|---|
| Claude Code | ✅ | Local server, `claude mcp add` (below) |
| Claude Desktop | ✅ | Local server, `claude_desktop_config.json` |
| Cursor | ✅ | Local server, `~/.cursor/mcp.json` |
| VS Code (Copilot) | ✅ | Local server, `.vscode/mcp.json` (uses `servers` instead of `mcpServers`) |
| Codex | ✅ | Local server, `~/.codex/config.toml` |
| Gemini CLI | ✅ | Local server, `~/.gemini/settings.json` |
| Windsurf and other local clients | ✅ | Local server, same JSON entry |
| Claude.ai and ChatGPT | ❌ not yet | These need a remote server with sign-in. This server only runs locally (stdio). Use a local client. |

## Setup

### 1. Install uv

The server runs with `uvx` from [uv](https://docs.astral.sh/uv/getting-started/installation/)
(`brew install uv` on macOS) and needs Python 3.10 or later. It installs straight
from this repository:

```shell
uvx --from git+https://github.com/AI-Shopping-Feeds/google-analytics-mcp.git analytics-mcp
```

Add `--allow-write` after `analytics-mcp` to enable write tools (here and in the client configs below). The `analytics-mcp` package on PyPI is Google's upstream release without this fork's tools, so install from this repository. Pin a release by adding `@vX.Y.Z` to the URL.

### 2. Get credentials

1. **Google Cloud project:** enable the
   [Admin API](https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com) and
   [Data API](https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com),
   and create an OAuth client (Desktop app).
2. **Sign in** with Application Default Credentials, as a Google user with access to
   your properties. Leave out `analytics.edit` if you only want read tools.

   ```shell
   gcloud auth application-default login \
     --scopes https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/analytics.edit,https://www.googleapis.com/auth/cloud-platform \
     --client-id-file=PATH_TO_OAUTH_CLIENT_JSON
   ```

   The credentials file path it prints is `GOOGLE_APPLICATION_CREDENTIALS`.

Service account impersonation and more: [docs/credentials.md](docs/credentials.md).

### 3. Add it to your client

Replace the placeholders. Keep your other servers in each file.

**Claude Code**

```bash
claude mcp add --scope user google-analytics \
  --env GOOGLE_APPLICATION_CREDENTIALS=/abs/path/credentials.json \
  --env GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID \
  -- uvx --from git+https://github.com/AI-Shopping-Feeds/google-analytics-mcp.git analytics-mcp
```

**Claude Desktop, Cursor, Gemini CLI, Windsurf** (and VS Code under `servers`)

```json
{
  "mcpServers": {
    "google-analytics": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/AI-Shopping-Feeds/google-analytics-mcp.git", "analytics-mcp"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/abs/path/credentials.json",
        "GOOGLE_CLOUD_PROJECT": "YOUR_PROJECT_ID"
      }
    }
  }
}
```

Desktop apps often can't find `uvx` on the PATH; if the server doesn't start, use
the full path from `which uvx` as the `command`.

**Codex** (`~/.codex/config.toml`)

```toml
[mcp_servers.google-analytics]
command = "uvx"
args = ["--from", "git+https://github.com/AI-Shopping-Feeds/google-analytics-mcp.git", "analytics-mcp"]
env = { GOOGLE_APPLICATION_CREDENTIALS = "/abs/path/credentials.json", GOOGLE_CLOUD_PROJECT = "YOUR_PROJECT_ID" }
```

### 4. Check it works

Restart or reload the client, then ask it to "list my Google Analytics accounts and properties". It should
call `get_account_summaries`.

## Configuration

| Variable | Required | What it does |
|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | yes* | Path to Application Default Credentials (*or a gcloud default login) |
| `GOOGLE_CLOUD_PROJECT` | recommended | Google Cloud project with the Admin and Data APIs enabled |
| `GA_MEASUREMENT_PROTOCOL_API_SECRET` | no | Measurement Protocol API secret, used when a tool call doesn't pass one |
| `--allow-write` (flag) | no | Enables write tools; needs the `analytics.edit` scope |
| `--tools` (flag) or `GOOGLE_ANALYTICS_MCP_TOOL_GROUPS` | no | Comma-separated tool groups to register, e.g. `--tools reports,properties`. The flag wins over the variable. Default: all groups |

Tool groups keep the tool list short when you only need part of it. `get_account_summaries` is always registered, and write tools still need `--allow-write`. An unknown group stops the server at startup.

| Group | Read tools | Write tools (`--allow-write`) |
|---|---|---|
| `reports` | `run_report`, `run_realtime_report`, `run_funnel_report`, `run_conversions_report`, `run_pivot_report`, `check_compatibility`, `get_dimensions_and_metrics`, `get_custom_dimensions_and_metrics`, `get_property_quotas_snapshot` | none |
| `properties` | `get_property_details`, `get_property_settings`, `list_data_streams`, `list_key_events`, `list_audiences`, `list_google_ads_links`, `list_property_annotations`, `search_change_history`, `run_access_report` | `create_property_annotation`, `create_custom_dimension`, `create_custom_metric`, `archive_custom_definition`, `create_key_event`, `delete_key_event`, `update_data_retention`, `create_google_ads_link` |
| `measurement_protocol` | `validate_measurement_protocol_events` | `create_measurement_protocol_secret`, `send_measurement_protocol_events` |
| `api` | `list_api_methods` | `call_api` |

## Example prompts

```text
What were my top 10 products by revenue in the last 28 days, and how did that compare with the previous 28?
```

```text
Break down sessions by channel and device as a pivot table.
```

```text
Audit my property: data streams, key events, custom dimensions, data retention, and what changed in the last 30 days.
```

```text
Validate, then send a purchase event for order T1001 worth £49.99 to my web stream.
```

## More docs

- [Credentials](docs/credentials.md): enabling the APIs, OAuth clients and service account impersonation
- [Agent skill](skills/google-analytics-mcp/SKILL.md): setup and usage guide for agents

## Contributing and licence

Issues and pull requests are welcome on [this repository](https://github.com/AI-Shopping-Feeds/google-analytics-mcp). See
[CONTRIBUTING.md](CONTRIBUTING.md).

Licensed under the [Apache License 2.0](LICENSE). Based on [googleanalytics/google-analytics-mcp](https://github.com/googleanalytics/google-analytics-mcp) by Google.

- The server sends your Google Analytics data to the agent or LLM you connect it to.

---

Try out [AI Shopping Feeds](https://aishoppingfeeds.com/), our shopping feed management tool (including Google Shopping feeds).
