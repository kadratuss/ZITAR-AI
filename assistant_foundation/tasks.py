"""Isolated durable task prototype; two deterministic tools, no model authority."""
import json
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from assistant_foundation.exact_tools import calculate, validate_json


class Tasks:
    def __init__(self, workspace):
        root = Path(workspace).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'assistant_tasks.sqlite3'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, tool TEXT, input TEXT, state TEXT, result TEXT, error TEXT)')

    def submit(self, tool, arguments):
        if tool not in ('calculate', 'validate_json') or not isinstance(arguments, dict):
            raise ValueError('INVALID_TASK')
        payload = json.dumps(arguments, allow_nan=False)
        if len(payload) > 100000: raise ValueError('TASK_TOO_LARGE')
        identity = uuid.uuid4().hex
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?)',
                       (identity, tool, payload, 'QUEUED', None, None))
        return identity

    def get(self, identity):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT * FROM tasks WHERE id=?', (identity,)).fetchone()
        if row is None: raise KeyError(identity)
        return dict(id=row[0], tool=row[1], arguments=json.loads(row[2]),
                    state=row[3], result=json.loads(row[4]) if row[4] else None,
                    error=row[5])

    def execute(self, identity):
        # Transaction serializes execution. These tools are bounded and have no
        # external side effects; interruption rolls back the terminal state.
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT tool,input,state FROM tasks WHERE id=?', (identity,)).fetchone()
            if row is None: raise KeyError(identity)
            if row[2] == 'QUEUED':
                try:
                    function = {'calculate': calculate, 'validate_json': validate_json}[row[0]]
                    result = function(**json.loads(row[1]))
                    db.execute('UPDATE tasks SET state=?,result=? WHERE id=?',
                               ('SUCCEEDED', json.dumps(result, allow_nan=False), identity))
                except (ValueError, TypeError, ArithmeticError) as exc:
                    db.execute('UPDATE tasks SET state=?,error=? WHERE id=?',
                               ('FAILED', type(exc).__name__, identity))
        return self.get(identity)
