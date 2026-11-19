# Ruby: Notion Workspace Outline (pre-PRD)

Version: Draft 1, Nov 18, 2026
Owner: Roxy Adams, Property Manager, Peak 88 + Heritage Grove (11 Residential, Renton WA)
Purpose: The blueprint for Ruby's Notion workspace and how it connects to Slack and Outlook. Once Roxy approves it, it becomes the PRD that Claude Code builds from.

## 0. Decisions locked in

| Topic | Decision |
|---|---|
| How Ruby runs | Custom Slack bot built by Claude Code: Slack + Claude API + Notion API + Microsoft Graph (Outlook) |
| Hosting | Railway (~$5/mo), always on, with scheduled jobs |
| Claude API | Roxy already has an Anthropic Console account and API key |
| Slack | New personal Slack workspace (Roxy + Ruby) |
| Notion | Personal workspace "Roxyadams" (hello@roxyadams.com). Nothing Ruby-related exists yet, so the build starts from scratch. |
| Outlook | hello@roxyadams.com on Microsoft 365 Business. Calendar is the single catch-all calendar. |
| Email intake | Roxy pastes emails into Slack. Ruby does not read any inbox. |
| Resident info in Notion | Unit # + first name only. Full details stay in Yardi. No dollar balances. |
| Proactive | Ruby messages first: 7:00 AM morning checklist, 4:00 PM DAR prompt, due/overdue reminders |
| Make Ready | Separate board for each property, starting empty |
| Renewal statuses | Need to Call, Contacted, No Response, Counter Offer (with details), Renewed/Signed, Giving Notice |
| DAR delivery | Ruby drafts in Slack; Roxy copies it into her work email and sends |
| Vendor messages | Ruby drafts in Slack; Roxy sends texts from her phone and emails from her work account |
| Voice notes | Roxy records with her phone's voice memo app and uploads the audio file to Slack. Ruby transcribes it and files it. |
| Standing rule | Ruby only drafts. Nothing is sent, posted or scheduled without Roxy's approval (calendar events need an Approve button click). |

## 1. Architecture

```
Roxy (Slack DM / #ruby channel, phone or desktop)
        │
        ▼
Ruby bot (Railway, Node or Python, Slack Socket Mode)
  ├── Claude API ............ understands plain language, drafts, categorizes
  ├── Notion API ............ reads/writes every database below (the "memory")
  ├── Microsoft Graph ....... reads/creates events on hello@roxyadams.com calendar
  ├── Transcription API ..... audio file → text (Claude can't take audio; e.g. OpenAI Whisper or Deepgram)
  └── Scheduler (cron) ...... 7:00 AM checklist, 4:00 PM DAR prompt, reminders, overdue sweep
```

- Notion is the single source of truth. Ruby keeps no memory outside Notion, apart from short-term conversation context.
- Each write Ruby makes includes a Source (Slack message link) and Created by Ruby flag so Roxy can audit.
- Confirm-before-save: for adds or changes to tasks, cards or calendar events, Ruby echoes back what she understood and shows Approve / Edit / Cancel buttons in Slack.

## 2. Notion page tree

```
🔴 Ruby HQ                                  (top-level page; Ruby's integration is shared here only)
├── 📌 Today                                 (dashboard: linked views, see §4)
├── 🧠 Ruby's Brain                          (settings + rules page, see §3)
│
├── 🏢 Properties & Units
│   ├── [DB] Properties
│   └── [DB] Units
│
├── 🔧 Make Ready
│   ├── [DB] Make Ready — Peak 88            (board)
│   ├── [DB] Make Ready — Heritage Grove     (board)
│   └── [DB] Vendor Jobs & Bids
│
├── ✅ Tasks
│   ├── [DB] Recurring Tasks                 (the definitions: what, how often)
│   ├── [DB] Task Tracker                    (each occurrence: due / done / overdue)
│   └── [DB] To-Dos                          (one-off items from emails, meetings, Slack)
│
├── 🚪 Move-Ins & Move-Outs
│   ├── [DB] Move-Ins
│   └── [DB] Move-Outs
│
├── 📞 Residents
│   ├── [DB] Renewals
│   ├── [DB] Renewal Call Log
│   ├── [DB] Delinquency Cycle
│   └── [DB] Work Orders
│
├── 🔍 Inspections
│   └── [DB] Inspections
│
├── 📨 Communication
│   ├── [DB] Email Triage
│   ├── [DB] Templates
│   ├── [DB] Daily Notes                     (all-day note dump → DAR)
│   ├── [DB] DARs
│   └── [DB] Meetings & Voice Notes
│
├── 📇 Directory
│   ├── [DB] Vendors
│   └── [DB] Contacts
│
├── 🛒 [DB] Supply List
└── 📣 [DB] Leads (Phase 2: Facebook Marketplace, etc.)
```

