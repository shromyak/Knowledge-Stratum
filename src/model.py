"""Core objects of the knowledge-stratum schema (Table 3 of the article).

Storage layout:
  <root>/content/<sha256>.txt     -- immutable content-addressed blobs
  <root>/entities.jsonl
  <root>/revisions.jsonl
  <root>/edges.jsonl
  <root>/strata.jsonl             -- stratum objects (manifest + contract rev)
  <root>/contracts.jsonl
"""
import hashlib
import json
import os


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class Store:
    """Revision store: immutable blobs + revision/edge metadata."""

    def __init__(self, root):
        self.root = root
        self.content_dir = os.path.join(root, "content")
        os.makedirs(self.content_dir, exist_ok=True)

    def add_content(self, text: str) -> dict:
        h = sha256_text(text)
        path = os.path.join(self.content_dir, h + ".txt")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return {"content_ref": path, "content_hash": h}

    def read_content(self, content_ref: str) -> str:
        with open(content_ref, encoding="utf-8") as f:
            return f.read()

    def revisions(self):
        return read_jsonl(os.path.join(self.root, "revisions.jsonl"))

    def revision(self, rev_id):
        for r in self.revisions():
            if r["rev_id"] == rev_id:
                return r
        return None

    def edges(self):
        return read_jsonl(os.path.join(self.root, "edges.jsonl"))

    def strata(self):
        return read_jsonl(os.path.join(self.root, "strata.jsonl"))

    def stratum(self, stratum_id):
        for s in self.strata():
            if s["stratum_id"] == stratum_id:
                return s
        return None

    def contracts(self):
        return read_jsonl(os.path.join(self.root, "contracts.jsonl"))

    def contract(self, contract_rev):
        for c in self.contracts():
            if c["contract_rev"] == contract_rev:
                return c
        return None


def latest_asof(revisions, entity_id, t):
    """Latest revision of entity visible in system time at t (pure temporal rule)."""
    best = None
    for r in revisions:
        if r["entity_id"] != entity_id:
            continue
        system_to = r.get("system_to")
        if system_to is None:
            system_to = float("inf")
        if r.get("system_from", 0) <= t and t < system_to:
            if best is None or r["system_from"] > best["system_from"]:
                best = r
    return best
