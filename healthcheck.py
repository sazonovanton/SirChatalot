# Container HEALTHCHECK entry point: exits 0 while the bot is polling Telegram.
# Tunable via SIRCHATALOT_HEARTBEAT (file path) and SIRCHATALOT_HEARTBEAT_MAX_AGE
# (seconds; keep it a few times telegram.network.heartbeat_seconds).
import os
import sys

from sirchatalot.health import HEARTBEAT_PATH, check_heartbeat

if __name__ == '__main__':
    path = os.environ.get('SIRCHATALOT_HEARTBEAT', HEARTBEAT_PATH)
    max_age = float(os.environ.get('SIRCHATALOT_HEARTBEAT_MAX_AGE', '300'))
    code, message = check_heartbeat(path, max_age)
    print(message)
    sys.exit(code)
