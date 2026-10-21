"""Synthetic requirements corpus (Scenario Req, Section 8.3 of the article).

Generates deterministically:
  - requirements R-1..R-6, architecture elements A-1..A-5, tests T-1..T-8
  - two strata B1 / B2 differing in requirement text, edge direction, test set
  - the Section 3.2 counterexample: a1 (t=1), a2 (t=3), b1 (t=4),
    stratum B_counter = {a1, b1} approved at t=5 -> no latest-as-of restores it
  - query suite + gold answers (generator-defined, not hand-annotated)
"""
import os
import shutil

from model import Store, sha256_text, write_jsonl

ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "req")


def make_revision(store, entity_id, rev_id, text, system_from,
                  valid_from, available_at=None, valid_to=None):
    ref = store.add_content(text)
    return {
        "rev_id": rev_id, "entity_id": entity_id,
        "content_ref": ref["content_ref"], "content_hash": ref["content_hash"],
        "valid_from": valid_from, "valid_to": valid_to,
        "available_at": available_at,
        "system_from": system_from, "system_to": None,
        "source_ref": f"synthetic://req/{rev_id}",
    }


def make_edge(store, edge_id, edge_rev_id, src_rev, dst_rev, etype,
              system_from):
    ref = store.add_content(f"{edge_id}:{etype}:{src_rev}->{dst_rev}")
    return {
        "edge_id": edge_id, "edge_rev_id": edge_rev_id,
        "src_rev": src_rev, "dst_rev": dst_rev, "type": etype,
        "content_ref": ref["content_ref"], "content_hash": ref["content_hash"],
        "valid_from": system_from, "valid_to": None,
        "available_at": system_from,
        "system_from": system_from, "system_to": None,
    }


