"""Generate a synthetic receipt from an order's details for a live upload demonstration."""
import argparse
from pathlib import Path
import sys
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.demo import render_slip, sms_text

p=argparse.ArgumentParser()
p.add_argument('--code',required=True,help='Copy the server-issued PAY- code from Orders')
p.add_argument('--account',default='1234567890')
p.add_argument('--amount-minor',type=int,default=2500000)
p.add_argument('--reference',default='TXDEMO123')
p.add_argument('--output',default='samples/upload-demo.png')
args=p.parse_args()
fields=dict(amount_minor=args.amount_minor,account=args.account,reference=args.reference,
            paid_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),order_code=args.code)
path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
path.write_bytes(render_slip(fields))
path.with_suffix('.sms.txt').write_text(sms_text(fields),encoding='utf-8')
print(f'Synthetic image: {path}\nMatching demo SMS: {path.with_suffix(".sms.txt")}')
