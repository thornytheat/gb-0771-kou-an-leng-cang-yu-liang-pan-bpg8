from contextlib import closing
import json
from pathlib import Path
import sqlite3
from app.faults import DockFault
from app.seals import compact


class Receipts:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, stamp TEXT NOT NULL, raw TEXT NOT NULL, stages TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS handovers (receipt_id TEXT NOT NULL, record_key TEXT NOT NULL, stamp TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(receipt_id, record_key))')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def read(self, key):
        with closing(self.connect()) as db:
            row = db.execute('SELECT stamp,raw,stages FROM receipts WHERE id=?', (key,)).fetchone()
        if row is None:
            raise DockFault('NO_RECEIPT', '冷库档案不存在', 404)
        return dict(zip(('manifest','files','stages'), map(json.loads, row)))

    def insert(self, key, stamp, files, stages):
        with closing(self.connect()) as db, db:
            cursor = db.execute('INSERT OR IGNORE INTO receipts VALUES (?,?,?,?)',
                                (key, compact(stamp), compact(files), compact(stages)))
            inserted = cursor.rowcount == 1
        return self.read(key), not inserted

    def add_handover(self, receipt_id, record_key, stamp, payload):
        with closing(self.connect()) as db, db:
            cursor = db.execute('INSERT OR IGNORE INTO handovers VALUES (?,?,?,?)',
                                (receipt_id, record_key, compact(stamp), compact(payload)))
            inserted = cursor.rowcount == 1
        return self.handover_stamp(receipt_id, record_key), not inserted

    def handover_stamp(self, receipt_id, record_key):
        with closing(self.connect()) as db:
            row = db.execute('SELECT stamp FROM handovers WHERE receipt_id=? AND record_key=?',
                             (receipt_id, record_key)).fetchone()
        return json.loads(row[0]) if row else None

    def handovers(self, receipt_id):
        with closing(self.connect()) as db:
            rows = db.execute('SELECT payload FROM handovers WHERE receipt_id=? ORDER BY rowid',
                              (receipt_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def list(self):
        with closing(self.connect()) as db:
            return [json.loads(row[0]) for row in db.execute('SELECT stamp FROM receipts ORDER BY rowid DESC')]
