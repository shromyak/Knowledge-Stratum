"""One-command reproduction: corpora -> checks -> A4/A5 runs -> parity."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import corpus_req
import corpus_sv
from asof_store import load_strata_to_db, verify_db_manifest
from contract import check_stratum
from engine import run_suite
from model import Store, latest_asof, read_jsonl
from parity import compare, metrics, write_report

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def process(name, store, runs_dir, checks_dir):
    queries = read_jsonl(os.path.join(store.root, "queries.jsonl"))
    for s in store.strata():
        rep = check_stratum(store, s)
        out = os.path.join(checks_dir, f"{s['stratum_id']}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
        print(f"  check {s['stratum_id']}: ok={rep['ok']}")
        if not rep["ok"]:
            for c in rep["checks"]:
                if not c["ok"]:
                    print("    FAIL", c["check"], c["detail"])

    db = os.path.join(store.root, "a5.db")
    load_strata_to_db(store, db)
    for s in store.strata():
        assert verify_db_manifest(store, db, s["stratum_id"])
    print(f"  {name}: A5 manifest hash verified")

    a4 = run_suite(store, queries, "A4",
                   os.path.join(runs_dir, f"{name}_a4.jsonl"))
    a5 = run_suite(store, queries, "A5",
                   os.path.join(runs_dir, f"{name}_a5.jsonl"))
    parity = compare(a4, a5, queries)
    rep = write_report(
        os.path.join(checks_dir, f"{name}_parity_report.json"),
        parity, metrics(a4, queries), metrics(a5, queries),
        notes=("A5-lite carrier: manifest rows in SQLite (git-commit "
               "analogue of DVC/LakeFS per Section 2.3). Parity expected "
               "for membership; divergence in cost only."))
    print(f"  {name}: parity={parity['parity']} "
          f"divergent={parity['divergent']} "
          f"fact={rep['metrics_A4']['fact_correctness']}")
    return rep


def main():
    runs_dir = os.path.join(BASE, "runs")
    checks_dir = os.path.join(BASE, "checks")
    os.makedirs(runs_dir, exist_ok=True)
    os.makedirs(checks_dir, exist_ok=True)

    print("== req corpus ==")
    req = process("req", Store(corpus_req.generate()), runs_dir, checks_dir)

    print("== sv corpus (Strategy Validator) ==")
    sv = process("sv", Store(corpus_sv.generate()), runs_dir, checks_dir)

    # counterexample assertion (Section 3.2)
    store = Store(os.path.join(BASE, "data", "req"))
    assert latest_asof(store.revisions(), "XA", 5)["rev_id"] == "XA-rev2"
    print("counterexample confirmed: latest-as-of(T=5) -> XA-rev2, "
          "but B_counter pins XA-rev1")

    summary = {"req": req, "sv": sv}
    with open(os.path.join(checks_dir, "summary.json"), "w",
              encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("\nDONE. journals:", runs_dir, "| checks:", checks_dir)


if __name__ == "__main__":
    main()
