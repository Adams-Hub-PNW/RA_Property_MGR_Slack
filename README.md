# Ruby (Slack half)

Slack app in Socket Mode for Roxy's property-management assistant. Roxy talks to Ruby in one DM;
Ruby files things and posts quiet updates into 9 muted job-area channels. Notion is the permanent record.
Design: [docs/slack-design.md](docs/slack-design.md).

## Status
Built: Phase 1 (intent router, confirm/Edit/Cancel, Undo, channel setup, App Home) and Phase 2 core
(7/11/2/4/5 beats, quiet-hours gate, Top 3 ranking, follow-up/star rule, Brain dump, Overwhelm reset,
emoji + buttons, /dump /top3 /week /overwhelmed /quiet, #wins, edit-in-place channel cards).
Notion (Phase 1): Task Tracker mirror, retry queue, startup sync, Brain read (`ruby/notion.py`); database IDs in `ruby/notion_ids.json`. Other databases are created but not yet written to.
Stubbed: Outlook, voice memos, DAR drafting, vendor drafts,
stuck-unit and Friday recap content.

## Setup
1. Create the app from `manifest.yaml` (api.slack.com/apps -> From manifest). Add an app-level token (`connections:write`).
2. `cp .env.example .env`, fill in tokens and `ROXY_SLACK_USER_ID`.
3. `pip install -r requirements.txt && python -m ruby.setup_workspace` (creates channels, pins guides and emoji key).
4. `python -m ruby.main` locally, or deploy to Railway (`Procfile`/`railway.json`; mount a volume at `/data` and set `RUBY_STATE_PATH=/data/ruby_state.json`).
5. DM Ruby "hi Ruby". Test the draft Copy long-press on Roxy's phone.

Tests: `pip install -r requirements-dev.txt && pytest`.
