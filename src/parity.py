"""Parity harness (condition A5, Section 8.1) + metrics (Table 6).

Compares A4 (contract service) vs A5 (manifest stored as data) on the same
query suite: membership divergence must be zero; answers evaluated against
generator-defined gold, not by text identity.
"""
import json
import os


def evaluate_run(run, query):
    """Gold-based evaluation of a single run."""
    res = {"q_id": run["q_id"], "ok": None, "detail": ""}
    qtype = query["type"]
    if "gold_rev" in query:
        got = set(run["context_revs"])
        exp = {query["gold_rev"]}
        res["ok"] = got == exp
        res["detail"] = f"expected {sorted(exp)} got {sorted(got)}"
    elif "gold_revs" in query:
        got = {c for c in run["context_revs"]
               if not c.startswith("E-")}
        exp = set(query["gold_revs"])
        res["ok"] = got == exp or exp <= got
        res["detail"] = f"expected {sorted(exp)} got {sorted(got)}"
    elif "gold_verdict" in query:
        res["ok"] = query["gold_verdict"] in run["answer"]
        res["detail"] = f"expected verdict {query['gold_verdict']}"
    elif "gold_answer" in query:
        res["ok"] = run["answer"] == query["gold_answer"]
        res["detail"] = f"expected '{query['gold_answer']}'"
    elif "gold_flag" in query:
        res["ok"] = query["gold_flag"] in run["flags"]
        res["detail"] = f"expected flag {query['gold_flag']}"
    return res


def metrics(runs, queries):
    """Table 6 metrics computed over a run set."""
    qmap = {q["q_id"]: q for q in queries}
    n_mem_viol = sum(1 for r in runs if "MEMBERSHIP_VIOLATION" in r["flags"])
    n_avail_viol = 0  # violations are prevented by filtering; counted in checks
    supported, material = 0, 0
    abstain_ok, abstain_cases = 0, 0
    for r in runs:
        for c in r["claims"]:
            if c["evidence_type"] in ("documented", "derived"):
                material += 1
                if (c.get("verification") or {}).get("semantic") == "supported":
                    supported += 1
        q = qmap[r["q_id"]]
        if q["type"] in ("record_query", "availability"):
            abstain_cases += 1
            if evaluate_run(r, q)["ok"]:
                abstain_ok += 1
    return {
        "fact_correctness": round(
            sum(1 for r in runs if evaluate_run(r, qmap[r["q_id"]])["ok"])
            / len(runs), 3),
        "membership_violations_flagged": n_mem_viol,
        "evidential_support": round(supported / material, 3) if material
        else None,
        "correct_abstention": round(abstain_ok / abstain_cases, 3)
        if abstain_cases else None,
        "runs": len(runs),
    }


def compare(a4_runs, a5_runs, queries):
    """Core parity check: admissible context and verdicts must match."""
    qmap = {q["q_id"]: q for q in queries}
    a5 = {r["q_id"]: r for r in a5_runs}
    rows, divergent = [], 0
    for r4 in a4_runs:
        r5 = a5[r4["q_id"]]
        same_ctx = set(r4["context_revs"]) == set(r5["context_revs"])
        same_eval = evaluate_run(r4, qmap[r4["q_id"]])["ok"] == \
            evaluate_run(r5, qmap[r4["q_id"]])["ok"]
        if not (same_ctx and same_eval):
            divergent += 1
        rows.append({"q_id": r4["q_id"], "same_context": same_ctx,
                     "same_eval": same_eval})
    return {"queries": len(a4_runs), "divergent": divergent,
            "parity": divergent == 0, "detail": rows}


def write_report(path, parity, m4, m5, notes=""):
    rep = {"parity": parity, "metrics_A4": m4, "metrics_A5": m5,
           "notes": notes}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    return rep
