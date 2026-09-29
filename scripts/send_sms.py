"""Reference merchant-phone gateway sender. Send JSON over HTTPS in a real integration."""
import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.request
import uuid

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://127.0.0.1:8000")
p.add_argument("--text", required=True)
p.add_argument("--sender", default="DEMO-BANK")
p.add_argument("--event-id", default=None, help="Persist this ID and reuse it for retries")
args = p.parse_args()
secret = os.environ.get("SMS_SECRET")
if not secret:
    raise SystemExit("Set SMS_SECRET to the server's gateway secret")
payload = json.dumps({"event_id": args.event_id or str(uuid.uuid4()), "sender": args.sender, "text": args.text}, separators=(",", ":")).encode()
stamp = str(int(time.time()))
signature = hmac.new(secret.encode(), stamp.encode()+b"."+payload, hashlib.sha256).hexdigest()
request = urllib.request.Request(args.url.rstrip("/")+"/api/gateway/sms", data=payload,
    headers={"Content-Type":"application/json", "X-Timestamp":stamp, "X-Signature":signature}, method="POST")
with urllib.request.urlopen(request, timeout=20) as response:
    print(response.read().decode())
