"""
The app's memory: a small SQLite database file (runs.db).
Every processed invoice is saved here. It powers:
  - the dashboard (history of all runs)
  - the duplicate check (have we seen this invoice before?)
  - the split-PO check (how much has already been billed on this PO?)
"""
import json
import sqlite3
from datetime import datetime

from pipeline.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT,
    filename            TEXT,
    sha256              TEXT,
    decision            TEXT,     -- APPROVE / HOLD / REJECT / ERROR / PENDING
    vendor_id           TEXT,
    vendor_name         TEXT,
    invoice_number      TEXT,
    invoice_number_norm TEXT,     -- cleaned version used for duplicate checks
    invoice_date        TEXT,
    po_number           TEXT,
    po_inferred         INTEGER,  -- 1 if the PO was guessed, not printed on the invoice
    subtotal            REAL,
    total               REAL,
    reasons             TEXT,     -- JSON list of reasons for the decision
    record              TEXT,     -- JSON with everything: fields, checks, timeline
    review_status       TEXT,     -- set when a human reviews a HOLD
    review_note         TEXT,
    reviewed_at         TEXT
);
"""


def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def save_run(row):
    """Insert a run (a dict of column → value). Returns the new run id."""
    row = dict(row)
    row.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
    for k in ("reasons", "record"):
        if k in row and not isinstance(row[k], str):
            row[k] = json.dumps(row[k], default=str)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    with _conn() as con:
        cur = con.execute(f"INSERT INTO runs ({cols}) VALUES ({marks})", list(row.values()))
        return cur.lastrowid


def update_run(run_id, **changes):
    for k in ("reasons", "record"):
        if k in changes and not isinstance(changes[k], str):
            changes[k] = json.dumps(changes[k], default=str)
    sets = ", ".join(f"{k} = ?" for k in changes)
    with _conn() as con:
        con.execute(f"UPDATE runs SET {sets} WHERE id = ?", [*changes.values(), run_id])


def all_runs():
    with _conn() as con:
        rows = con.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["reasons"] = json.loads(d["reasons"] or "[]")
        d["record"] = json.loads(d["record"] or "{}")
        out.append(d)
    return out


def get_run(run_id):
    return next((r for r in all_runs() if r["id"] == run_id), None)


def billed_on_po(po_number):
    """Total (pre-tax) already approved by this app against a PO.
    A HOLD only counts once a human has approved it."""
    with _conn() as con:
        row = con.execute(
            """SELECT COALESCE(SUM(subtotal), 0) FROM runs
               WHERE po_number = ?
                 AND (decision = 'APPROVE' OR review_status = 'APPROVED')""",
            (po_number,),
        ).fetchone()
    return float(row[0])


def reset():
    """Delete all history (used by the 'Reset demo' button)."""
    with _conn() as con:
        con.execute("DELETE FROM runs")
        con.execute("DELETE FROM sqlite_sequence WHERE name = 'runs'")
