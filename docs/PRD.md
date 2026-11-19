# Ruby PRD (v1 draft)

Reconciles [notion-workspace-outline.md](notion-workspace-outline.md) (Notion, data, Outlook) with
[slack-design.md](slack-design.md) (Slack behavior, already built). Where they disagreed, the choice
made here is in §1. Items marked **(confirm)** need Roxy's yes.

Owner: Roxy Adams, Property Manager, Peak 88 + Heritage Grove (11 Residential, Renton WA).

## 1. Reconciled decisions

| Topic | Outline said | Slack design said | **Resolved** |
|---|---|---|---|
| Daily rhythm | 7:00 checklist, 4:00 DAR | 7:00 Top 3, 11:00/2:00 check-ins, 4:00 DAR, 5:00 shutdown | **Slack design (built).** The 7:00 post contains the Top 3 plus the full checklist content from the outline (tasks by property, move-ins/outs, SODA, overdue, renewals, urgent emails, calendar). |
| Channels | DM + optional #ruby-log | DM + 9 muted channels | **DM + 9 muted channels (built).** DM is the only thing that pings. Notion changes are logged in #ruby-log. |
| Quiet hours | 7 AM-6 PM, urgent exempt | Mon-Fri 7:00-17:30; only urgent, next-morning move-in gaps, next-business-day legal deadlines may break it, 6:00-21:00 | **Slack design.** (confirm: weekends fully quiet) |
| Memory | Notion only | JSON working state, Notion mirror | **Notion is the system of record; JsonStore is a cache + retry queue.** On startup Ruby syncs from Notion; on conflict Notion wins. Failed Notion writes stay queued and are retried, never dropped. |
| Make Ready | Two databases | n/a | **One database, `Property` select, two board views** (Peak 88 / Heritage Grove) plus a combined Stuck view. Same look for Roxy, simpler code and reporting. (confirm) |
| Email Triage | Summary only | n/a | **Summary only**, no raw email text in Notion. (confirm) |
| Transcription | Whisper | n/a | **OpenAI Whisper API**, with consent prompt first. |
| Move-out -> Make Ready | Auto-create card | n/a | **Auto-create, shown through Approve / Edit / Cancel**, so it still follows "drafts only". |

## 2. Principles (non-negotiable)

1. Ruby only drafts. Nothing is sent, posted, scheduled or created in Outlook without Roxy's Approve.
2. Residents: unit # + first name only. No balances or dollar amounts in Notion or channels (a checkbox for "under $500" only).
3. Ruby never touches Yardi, Cube, HappyCo, Key2Purchase, Rapidsoft. She reminds and gives a checklist; Roxy enters.
4. No manual rent changes (Revenue IQ). Concessions need Robin's approval; Ruby can draft the request.
5. Approved vendors only.
6. Every write carries Source (Slack link) + Created by Ruby, and is Undo-able for 24h.
7. Calm, batched, one next thing (see slack-design principles).

## 3. System

Slack (Socket Mode) -> Ruby (Python, Railway, volume at `/data`) -> Claude API (intent, drafting, triage) / Notion API (records) / Microsoft Graph (calendar only, `Calendars.ReadWrite`) / Whisper (audio) / scheduler (beats, reminders, sweeps).

Existing modules: `intent`, `core`, `store` (`Store`/`JsonStore`/`NotionMirror`), `scheduler`, `quiet`, `top3`, `followup`, `messages`, `models`.

## 4. Data model (Notion)

Source of truth for fields: outline §2 (page tree), §3 (Ruby's Brain), §4 (Today dashboard), §5 (all 23 databases). Deltas from the outline:

- Make Ready is a single database (§1). Vendor Jobs relate to it.
- Add `Notion ID` mapping per `Item` so `NotionMirror.upsert` is idempotent.
- Ruby's Brain page is read at startup and on `refresh`; edits by Roxy in Notion or Slack take effect without redeploy.

## 5. Behavior

Slack behavior is as built (intent router, confirm/Edit/Cancel, Undo, emoji + buttons, Top 3 ordering, follow-up/star rule, Brain dump, Overwhelm reset, slash commands). Intents to add per outline §6:

| Intent | Result |
|---|---|
| Unit vacant / needs work | Make Ready card, approved vendor suggestions, drafted messages, offer to schedule |
| Pasted email | Email Triage row (topic, urgency, summary), To-Dos, reply draft offered |
| Template trigger phrase | Template filled with placeholders |
| Renewal call | Call Log row + Renewal status/next action |
| Tour/prospect note | Daily Note |
| "done with X" | Task Tracker occurrence Done |
| Add/list recurring task | Confirm, then Recurring Tasks |
| Supplies | Supply List rows |
| Audio upload | Consent question, transcribe, Meeting row, To-Dos |
| Schedule vendor | Draft event, Approve, create in Outlook, update Vendor Job |

Scheduled: beats per slack-design; reminders from due time + offset; daily overdue sweep; 7th = delinquency cycle; first business day = inspections; Mon/Thu 11:00 stuck units; Fri 5:00 weekly wins; day-before move-in gap reminder; daily work-order follow-up.

## 6. Build phases

| # | Phase | Scope | Status |
|---|---|---|---|
| 0 | Slack shell | Router, confirm/Undo, beats, quiet hours, Top 3, channels | **Done** |
| 1 | Foundation | Create Notion workspace + all databases + Brain page; implement `NotionMirror` (upsert/archive/retry/startup sync); Claude API intent classification replacing keyword router | **In progress**: 23 databases + Brain + Today created; Task Tracker mirror, retry, sync done; Claude intent router pending |
| 2 | Daily engine | Recurring Tasks -> Task Tracker generator, real 7:00 content, reminders, overdue sweep, "done", add/change tasks | |
| 3 | Make Ready + Vendors + Outlook | Board, Vendor Jobs, drafts, Graph auth, Approve-to-create, conflict check | |
| 4 | Communication | Email Triage, Templates, Daily Notes -> 4:00 DAR in Roxy's voice | |
| 5 | Residents | Renewals + Call Log, Move-Ins/Outs + SODA (+7 days), Work Orders, Delinquency, Inspections | |
| 6 | Voice + extras | Whisper, Meetings, Supply List, Leads (Phase 2), notices | |

## 7. Acceptance for Phase 1

- A task or note typed in Slack appears in the right Notion database with Source + Created by Ruby, within one retry cycle even if Notion was briefly down.
- Restart on a fresh volume rebuilds state from Notion.
- Undo archives the Notion page.
- Tests cover the mirror (mocked client), retry queue, and conflict rule.

## 8. Open items

From Roxy: 1-2 sample DARs; current templates (small balance letter, move-in outreach, Two Dots); full approved vendor list; Betsy/Barrett full names + emails, Sara Campbell's role, housing specialist contact; unit lists (Yardi export); weekly/quarterly tasks after orientation; Rapidsoft ad units and frequency.
Decisions: **company policy on pasting work emails into personal Slack/AI tools (blocks real use of Email Triage)**; Slack Free vs Pro; overwhelm-pause length; weekend quiet; confirm the four **(confirm)** rows above.
Risks: Washington all-party recording consent (Ruby asks first); Microsoft Entra app registration needs tenant admin consent; Facebook Marketplace has no API (paste only).