## 3. Ruby's Brain (settings page)

Ruby reads this page every time she starts up or refreshes. Roxy can edit it, or tell Ruby in Slack to change it.

- **Identity:** Ruby (she/her), assistant to Roxy Adams, PM for Peak 88 + Heritage Grove
- **Standing rules:** drafts only; no manual rent changes (Revenue IQ sets pricing); concessions need Robin's approval (Ruby can draft the request); approved vendors only; unit # + first name only for residents
- **Schedule:** morning checklist 7:00 AM, DAR prompt 4:00 PM, Pacific time. Proactive pings only between 7 AM and 6 PM unless something is marked urgent (assumption, confirm)
- **Voice guide:** how Roxy writes. Sample DARs go here (Roxy to provide 1–2)
- **Property facts:** addresses, office hours, unit counts, floor plans, key systems (Yardi, Cube, HappyCo, Key2Purchase, Rapidsoft, Revenue IQ, Chat IQ, Two Dots)
- **DAR recipients:** Robin Matishak, Betsy (full name/email TBD), Barrett (full name/email TBD)
- **Systems Ruby can't touch:** Yardi, Cube, HappyCo, Key2Purchase, Rapidsoft. For these, Ruby reminds Roxy and gives her a checklist, and Roxy does the entry.

## 4. "Today" dashboard (linked views)

- Due today: Task Tracker filtered to today, grouped by property
- Overdue: Task Tracker, Status = Overdue
- Move-ins tomorrow: with checklist progress
- Move-outs today: with checklist progress
- SODA deadlines this week: Move-Outs where SODA is not done, sorted by due date
- Make Ready: stuck: both boards, Waiting longer than 3 days or past target date
- Open emails: Email Triage, Status ≠ Answered, sorted by urgency
- Renewals to call next: Renewals, Next Action Date ≤ today
- Work orders needing follow-up
- Today's notes: Daily Notes, Date = today

## 5. Databases (fields)

Conventions for every database: Property (select: Peak 88 / Heritage Grove / Both), Created by Ruby (checkbox), Source (URL to Slack message), Notes (text). These are not repeated in each list below.

### 5.1 Properties
Name · Address · Unit count · Office phone · Notes (2 rows. Other databases relate here where useful.)

### 5.2 Units
Unit # (title, e.g. "C214") · Property (relation) · Floor plan · Status (Occupied / On Notice / Vacant / Model / Down) · Current resident first name · Lease end date · Last annual inspection date · Relations to: Make Ready cards, Move-Ins, Move-Outs, Renewals, Work Orders, Inspections.
Roxy to provide the unit list (export from Yardi if possible), or Ruby creates units as they come up.

### 5.3 Make Ready — Peak 88 / Make Ready — Heritage Grove
Two databases with identical schemas:
- Unit (title) · Unit (relation) · Floor plan
- Status (board columns): On Notice → Vacant, Not Started → In Progress → Waiting → Ready → Leased / Move-in Scheduled
- Waiting reason (select: Bid / Approval / Parts / Vendor / Other)
- Move-out date · Move-out inspection done (checkbox)
- Work needed (multi-select: Paint, Carpet, Cleaning, Resurfacing, Repairs, Appliances, Junk Haul, Pest, Flooring, Blinds, Other)
- Vendor Jobs (relation → Vendor Jobs & Bids)
- Target ready date · Days vacant (formula: today − move-out date)
- HappyCo updated (checkbox) · Blockers (text)
- Leased date / Move-in date
- Views: Board (default) · Stuck / Overdue · Calendar by target ready date

### 5.4 Vendor Jobs & Bids
Job (title, e.g. "C214 Paint") · Unit card (relation to either Make Ready DB) · Vendor (relation → Vendors) · Service · Bid amount · Bid status (Requested / Received / Sent for Approval / Approved / Declined) · Approved by · Appointment date/time · Outlook event ID (hidden, Ruby uses it) · Job status (Not Scheduled / Scheduled / In Progress / Done / Invoice Received) · Message draft (text).
These are business costs, not resident finances.

