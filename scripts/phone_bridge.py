"""Read a merchant Android inbox via Termux:API; queue and sign bank SMS only.

Use --inbox-json for a fixture dry run. Physical Android integration is not tested here.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

def enqueue(db, rows, sender, device):
    added = 0
    for row in rows:
        address = row.get('address', row.get('number'))
        if address != sender or row.get('type') != 'inbox' or not row.get('body'):
            continue
        # ID survives network retries, including a lost HTTP response after server commit.
        identity = json.dumps([device,row.get('_id'),row.get('received'),address,row['body']])
        event = hashlib.sha256(identity.encode()).hexdigest()
        payload = json.dumps({'event_id':event,'sender':address,'text':row['body']},separators=(',',':'))
        cursor = db.execute('INSERT OR IGNORE INTO outbox(event_id,payload) VALUES(?,?)',(event,payload))
        added += cursor.rowcount
    db.commit()
    return added

def deliver(db, url, secret):
    sent = 0
    for event,payload in db.execute('SELECT event_id,payload FROM outbox WHERE delivered=0').fetchall():
        raw=payload.encode(); stamp=str(int(time.time()))
        sig=hmac.new(secret.encode(),stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        req=urllib.request.Request(url.rstrip('/')+'/api/gateway/sms',data=raw,
            headers={'Content-Type':'application/json','X-Timestamp':stamp,'X-Signature':sig},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=20) as response:
                if response.status != 200:
                    continue
            db.execute('UPDATE outbox SET delivered=1 WHERE event_id=?',(event,)); db.commit(); sent+=1
        except (urllib.error.URLError,TimeoutError):
            # Keep the durable event for retry; never log private message bodies.
            print('Gateway unavailable or rejected an event; retained for retry.')
            break
    return sent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8000')
    parser.add_argument('--sender',required=True)
    parser.add_argument('--device',default='merchant-phone-1')
    parser.add_argument('--queue',default='data/phone-outbox.sqlite3')
    parser.add_argument('--inbox-json',help='Read a Termux-format JSON fixture instead of the phone')
    parser.add_argument('--dry-run',action='store_true',help='Queue only; do not transmit')
    parser.add_argument('--watch',action='store_true')
    args=parser.parse_args()
    parsed=urlparse(args.url)
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1')):
        raise SystemExit('Use HTTPS outside localhost')
    secret=os.getenv('SMS_SECRET','')
    if not args.dry_run and len(secret)<32:
        raise SystemExit('Set SMS_SECRET with at least 32 characters')
    Path(args.queue).parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(args.queue)
    db.execute('CREATE TABLE IF NOT EXISTS outbox(event_id TEXT PRIMARY KEY,payload TEXT NOT NULL,delivered INTEGER NOT NULL DEFAULT 0)')
    while True:
        if args.inbox_json:
            rows=json.loads(Path(args.inbox_json).read_text(encoding='utf-8'))
        else:
            result=subprocess.run(['termux-sms-list','-t','inbox','-l','1000'],capture_output=True,text=True,check=True,timeout=30)
            rows=json.loads(result.stdout)
        added=enqueue(db,rows,args.sender,args.device)
        sent=0 if args.dry_run else deliver(db,args.url,secret)
        print(f'Queued {added}; delivered {sent}; pending {db.execute("SELECT COUNT(*) FROM outbox WHERE delivered=0").fetchone()[0]}')
        if not args.watch:
            break
        time.sleep(20)
    db.close()

if __name__=='__main__':
    main()