def generate():
    root = os.path.abspath(ROOT)
    if os.path.exists(root):
        shutil.rmtree(root)
    store = Store(root)

    entities, revisions, edges = [], [], []

    def ent(eid, etype):
        entities.append({"entity_id": eid, "type": etype})

    # ---- requirements: R-3 gets a second revision (the B1/B2 difference)
    req_text = {}
    for i in range(1, 7):
        eid = f"R-{i}"
        ent(eid, "requirement")
        t1 = (f"REQ {eid} rev1: the system shall maintain consistency "
              f"of configuration item {i} across releases.")
        req_text[f"{eid}-rev1"] = t1
        revisions.append(make_revision(store, eid, f"{eid}-rev1", t1,
                                       system_from=1, valid_from=1,
                                       available_at=1))
    t_r3v2 = ("REQ R-3 rev2: the system shall maintain consistency of "
              "configuration item 3 across releases AND expose an audit "
              "interface for baseline reconstruction.")
    req_text["R-3-rev2"] = t_r3v2
    revisions.append(make_revision(store, "R-3", "R-3-rev2", t_r3v2,
                                   system_from=4, valid_from=4,
                                   available_at=4))

    # ---- architecture elements
    for i in range(1, 6):
        eid = f"A-{i}"
        ent(eid, "arch_element")
        txt = f"ARCH {eid}: component implementing requirement R-{i}."
        revisions.append(make_revision(store, eid, f"{eid}-rev1", txt,
                                       system_from=1, valid_from=1,
                                       available_at=1))

    # ---- tests: T-8 exists only in B2 (added at t=4)
    for i in range(1, 9):
        eid = f"T-{i}"
        ent(eid, "test")
        txt = f"TEST {eid}: verification procedure for requirement R-{i % 6 + 1}."
        t = 4 if i == 8 else 1
        revisions.append(make_revision(store, eid, f"{eid}-rev1", txt,
                                       system_from=t, valid_from=t,
                                       available_at=t))

    # ---- edges: A-i satisfies R-i; T-i verifies R-(i%6+1)
    # change control: revising R-3 propagates to the edges that end at it
    for i in range(1, 6):
        eid = f"E-sat-{i}"
        ent(eid, "edge")
        edges.append(make_edge(store, eid, f"{eid}-rev1",
                               f"A-{i}-rev1", f"R-{i}-rev1", "satisfies", 1))
        if i == 3:
            edges.append(make_edge(store, eid, f"{eid}-rev2",
                                   "A-3-rev1", "R-3-rev2", "satisfies", 4))
    for i in range(1, 9):
        eid = f"E-ver-{i}"
        ent(eid, "edge")
        edges.append(make_edge(store, eid, f"{eid}-rev1",
                               f"T-{i}-rev1", f"R-{i % 6 + 1}-rev1",
                               "verifies", 1))
        # B2 differences: T-8 verifies R-3-rev2; T-2's edge re-targeted
        if i == 3:
            edges.append(make_edge(store, eid, f"{eid}-rev2",
                                   "T-8-rev1", "R-3-rev2", "verifies", 4))
        if i == 2:
            edges.append(make_edge(store, eid, f"{eid}-rev2",
                                   "T-2-rev1", "R-3-rev2", "verifies", 4))

    # ---- Section 3.2 counterexample: a1(t=1), a2(t=3), b1(t=4), B at t=5
    for eid in ("XA", "XB"):
        ent(eid, "document")
    revisions.append(make_revision(store, "XA", "XA-rev1",
                                   "DOC XA rev1: original analysis basis.",
                                   system_from=1, valid_from=1,
                                   available_at=1))
    revisions.append(make_revision(store, "XA", "XA-rev2",
                                   "DOC XA rev2: revised analysis basis.",
                                   system_from=3, valid_from=3,
                                   available_at=3))
    revisions.append(make_revision(store, "XB", "XB-rev1",
                                   "DOC XB rev1: supplementary evidence.",
                                   system_from=4, valid_from=4,
                                   available_at=4))

    # ---- contract
    contract = {
        "contract_rev": "C-req-1",
        "domain": "synthetic requirements project",
        "description": "Contract for the Req scenario strata.",
        "historicity_mode": "as_available_at_T",
        "member_types": ["requirement", "arch_element", "test", "edge",
                         "document"],
        "versioning_policy": {"revisions": "immutable",
                              "selection": "pinned"},
        "external_deps": [],
        "temporal_constraints": {"max_available_at": None},
        "contradiction_rules": {
            "allow_multiple_revisions_per_entity": False,
            "require_explicit_roles": True, "mark_conflicts": True},
        "consistency_checks": ["members_exist", "hash_integrity",
                               "member_types", "edge_endpoints",
                               "temporal_constraints",
                               "contradiction_rules"],
        "approval": {"approver_ref": "synthetic-generator",
                     "decision_ref": "gen://approval/C-req-1"},
    }

    def manifest(members):
        joined = "|".join(sorted(m["rev_id"] for m in members))
        return {"members_manifest": members, "members_hash":
                sha256_text(joined)}

    def stratum(sid, rev_ids, tau, parent=None):
        members = [{"rev_id": r, "role": "member"} for r in rev_ids]
        s = {"stratum_id": sid, "contract_rev": "C-req-1",
             "approval": {"approver_ref": "synthetic-generator",
                          "decision_ref": f"gen://approval/{sid}",
                          "tau": tau},
             "parent_ref": parent}
        s.update(manifest(members))
        return s

    base_members = (
        [f"R-{i}-rev1" for i in range(1, 7)]
        + [f"A-{i}-rev1" for i in range(1, 6)]
        + [f"T-{i}-rev1" for i in range(1, 8)]
        + [f"E-sat-{i}-rev1" for i in range(1, 6)]
        + [f"E-ver-{i}-rev1" for i in range(1, 8)]
    )
    b1 = stratum("B1", base_members, tau=2)
    b2_members = ([r for r in base_members
                   if r not in ("R-3-rev1", "E-ver-3-rev1",
                                "E-ver-2-rev1", "E-sat-3-rev1")]
                  + ["R-3-rev2", "T-8-rev1", "E-ver-3-rev2",
                     "E-ver-2-rev2", "E-sat-3-rev2"])
    b2 = stratum("B2", b2_members, tau=5, parent="B1")
    b_counter = stratum("B_counter", ["XA-rev1", "XB-rev1"], tau=5)

    # ---- query suite + gold (generator-defined)
    queries = [
        {"q_id": "Q1", "type": "entity_text", "stratum": "B1",
         "entity_id": "R-3", "mode": "stratum",
         "question": "What does requirement R-3 state in the approved "
                    "configuration B1? Cite the revision id.",
         "gold_rev": "R-3-rev1"},
        {"q_id": "Q2", "type": "entity_text", "stratum": "B2",
         "entity_id": "R-3", "mode": "stratum",
         "question": "What does requirement R-3 state in the approved "
                    "configuration B2? Cite the revision id.",
         "gold_rev": "R-3-rev2"},
        {"q_id": "Q3", "type": "verifiers", "stratum": "B1",
         "entity_id": "R-3", "mode": "stratum",
         "question": "Which test revisions verify requirement R-3 in "
                    "configuration B1? List revision ids.",
         "gold_revs": ["T-2-rev1"]},
        {"q_id": "Q4", "type": "verifiers", "stratum": "B2",
         "entity_id": "R-3", "mode": "stratum",
         "question": "Which test revisions verify requirement R-3 in "
                    "configuration B2? List revision ids.",
         "gold_revs": ["T-2-rev1", "T-8-rev1"]},
        {"q_id": "Q5", "type": "entity_text", "stratum": "B1",
         "entity_id": "R-1", "mode": "stratum",
         "question": "What does requirement R-1 state in configuration "
                    "B1? Cite the revision id.",
         "gold_rev": "R-1-rev1",
         "note": "revision-insensitive control: same answer in B1 and B2"},
        {"q_id": "Q6", "type": "config_members", "stratum": "B_counter",
         "mode": "stratum",
         "question": "Which revisions form the approved configuration "
                    "B_counter? List revision ids.",
         "gold_revs": ["XA-rev1", "XB-rev1"],
         "note": "counterexample: no latest-as-of restores {a1,b1}"},
        {"q_id": "Q7", "type": "asof_latest", "entity_id": "XA", "t": 5,
         "mode": "asof", "gold_rev": "XA-rev2",
         "note": "temporal slice returns a2 -- differs from B_counter"},
        {"q_id": "Q8", "type": "record_query", "stratum": "B1", "t": 1,
         "mode": "record",
         "gold_answer": "no record exists",
         "note": "absence of archive must not be reconstructed"},
        {"q_id": "Q9", "type": "availability", "stratum": "B2",
         "entity_id": "T-8", "t": 2, "mode": "as_available_at_T",
         "gold_revs": [],
         "note": "T-8 available_at=4 excluded in 'as available at T=2'"},
        {"q_id": "Q10", "type": "mixed_context", "stratum": "B1",
         "extra_rev": "R-3-rev2", "mode": "stratum",
         "gold_flag": "MEMBERSHIP_VIOLATION",
         "note": "injecting a genuine but non-member revision is flagged"},
    ]

    write_jsonl(os.path.join(root, "entities.jsonl"), entities)
    write_jsonl(os.path.join(root, "revisions.jsonl"), revisions)
    write_jsonl(os.path.join(root, "edges.jsonl"), edges)
    write_jsonl(os.path.join(root, "contracts.jsonl"), [contract])
    write_jsonl(os.path.join(root, "strata.jsonl"), [b1, b2, b_counter])
    write_jsonl(os.path.join(root, "queries.jsonl"), queries)
    return root


if __name__ == "__main__":
    print("corpus written to", generate())