### 5.5 Recurring Tasks (definitions)
Task (title) · Cadence (Daily / Weekly / Monthly / Quarterly / Annual / Per Event) · Due rule (text Ruby understands, e.g. "every Monday", "by the 7th", "15th of month", "within 7 days of move-out") · Due time · Property (Peak 88 / Heritage Grove / Both, generating one occurrence per property) · Category (Leasing / Maintenance / Collections / Reporting / Admin / Inspections / Move-in / Move-out) · System (Yardi / HappyCo / Key2Purchase / Cube / Rapidsoft / Outlook / None) · Active (checkbox) · Start date (e.g. Annual unit inspections start Mar 2027) · Reminder offset

- Seeded from Roxy's Nov 18 list (log #13): all Daily, Monthly (first week), Monthly inspections, Annual unit inspections (target 7/month from March 2027), Weekly reports to Robin (delinquency, occupancy, market surveys)
- Per-unit checklists (move-in, move-out) live in their own databases, not here
- Weekly/Quarterly: placeholders until orientation is done; added later via Slack ("Add a weekly task: market survey every Monday")

### 5.6 Task Tracker (occurrences)
Task occurrence (title, e.g. "Post Rapidsoft ads, Nov 19, Peak 88") · Recurring Task (relation) · Due date · Status (Due / Done / Overdue / Skipped) · Completed at · Property
- Scheduler creates each day's/week's/month's rows ahead of time and marks unfinished ones as Overdue
- Roxy marks items done in Slack ("done with price sheets") or by ticking the box in Notion

### 5.7 To-Dos (one-offs)
To-do (title) · Due date · Priority (Urgent / High / Normal / Low) · Status (Open / Waiting / Done) · From (relation to Email Triage / Meetings / none) · Property

### 5.8 Move-Ins
Unit (relation) · Resident first name · Move-in date · Checklist checkboxes: Lock changed from vendor lock · Keys made · Move-in inspection done · Key pick-up time confirmed (date/time) · PSE account # confirmed ready · Renters insurance confirmed · Move-in gift placed · Ready (formula: all boxes checked)
Ruby reminds Roxy the day before move-in about any unchecked items.

### 5.9 Move-Outs
Unit (relation) · Move-out date · Checklist: Keys turned in · Vendor lock placed · Move-out inspection done (same day) · HappyCo make-ready updated · Added to Make Ready board · Vendors coordinated · SODA started · SODA sent
SODA due (formula: move-out date + 7 days) · SODA days left (formula)
When Roxy logs a move-out, Ruby creates the Make Ready card automatically (Status = Vacant, Not Started).

### 5.10 Renewals
Unit (relation) · Resident first name · Lease end date · Status: Need to Call / Contacted / No Response / Counter Offer / Renewed–Signed / Giving Notice · Counter offer details (text) · Attempts (rollup count from Call Log) · Last contact date (rollup) · Next action date · Next action (text)
- Views: Call next (sorted by lease end) · By status (board) · Expiring in 60/90 days
- Status = Giving Notice → Ruby asks whether to add an "On Notice" card to that property's Make Ready board

