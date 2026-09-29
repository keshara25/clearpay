import sqlite3
from scripts.phone_bridge import enqueue

def test_only_allowlisted_inbox_sms_queued_once():
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE outbox(event_id TEXT PRIMARY KEY,payload TEXT,delivered INTEGER DEFAULT 0)')
    row=dict(_id=1,address='DEMO-BANK',type='inbox',received='2026-09-29',body='Credit notification')
    rows=[row,{**row,'address':'FRIEND'},{**row,'type':'sent'}]
    assert enqueue(db,rows,'DEMO-BANK','phone1')==1
    assert enqueue(db,rows,'DEMO-BANK','phone1')==0
    assert db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==1
