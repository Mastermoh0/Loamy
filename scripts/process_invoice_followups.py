"""Supervise separately; only explicitly enabled plans are eligible for delivery."""
import argparse
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from enterprise_production import create_app

parser=argparse.ArgumentParser()
parser.add_argument('--once',action='store_true')
args=parser.parse_args()
app=create_app()
try:
    while True:
        result=app.state.run_due_followup()
        if args.once:break
        if not result['processed']:time.sleep(5)
except KeyboardInterrupt:pass
