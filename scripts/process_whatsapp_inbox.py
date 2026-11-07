"""Run as a separately supervised production worker; no outbound messages are sent."""
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from enterprise_production import create_app

parser = argparse.ArgumentParser()
parser.add_argument('--once', action='store_true', help='Process at most one queued receipt and exit')
args = parser.parse_args()
app = create_app()
if not app.state.whatsapp_enabled:
    raise RuntimeError('Configure the approved WhatsApp integration before starting its worker')
try:
    while True:
        processed = app.state.process_whatsapp_message()
        if args.once:
            break
        if not processed:
            time.sleep(5)
except KeyboardInterrupt:
    pass
