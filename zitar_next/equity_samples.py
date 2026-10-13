"""Minute-sampled account equity, separate metrics DB; never edits accounts."""
import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path

def record(base,state):
 ts=int(state['heartbeat_ms']);minute=ts//60000
 with closing(sqlite3.connect(Path(base)/'zitar_equity_samples_v1.sqlite3',timeout=5)) as db,db:
  db.execute('CREATE TABLE IF NOT EXISTS samples(account TEXT, started INTEGER, minute INTEGER, timestamp INTEGER, equity TEXT, health TEXT, PRIMARY KEY(account,started,minute))')
  for key,b in state['books'].items():
   if b.get('retired_ms'):continue
   value=Decimal(b['equity'])
   if not value.is_finite():continue
   db.execute('INSERT OR IGNORE INTO samples VALUES(?,?,?,?,?,?)',(key,b['started_ms'],minute,ts,str(value),b.get('health','UNKNOWN')))
  db.execute('DELETE FROM samples WHERE minute<?',(minute-60*24*35,))
