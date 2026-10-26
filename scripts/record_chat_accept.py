#!/usr/bin/env python3
"""Record a chat Accept, Reject, or alternative in the responses store.

A chat Accept and a tracker Accept both count. Every answer must still be recorded on the tracker.
Writes .cache/responses-chat.json and .cache/responses.json in the same shape as a tracker tap
(one chat entry per Decision id), and the responses KV value when CLOUDFLARE_API_TOKEN and the
responses ids in sync config are set. Never edits data.json. Run ./publish.sh afterwards.

Usage: record_chat_accept.py --id dec-... [--value accepted|rejected|comment] [--comment '...']
       [--at 2026-10-26T14:18:00Z] [--ref 'chat <message id>'] [--email ...] [--no-kv]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flightdeck.sync import main_record_chat_accept

if __name__ == "__main__":
    sys.exit(main_record_chat_accept())
