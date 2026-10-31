# Google Analytics MCP Server (GA4, read + write)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/AI-Shopping-Feeds/google-analytics-mcp?style=social)](https://github.com/AI-Shopping-Feeds/google-analytics-mcp/stargazers)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

This repo contains the source code for running a local
[MCP](https://modelcontextprotocol.io) server that interacts with APIs for
[Google Analytics 4](https://support.google.com/analytics).

This is a fork of [googleanalytics/google-analytics-mcp](https://github.com/googleanalytics/google-analytics-mcp),
maintained by [AI Shopping Feeds](https://github.com/AI-Shopping-Feeds).
Upstream covers reports and a few account lookups. This fork adds:

- **Reports:** pivot reports, a field compatibility checker, a searchable list
  of every dimension and metric, and quota usage.
- **Property configuration:** data streams, key events, audiences, change
  history, data retention, attribution and Google signals settings, and data
  access reports.
- **Write tools** (with `--allow-write`): custom dimensions and metrics, key
  events, data retention, Google Ads links and Measurement Protocol secrets.
- **The Measurement Protocol:** validate events, and send them from a server,
  for example offline purchases and refunds.
- **Every other method:** the Data and Admin APIs have about 240 methods across
  v1beta and v1alpha, and `list_api_methods` and `call_api` reach all of them.

> **Using an AI agent?** See [Let your agent set it up](#let-your-agent-set-it-up).

## Let your agent set it up

Paste this into Claude Code, Codex, Cursor or any agent that can read web pages and edit files:

```text
Set up the Google Analytics MCP server for me by following https://raw.githubusercontent.com/AI-Shopping-Feeds/google-analytics-mcp/main/skills/google-analytics-mcp/SKILL.md
```

The agent:
- checks whether it's already connected
- installs the runner if you agree
- walks you through Google credentials
- adds the server to your client's config without touching your other servers
- checks it works by calling `get_account_summaries`

The same file is an [Agent Skill](https://agentskills.io), so your agent can keep it as a guide to using the tools well. For Claude Code, copy the folder into your skills:

```bash
git clone --depth 1 https://github.com/AI-Shopping-Feeds/google-analytics-mcp.git /tmp/google-analytics-mcp
cp -r /tmp/google-analytics-mcp/skills/google-analytics-mcp ~/.claude/skills/
```

Other agents that support skills load the same `skills/google-analytics-mcp` folder from their own skills directory.

## Tools 🛠️

The server uses the
[Google Analytics Data API](https://developers.google.com/analytics/devguides/reporting/data/v1),
the [Admin API](https://developers.google.com/analytics/devguides/config/admin/v1)
and the [Measurement Protocol](https://developers.google.com/analytics/devguides/collection/protocol/ga4).

### Reports 📙

| Tool | What it does |
|---|---|
| `run_report` | Runs a core report. |
| `run_realtime_report` | Runs a realtime report (last 30 minutes). |
| `run_funnel_report` | Runs a funnel report (Data API v1alpha). |
| `run_conversions_report` | Runs a report scoped to specific key events. |
| `run_pivot_report` | Runs a pivot (cross-tab) report. |
| `check_compatibility` | Checks which dimensions and metrics can be combined. |
| `get_dimensions_and_metrics` | Lists every standard and custom dimension and metric, with search. |
| `get_custom_dimensions_and_metrics` | Lists the property's custom dimensions and metrics. |
| `get_property_quotas_snapshot` | Shows Data API quota used today and this hour. |

### Account and property configuration 🟠

| Tool | What it does |
|---|---|
| `get_account_summaries` | Lists the accounts and properties the user can access. |
| `get_property_details` | Returns a property's details. |
| `get_property_settings` | Returns data retention, attribution and Google signals settings. |
| `list_data_streams` | Lists web and app data streams, with measurement IDs. |
| `list_key_events` | Lists key events (formerly conversions). |
| `list_audiences` | Lists audiences and their rules. |
| `list_google_ads_links` | Lists linked Google Ads accounts. |
| `list_property_annotations` | Lists annotations. |
| `search_change_history` | Shows who changed what in the account, and when. |
| `run_access_report` | Shows who read the property's data (admins only). |
| `list_api_methods` | Lists every Data and Admin API method, and a method's request fields. |
| `validate_measurement_protocol_events` | Checks Measurement Protocol events without recording them. |

### Write tools ✏️ (need `--allow-write`)

| Tool | What it does |
|---|---|
| `create_property_annotation` | Adds an annotation to reports. |
| `create_custom_dimension` | Registers an event, user or item parameter as a custom dimension. |
| `create_custom_metric` | Registers a numeric event parameter as a custom metric. |
| `archive_custom_definition` | Archives a custom dimension or metric. |
| `create_key_event` | Marks an event as a key event. |
| `delete_key_event` | Stops treating an event as a key event. |
| `update_data_retention` | Changes how long event-level data is kept. |
| `create_google_ads_link` | Links a Google Ads account. |
| `create_measurement_protocol_secret` | Creates an API secret for the Measurement Protocol. |
| `send_measurement_protocol_events` | Validates, then sends events to GA4. |
| `call_api` | Calls any Data or Admin API method, such as `create_audience` or `create_big_query_link`. |

### Write safety

- **Off by default:** write tools are only listed when the server starts
  with `--allow-write`. They also need the `analytics.edit` scope and at least
  the Editor (or Marketer) role on the property.
- **Annotated:** write tools carry MCP annotations
  (`readOnlyHint: false`). `archive_custom_definition`, `delete_key_event`,
  `send_measurement_protocol_events` and `call_api` are also marked
  `destructiveHint: true`, so clients that confirm destructive tools will ask
  first.
- **Measurement Protocol events:** `send_measurement_protocol_events`
  validates events against Google's debug endpoint and sends nothing if
  there are problems. Sent events can't be deleted. Set the API secret in
  `GA_MEASUREMENT_PROTOCOL_API_SECRET` instead of passing it to the tool.

## Setup instructions 🔧

✨ Watch the [Google Analytics MCP Setup
Tutorial](https://youtu.be/nS8HLdwmVlY) on YouTube for a step-by-step
walkthrough of these instructions.

[![Watch the video](https://img.youtube.com/vi/nS8HLdwmVlY/mqdefault.jpg)](https://www.youtube.com/watch?v=nS8HLdwmVlY)

Setup involves the following steps:

1.  Configure Python.
1.  Configure credentials for Google Analytics.
1.  Configure your MCP client.

### Configure Python 🐍

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) (or
[pipx](https://pipx.pypa.io/stable/#install-pipx)). The server runs straight from
this repository. The `analytics-mcp` package on PyPI is the upstream release
without this fork's tools.

```shell
uvx --from git+https://github.com/AI-Shopping-Feeds/google-analytics-mcp.git analytics-mcp
```

Pin a release by adding `@vX.Y.Z` to the URL.

### Enable APIs in your project ✅

[Follow the instructions](https://support.google.com/googleapi/answer/6158841)
to enable the following APIs in your Google Cloud project:

- [Google Analytics Admin API](https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com)
- [Google Analytics Data API](https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com)

### Configure credentials 🔑

Configure your [Application Default Credentials
(ADC)](https://cloud.google.com/docs/authentication/provide-credentials-adc).
Make sure the credentials are for a user with access to your Google Analytics
accounts or properties.

Credentials must include the Google Analytics read-only scope:

```
https://www.googleapis.com/auth/analytics.readonly
```

If you plan to enable write tools (such as `create_custom_dimension`) using
the `--allow-write` flag, your credentials must also include the edit scope:

```
https://www.googleapis.com/auth/analytics.edit
```

Check out
[Manage OAuth Clients](https://support.google.com/cloud/answer/15549257)
for how to create an OAuth client.

Here are some sample `gcloud` commands you might find useful:

- Set up ADC using user credentials and an OAuth desktop or web client after
  downloading the client JSON to `YOUR_CLIENT_JSON_FILE`.

  ```shell
  gcloud auth application-default login \
    --scopes https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/cloud-platform \
    --client-id-file=YOUR_CLIENT_JSON_FILE
  ```

- Set up ADC using service account impersonation.

  ```shell
  gcloud auth application-default login \
    --impersonate-service-account=SERVICE_ACCOUNT_EMAIL \
    --scopes=https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/cloud-platform
  ```

When the `gcloud auth application-default` command completes, copy the
`PATH_TO_CREDENTIALS_JSON` file location printed to the console in the
following message. You'll need this for the next step!

```
Credentials saved to file: [PATH_TO_CREDENTIALS_JSON]
```

### Configure Gemini

1.  Install [Gemini
    CLI](https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/installation.md)
    or [Gemini Code
    Assist](https://marketplace.visualstudio.com/items?itemName=Google.geminicodeassist).

1.  Create or edit the file at `~/.gemini/settings.json`, adding your server
    to the `mcpServers` list.

    Replace `PATH_TO_CREDENTIALS_JSON` with the path you copied in the previous
    step.

    We also recommend that you add a `GOOGLE_CLOUD_PROJECT` attribute to the
    `env` object. Replace `YOUR_PROJECT_ID` in the following example with the
    [project ID](https://support.google.com/googleapi/answer/7014113) of your
    Google Cloud project.

    ```json
    {
      "mcpServers": {
        "analytics-mcp": {
          "command": "uvx",
          "args": ["--from", "git+https://github.com/AI-Shopping-Feeds/google-analytics-mcp.git", "analytics-mcp"],
          "env": {
            "GOOGLE_APPLICATION_CREDENTIALS": "PATH_TO_CREDENTIALS_JSON",
            "GOOGLE_CLOUD_PROJECT": "YOUR_PROJECT_ID"
          }
        }
      }
    }
    ```

    To enable write tools, append `"--allow-write"` to `"args"`.

### Configure Claude Code

1.  Add the MCP server with the following command:

    Replace `PATH_TO_CREDENTIALS_JSON` with the path you copied in the previous
    step, and replace `YOUR_PROJECT_ID` with the
    [project ID](https://support.google.com/googleapi/answer/7014113) of your
    Google Cloud project.

    ```shell
    claude mcp add analytics-mcp \
      --scope user \
      -e "GOOGLE_APPLICATION_CREDENTIALS=PATH_TO_CREDENTIALS_JSON" \
      -e "GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID" \
      -- uvx --from git+https://github.com/AI-Shopping-Feeds/google-analytics-mcp.git analytics-mcp
    ```

    Add `--allow-write` at the end to enable write tools.

### Other MCP clients (Claude Desktop, Cursor, Codex, VS Code)

Use the command `uvx` with the arguments
`--from git+https://github.com/AI-Shopping-Feeds/google-analytics-mcp.git analytics-mcp` (plus `--allow-write` for write tools) and the
same `GOOGLE_APPLICATION_CREDENTIALS` and `GOOGLE_CLOUD_PROJECT` environment
variables, in `claude_desktop_config.json`, `~/.cursor/mcp.json`,
`~/.codex/config.toml` or `.vscode/mcp.json`. The
[agent skill](skills/google-analytics-mcp/SKILL.md) has a ready-made snippet
for each one.

## Try it out 🥼

Launch your MCP client (for example Claude Code, Gemini CLI or Gemini Code Assist) and type `/mcp`. You should see
`analytics-mcp` listed in the results.

Here are some sample prompts to get you started:

- Ask what the server can do:

  ```
  what can the analytics-mcp server do?
  ```

- Ask about a Google Analytics property

  ```
  Give me details about my Google Analytics property with 'xyz' in the name
  ```

- Prompt for analysis:

  ```
  what are the most popular events in my Google Analytics property in the last 180 days?
  ```

- Ask about signed-in users:

  ```
  were most of my users in the last 6 months logged in?
  ```

- Ask about property configuration:

  ```
  what are the custom dimensions and custom metrics in my property?
  ```

- Audit tracking setup:

  ```
  which data streams and key events does my property have, and what changed in the last 30 days?
  ```

- Send an offline purchase (with `--allow-write`):

  ```
  validate, then send a purchase event for order T1001 worth £49.99 to my web stream
  ```

## Contributing ✨

Contributions welcome! Open an issue or pull request on
[this repository](https://github.com/AI-Shopping-Feeds/google-analytics-mcp). See the [Contributing Guide](CONTRIBUTING.md).
