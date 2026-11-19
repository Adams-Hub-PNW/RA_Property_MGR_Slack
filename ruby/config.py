"""Central settings: schedule, channels, emoji map. Mirrors the Slack outline (Nov 18)."""
import os
from datetime import time
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")

# Ruby only starts conversations inside this window, Mon-Fri.
WORK_START = time(7, 0)
WORK_END = time(17, 30)
# Urgent exceptions may go out in this wider window, never overnight.
URGENT_START = time(6, 0)
URGENT_END = time(21, 0)

# (hour, minute) of each daily beat, Mon-Fri.
SCHEDULE = {
    "morning": (7, 0),
    "checkin_1": (11, 0),
    "checkin_2": (14, 0),
    "dar": (16, 0),
    "shutdown": (17, 0),
}
NEXT_CHECKIN_ORDER = ["morning", "checkin_1", "checkin_2", "dar", "shutdown"]

OVERWHELM_PAUSE_MIN = 60

# channel name -> (description, pinned "How this channel works")
CHANNELS = {
    "make-ready-vendors": ("Unit turns, vendor bids and appointments",
                           "Ruby posts one card per vacant unit and edits it as status changes. Roxy: just DM Ruby."),
    "residents": ("Renewals, move-ins, move-outs, work orders",
                  "Unit # and first name only, no dollar balances. Roxy: just DM Ruby."),
    "collections": ("Monthly delinquency cycle and POV packets",
                    "Cycle starts on the 7th. Unit # and first name only. Roxy: just DM Ruby."),
    "inspections": ("Monthly HappyCo, landscape, light and annual unit inspections",
                    "Monthly checklist per property. Roxy: just DM Ruby."),
    "inbox-emails": ("Triaged emails", "One line per email. Roxy: paste emails in the DM."),
    "dar-notes": ("Daily notes and the DAR", "Filed notes plus the 4 PM DAR draft."),
    "supplies": ("Shopping list for model units and offices", "Grouped by property and store."),
    "wins": ("Proof of progress", "Each finished item, the 5 PM summary, Friday recap."),
    "ruby-log": ("Audit trail", "One line per Notion/calendar change, with links."),
}

# Emoji reaction name (Slack, no colons) -> action key
REACTIONS = {
    "white_check_mark": "done",
    "alarm_clock": "tomorrow",
    "pushpin": "pin",
    "repeat": "later",
    "rotating_light": "urgent",
    "x": "skip",
    "eyes": "in_progress",
}

EMOJI_KEY = (
    "*Emoji key* — react on any Ruby message:\n"
    ":white_check_mark: done · :alarm_clock: tomorrow · :pushpin: make it Top 3 · "
    ":repeat: later today · :rotating_light: urgent · :x: not needed · :eyes: I'm on it"
)

OVERWHELM_PHRASES = ("i'm overwhelmed", "im overwhelmed", "overwhelmed", "too much", "help")

ROXY_USER_ID = os.environ.get("ROXY_SLACK_USER_ID", "")
STATE_PATH = os.environ.get("RUBY_STATE_PATH", "ruby_state.json")
MODEL = os.environ.get("RUBY_MODEL", "claude-sonnet-5-5")
