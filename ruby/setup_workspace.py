"""One-time: create the 9 channels, pin 'How this channel works', add status line.
Run: python -m ruby.setup_workspace   (needs SLACK_BOT_TOKEN)."""
import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from .config import CHANNELS, EMOJI_KEY


def main():
    c = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    for name, (desc, how) in CHANNELS.items():
        try:
            r = c.conversations_create(name=name)
            cid = r["channel"]["id"]
        except SlackApiError as e:
            if e.response["error"] != "name_taken":
                raise
            cid = next(ch["id"] for ch in c.conversations_list(types="public_channel", limit=1000)["channels"] if ch["name"] == name)
            c.conversations_join(channel=cid)
        c.conversations_setPurpose(channel=cid, purpose=desc)
        msg = c.chat_postMessage(channel=cid, text=f"*How this channel works*\n{how}")
        try:
            c.pins_add(channel=cid, timestamp=msg["ts"])
        except SlackApiError:
            pass
        print("ready #" + name)
    roxy = os.environ.get("ROXY_SLACK_USER_ID")
    if roxy:
        dm = c.conversations_open(users=roxy)["channel"]["id"]
        m = c.chat_postMessage(channel=dm, text=EMOJI_KEY)
        c.pins_add(channel=dm, timestamp=m["ts"])


if __name__ == "__main__":
    main()