### 5.11 Renewal Call Log
Date/time · Renewal (relation) · Method (Call / Text / Email / In person) · Outcome (Reached / Voicemail / No answer / Counter / Agreed / Declined) · How it went (text, in Roxy's words)

### 5.12 Delinquency Cycle (monthly)
Month (e.g. "Dec 2026") · Unit (relation) · Resident first name · Section 8 (checkbox) · Steps: 30-day notice issued · Declaration of service · VAWA notice · Posted to door · Mailed USPS · Scanned + uploaded to profile · Yardi notes updated · Cube notes updated · Housing specialist notified (if Section 8) · Small balance letter (checkbox, used instead of a notice when the balance is under $500) · 30-day POV expired date · POV packet sent to Robin / Sara / evictions inbox (checkbox)
- No dollar amounts stored: only a checkbox for whether the balance is under $500
- Ruby builds the checklist on the 7th from the list Roxy pastes in

### 5.13 Work Orders
WO # (from Yardi/HappyCo) · Unit · Issue (short) · Status (Needs Scheduling / Scheduled / Completed – Needs Follow-up / Closed) · Scheduled date · Completed date · Follow-up done (checkbox) · Vendor (relation, optional)
- Daily reminder: anything in Needs Scheduling, and completed WOs without a follow-up
- Open: Roxy pastes WOs in, or later a Yardi/HappyCo export if one is available

### 5.14 Inspections
Inspection (title) · Type (Monthly Property / Landscape Log / Light / Annual Unit / Move-in / Move-out / City / Insurance / Other) · Property · Unit (relation, for unit inspections) · Due date · Done date · Done in HappyCo (checkbox) · Prep needed (text) · Issues found (text)
View: Annual unit progress: this month's count vs. target of 7, plus units not inspected in the last 12 months

### 5.15 Email Triage
Subject (title) · Sender name · Sender org · Received date · Topic (Leasing / Maintenance / Vendor / Collections / Corporate / Reporting / Resident / Compliance / Other) · Urgency (Urgent / Today / This Week / FYI) · Status (Open / Drafted Reply / Answered / Waiting on Others / No Action) · Summary (2–3 lines) · Action items (→ To-Dos) · Reply draft · Answered date
Raw email text: store a summary rather than the full text, to keep resident information out of Notion (assumption, confirm)

### 5.16 Templates
Name (title) · Channel (Email / Text) · Category (Applicant / Resident / Vendor / Corporate / Collections / Move-in / Renewal) · Trigger phrases (e.g. "hasn't finished Two Dots", "small balance") · Subject · Body with placeholders ({first_name}, {unit}, {property}, {date}) · Times used · Last used
Roxy to paste her current templates first: small balance letter, move-in outreach, Two Dots reminder

### 5.17 Daily Notes
Note (title, auto from first words) · Date/time · Type (Tour / Prospect / Resident / Vendor / Task / Issue / Other) · Property · Note text (as Roxy typed it) · Include in DAR (checkbox, default on)
Roxy dumps notes in Slack all day ("toured a 2x2 at HG, liked it, applying Fri") and Ruby files each one here.

### 5.18 DARs
Date (title) · Property coverage · Draft (text, first person in Roxy's voice) · Status (Drafted / Approved / Sent by Roxy) · Notes used (relation → Daily Notes)

### 5.19 Meetings & Voice Notes
Title · Date · With (relation → Contacts) · Audio file · Transcript · Summary · Decisions · Action items (→ To-Dos) · Consent noted (checkbox: everyone agreed to the recording, or this is Roxy's own recap)
Washington is an all-party consent state. Ruby asks "Did everyone agree to the recording, or is this your recap?" before she processes a file.

### 5.20 Vendors
Company (title) · Contact name · Trades (multi-select: Carpet/Flooring, Paint, Resurfacing, Cleaning, Junk Haul, Pest, Appliance, Locksmith, Towing, Plumbing, Electrical, HVAC, Landscaping, Other) · Phone · Email · Properties served · Approved (checkbox; Ruby only suggests approved vendors) · Preferred contact (Text / Email / Call) · Notes
Seed with known vendors: MFI, Sherwin Williams/painter, MODern Resurfacing, Elite Resurfacing, All Haul Junk Removal, 1 Stop Towing. Roxy to upload the full approved list.

### 5.21 Contacts
Name · Role · Org · Email · Phone · Receives DAR (checkbox) · Notes
Robin Matishak (Regional Asset Manager), Betsy, Barrett (Director), Sara Campbell (role TBD), housing authority housing specialist (TBD), Elevenevictions@montgomerypurdue.com, City of Renton (street parking)

### 5.22 Supply List
Item (title) · Property · For (Model Unit / Office) · Qty · Status (Needed / Purchased) · Store · Purchased date · P-card receipt in Key2Purchase (checkbox)

### 5.23 Leads (Phase 2)
Name/handle · Source (Facebook Marketplace / Walk-in / Other) · Property · Interest (floor plan, move date) · Status (New / Contacted / Tour Scheduled / Applied / Lost) · Next follow-up · Template used
Facebook Marketplace has no public API, so to start, Roxy pastes leads into Slack.

## 6. Slack design

Channel setup: DM with Ruby for everything, plus an optional #ruby-log channel where Ruby posts a record of every Notion change.

Plain-language intents Ruby must handle (examples, not commands):

| Roxy says | Ruby does |
|---|---|
| "C214 at Heritage Grove is vacant, needs paint and carpet" | Creates a card on the HG Make Ready board, finds approved paint and carpet vendors, drafts their messages, offers to schedule |
| "Pasted email: …" | Files it in Email Triage with topic, urgency and a summary; creates any To-Dos; offers a reply draft |
| "I have an applicant that hasn't finished Two Dots yet" | Retrieves the Two Dots template and fills in the placeholders |
| "Called B105 Maria, she wants $50 off, countering" | Logs the call and sets Renewal status to Counter Offer with the details |
| "Toured a 1x1 at Peak, she's applying tomorrow" | Files a Daily Note |
| "done with price sheets" | Marks today's Task Tracker item Done |
| "Add a weekly task: market survey every Monday" | Confirms task, cadence, property and due day, then saves to Recurring Tasks |
| "Show my weekly tasks" | Lists active Weekly recurring tasks |
| "Need paper towels and air freshener for the Peak model" | Adds both to the Supply List |
| [uploads audio file] | Asks about consent, transcribes, files the summary, decisions and To-Dos |
| "Schedule MFI Thursday 10am for C214" | Shows a draft calendar event; after Approve, creates it in Outlook and updates the Vendor Job |

Scheduled messages from Ruby:
- 7:00 AM: morning checklist (today's tasks by property, move-ins tomorrow, move-outs today, SODA deadlines, overdue items, renewals to call, open urgent emails, today's calendar)
- 4:00 PM: DAR prompt ("Anything to add before I draft?"), then the DAR draft in Slack for Roxy to copy
- Reminders: based on each task's due time and reminder offset
- Overdue sweep: once a day, flags anything past due
- Monthly, on the 7th: starts the delinquency cycle and asks Roxy to paste the unpaid list

## 7. Outlook (Microsoft Graph)

- Scope: calendar only (Calendars.ReadWrite). No mail access, since emails are pasted into Slack.
- Setup: app registration in Microsoft Entra ID (Microsoft 365 Business tenant for roxyadams.com), signed in once as hello@roxyadams.com
- Reads: today's and tomorrow's events (for the morning checklist and tour-conflict check)
- Writes: vendor appointments, inspections and reminders, created only after Roxy clicks Approve. Event body includes unit, property and vendor phone.
- Conflict check: before proposing a time, Ruby checks the calendar for overlaps (daily task: "check tour schedule for conflicts")

## 8. Build phases (proposed)

1. **Foundation:** Notion page tree and all databases, Ruby's Brain page, Slack app, Railway deploy, basic chat that reads and writes Notion
2. **Daily engine:** Recurring Tasks → Task Tracker generator, 7 AM checklist, reminders, overdue sweep, "done" handling, add/change tasks by Slack
3. **Make Ready + Vendors + Outlook:** both boards, Vendor Jobs, vendor drafting, calendar approve-to-create
4. **Communication:** Email Triage, Templates, Daily Notes → DAR at 4 PM
5. **Residents:** Renewals + Call Log, Move-Ins/Move-Outs with SODA tracking, Work Orders, Delinquency Cycle, Inspections
6. **Voice + extras:** audio transcription, Meetings, Supply List, Leads (Phase 2), parking/storage notices

## 9. Still needed from Roxy (doesn't block the outline)

- 1–2 sample DARs (for Ruby's voice)
- Current templates (small balance letter, move-in outreach, Two Dots reminder, others)
- Full approved vendor list
- Betsy's and Barrett's full names and emails; Sara Campbell's role; housing specialist contact
- Unit list for both properties (a Yardi export would be ideal)
- Weekly and quarterly tasks after orientation
- Rapidsoft ads: which units, how often
- Company policy check: is it OK to paste work emails (with resident first names) into a personal Slack/AI tool?

## 10. Assumptions to confirm

- Proactive pings only between 7 AM and 6 PM, except for urgent items (Roxy can still message Ruby 24/7)
- Email Triage stores a summary, not the full pasted email
- Ruby creates the Make Ready card automatically when a move-out is logged
- Two separate Make Ready databases. The alternative is one database shown as two property boards: it looks the same and makes combined reporting easier.
- Transcription service: OpenAI Whisper API (~$0.006/min)
