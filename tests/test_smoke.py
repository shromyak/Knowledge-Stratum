"""Dependency-free smoke tests (runnable as `python3 tests/test_smoke.py`,
also collectable by pytest if installed)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import corpus_req
from asof_store import load_strata_to_db, verify_db_manifest
from contract import admissible_members, check_stratum
from engine import run_suite
from model import Store, latest_asof, read_jsonl
from parity import compare, metrics


def _env():
    root = corpus_req.generate()
    store = Store(root)
    queries = read_jsonl(os.path.join(root, "queries.jsonl"))
    load_strata_to_db(store, os.path.join(root, "a5.db"))
    return store, queries


def test_contracts_pass():
    store, _ = _env()
    for s in store.strata():
        assert check_stratum(store, s)["ok"], s["stratum_id"]


def test_fabricated_violation_rejected():
    store, _ = _env()
    bad = dict(store.stratum("B1"))
    bad["stratum_id"] = "BAD"
    bad["members_manifest"] = list(bad["members_manifest"]) + [
        {"rev_id": "NOPE-rev9", "role": "member"}]
    rep = check_stratum(store, bad)
    assert not rep["ok"]
    assert any(c["check"] == "members_exist" and not c["ok"]
               for c in rep["checks"])


def test_counterexample_not_recoverable_by_asof():
    store, _ = _env()
    # approved stratum {a1, b1} at t=5: no latest-as-of restores it
    assert latest_asof(store.revisions(), "XA", 5)["rev_id"] == "XA-rev2"
    members, _ = admissible_members(store, store.stratum("B_counter"))
    assert members == {"XA-rev1", "XB-rev1"}


def test_a5_manifest_parity():
    store, _ = _env()
    db = os.path.join(store.root, "a5.db")
    for s in store.strata():
        assert verify_db_manifest(store, db, s["stratum_id"])


def test_parity_runs():
    store, queries = _env()
    with tempfile.TemporaryDirectory() as out:
        a4 = run_suite(store, queries, "A4",
                       os.path.join(out, "a4.jsonl"))
        a5 = run_suite(store, queries, "A5",
                       os.path.join(out, "a5.jsonl"))
    rep = compare(a4, a5, queries)
    assert rep["parity"], rep["detail"]
    m = metrics(a4, queries)
    assert m["fact_correctness"] == 1.0
    assert m["membership_violations_flagged"] == 1


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print(f"{len(fns)} tests passed")
