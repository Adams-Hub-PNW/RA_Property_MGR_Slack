import logging, os
from slack_bolt.adapter.socket_mode import SocketModeHandler
from . import app as appmod, scheduler

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    bolt, ruby = appmod.build()
    scheduler.build(ruby).start()
    SocketModeHandler(bolt, os.environ["SLACK_APP_TOKEN"]).start()
