"""A5-lite: stratum manifest stored as data in a temporal table (SQLite).

Emulates 'manifest as records' in a bitemporal store (condition A5):
membership is recovered by querying rows, not derived from timestamps.
"""
import os
import sqlite3

from model import sha256_text

SCHEMA = """
CREATE TABLE IF NOT EXISTS stratum_manifest (
    stratum_id  TEXT NOT NULL,
    rev_id      TEXT NOT NULL,
    role        TEXT,
    system_from INTEGER NOT NULL,
    system_to   INTEGER,
    PRIMARY KEY (stratum_id, rev_id, system_from)
);
CREATE TABLE IF NOT EXISTS stratum_meta (
    stratum_id   TEXT PRIMARY KEY,
    contract_rev TEXT,
    members_hash TEXT,
    tau          INTEGER
);
"""


def load_strata_to_db(store, db_path):
    """Persist each stratum's manifest as rows (the A5 carrier)."""
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    for s in store.strata():
        tau = s["approval"]["tau"]
        for m in s["members_manifest"]:
            con.execute(
                "INSERT OR REPLACE INTO stratum_manifest"
                " (stratum_id, rev_id, role, system_from) VALUES (?,?,?,?)",
                (s["stratum_id"], m["rev_id"], m.get("role"), tau))
        con.execute(
            "INSERT OR REPLACE INTO stratum_meta VALUES (?,?,?,?)",
            (s["stratum_id"], s["contract_rev"], s["members_hash"], tau))
    con.commit()
    con.close()


def members_from_db(db_path, stratum_id):
    """Recover membership from stored manifest rows (as-of-safe)."""
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT rev_id FROM stratum_manifest WHERE stratum_id=?",
        (stratum_id,)).fetchall()
    con.close()
    return {r[0] for r in rows}


def manifest_hash_from_db(db_path, stratum_id):
    con = sqlite3.connect(db_path)
    row = con.execute(
        "SELECT members_hash FROM stratum_meta WHERE stratum_id=?",
        (stratum_id,)).fetchone()
    con.close()
    return row[0] if row else None


def verify_db_manifest(store, db_path, stratum_id):
    """Recompute the membership hash from DB rows and compare with stored."""
    members = members_from_db(db_path, stratum_id)
    recomputed = sha256_text("|".join(sorted(members)))
    return recomputed == manifest_hash_from_db(db_path, stratum_id)
