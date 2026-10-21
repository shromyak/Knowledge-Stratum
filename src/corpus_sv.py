"""Strategy Validator mini-corpus (Section 7 illustration, Phase 5).

Exports a small real subgraph from the epoch taxonomy (France chain,
society types, markers) and adds:
  - two strata SV_B1 / SV_B2 differing by a T5 taxonomy revision
    (FRANCE_RESTORATION reclassified Rigid_Hierarchical -> Legal;
    marker edge added to Anarchic)
  - strategy revisions evaluated as V(S, B, M) verdicts
  - control cases of Section 8.5: marker without a source,
    retrospective label in 'as available at T' mode
"""
import os
import shutil

from corpus_req import make_edge, make_revision
from model import Store, sha256_text, write_jsonl

ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "sv")

EPOCHS = [
    ("FRANCE_ANCIEN_REGIME", "Франція Ancien Régime", "Rigid_Hierarchical",
     "1643-1789", 0.7435, 0.9),
    ("FRANCE_REVOLUTION", "Французька Революція", "Anarchic",
     "1789-1794", 0.3025, 0.06),
    ("FRANCE_DIRECTORY", "Директорія", "Wild", "1795-1799", 0.5399, 0.15),
    ("FRANCE_NAPOLEON", "Наполеонівська Франція", "Rigid_Hierarchical",
     "1799-1815", 0.7535, 0.78),
    ("FRANCE_RESTORATION", "Реставрація Бурбонів", "Rigid_Hierarchical",
     "1815-1848", 0.6996, 0.674),
    ("FRANCE_SECOND_REPUBLIC", "Друга республіка", "Legal",
     "1848-1852", 0.1663, 0.637),
    ("FRANCE_SECOND_EMPIRE", "Друга імперія", "Rigid_Hierarchical",
     "1852-1870", 0.827, 0.689),
    ("FRANCE_THIRD_REPUBLIC", "Третя Республіка", "Consumer",
     "1870-1940", 0.3853, 0.64),
]

MARKERS = {
    "Rigid_Hierarchical": [
        ("M-RH-NAPOLEON", "Наполеон", "Marker_HistoricalHero"),
        ("M-RH-MACHT", "Князь (Макіавеллі, 1532)", "Marker_Literature"),
        ("M-RH-FIG", "Генеральний секретар / Імператор",
         "Marker_FigureState"),
    ],
    "Anarchic": [
        ("M-AN-MAHNO", "Нестор Махно", "Marker_HistoricalHero"),
        ("M-AN-UTOP", "Утопія (Томас Мор, 1516)", "Marker_Literature"),
        ("M-AN-FIG", "Отаман / Обраний гетьман", "Marker_FigureState"),
    ],
    "Wild": [
        ("M-W-DOVBUSH", "Олекса Довбуш", "Marker_HistoricalHero"),
        ("M-W-FIG", "Воєначальник / Ватажок банди", "Marker_FigureState"),
    ],
    "Legal": [
        ("M-L-LOCKE", "Джон Локк (1689)", "Marker_HistoricalHero"),
        ("M-L-FIG", "Суддя / Омбудсмен", "Marker_FigureState"),
    ],
    "Consumer": [
        ("M-C-FORD", "Генрі Форд", "Marker_HistoricalHero"),
        ("M-C-GATSBY", "Великий Гетсбі (1925)", "Marker_Literature"),
    ],
}


def generate():
    root = os.path.abspath(ROOT)
    if os.path.exists(root):
        shutil.rmtree(root)
    store = Store(root)
    entities, revisions, edges = [], [], []

    def ent(eid, etype):
        entities.append({"entity_id": eid, "type": etype})

    # ---- epochs (available since t=1)
    for eid, label, st, period, eta, g in EPOCHS:
        ent(eid, "epoch")
        txt = (f"EPOCH {eid}: {label}. period={period} "
               f"society_type={st} eta_lie={eta} military_gini={g}")
        revisions.append(make_revision(
            store, eid, f"{eid}-rev1", txt, system_from=1, valid_from=1,
            available_at=1))

    # ---- society types + markers
    for st, marks in MARKERS.items():
        ent(st, "society_type")
        revisions.append(make_revision(
            store, st, f"{st}-rev1",
            f"SOCIETY_TYPE {st}: taxonomy class rev1.",
            system_from=1, valid_from=1, available_at=1))
        for mid, name, mtype in marks:
            ent(mid, "marker")
            src = (f"wikidata://{mid}" if mid != "M-AN-MAHNO" else None)
            # M-AN-MAHNO deliberately has no source (Section 8.5 control)
            revisions.append(make_revision(
                store, mid, f"{mid}-rev1",
                f"MARKER {mid}: {name} [{mtype}] -> {st}",
                system_from=1, valid_from=1, available_at=1))
            revisions[-1]["source_ref"] = src

    # retrospective marker: created at t=10, 'available' then only
    ent("M-AN-RETRO", "marker")
    revisions.append(make_revision(
        store, "M-AN-RETRO", "M-AN-RETRO-rev1",
        "MARKER M-AN-RETRO: retrospectively attributed marker.",
        system_from=10, valid_from=10, available_at=10))

    # ---- edges: instance_of epoch -> society_type (rev1)
    for eid, _, st, *_ in EPOCHS:
        e_edge = f"EI-{eid}"
        ent(e_edge, "edge")
        edges.append(make_edge(store, e_edge, f"{e_edge}-rev1",
                               f"{eid}-rev1", f"{st}-rev1",
                               "instance_of", 1))
    # T5 revision: FRANCE_RESTORATION reclassified to Legal at t=4
    edges.append(make_edge(store, "EI-FRANCE_RESTORATION",
                           "EI-FRANCE_RESTORATION-rev2",
                           "FRANCE_RESTORATION-rev1", "Legal-rev1",
                           "instance_of", 4))

    # transitions between consecutive epochs
    for i in range(len(EPOCHS) - 1):
        e_edge = f"ET-{i}"
        ent(e_edge, "edge")
        edges.append(make_edge(store, e_edge, f"{e_edge}-rev1",
                               f"{EPOCHS[i][0]}-rev1",
                               f"{EPOCHS[i+1][0]}-rev1",
                               "transitioned_to", 1))

    # has_marker edges society_type -> marker
    for st, marks in MARKERS.items():
        for j, (mid, *_m) in enumerate(marks):
            e_edge = f"EM-{st}-{j}"
            ent(e_edge, "edge")
            edges.append(make_edge(store, e_edge, f"{e_edge}-rev1",
                                   f"{st}-rev1", f"{mid}-rev1",
                                   "has_marker", 1))
    # T5 addition: retrospective marker attached to Anarchic at t=10
    ent("EM-Anarchic-retro", "edge")
    edges.append(make_edge(store, "EM-Anarchic-retro",
                           "EM-Anarchic-retro-rev1",
                           "Anarchic-rev1", "M-AN-RETRO-rev1",
                           "has_marker", 10))

    # ---- strategies
    ent("S-CENTRAL", "strategy")
    revisions.append(make_revision(
        store, "S-CENTRAL", "S-CENTRAL-rev1",
        "STRATEGY S-CENTRAL rev1: expand via centralized command "
        "hierarchy.\nrequires_society_type: Rigid_Hierarchical\n"
        "epoch: FRANCE_REVOLUTION",
        system_from=1, valid_from=1, available_at=1))
    ent("S-ORDER", "strategy")
    revisions.append(make_revision(
        store, "S-ORDER", "S-ORDER-rev1",
        "STRATEGY S-ORDER rev1: consolidate via restored dynastic "
        "order.\nrequires_society_type: Rigid_Hierarchical\n"
        "epoch: FRANCE_RESTORATION",
        system_from=1, valid_from=1, available_at=1))
    ent("S-EVID", "strategy")
    revisions.append(make_revision(
        store, "S-EVID", "S-EVID-rev1",
        "STRATEGY S-EVID rev1: mobilize via ataman-style coalition.\n"
        "requires_society_type: Anarchic\nepoch: FRANCE_REVOLUTION\n"
        "needs_marker: M-AN-MAHNO",
        system_from=1, valid_from=1, available_at=1))

    # ---- contract
    contract = {
        "contract_rev": "C-sv-1", "domain": "strategy validation",
        "description": "Contract for the Strategy Validator strata.",
        "historicity_mode": "as_available_at_T",
        "member_types": ["epoch", "society_type", "marker", "strategy",
                         "edge"],
        "versioning_policy": {"revisions": "immutable",
                              "selection": "pinned"},
        "external_deps": [],
        "temporal_constraints": {"max_available_at": None},
        "contradiction_rules": {
            "allow_multiple_revisions_per_entity": True,
            "require_explicit_roles": True, "mark_conflicts": True},
        "consistency_checks": ["members_exist", "hash_integrity",
                               "member_types", "edge_endpoints",
                               "temporal_constraints",
                               "contradiction_rules"],
        "approval": {"approver_ref": "synthetic-generator",
                     "decision_ref": "gen://approval/C-sv-1"},
    }

    def stratum(sid, rev_ids, tau, parent=None, roles=None):
        roles = roles or {}
        members = [{"rev_id": r, "role": roles.get(r, "member")}
                   for r in rev_ids]
        s = {"stratum_id": sid, "contract_rev": "C-sv-1",
             "approval": {"approver_ref": "synthetic-generator",
                          "decision_ref": f"gen://approval/{sid}",
                          "tau": tau}, "parent_ref": parent}
        joined = "|".join(sorted(m["rev_id"] for m in members))
        s["members_manifest"] = members
        s["members_hash"] = sha256_text(joined)
        return s

    epoch_revs = [f"{e[0]}-rev1" for e in EPOCHS]
    stype_revs = [f"{st}-rev1" for st in MARKERS]
    marker_revs = [f"{m[0]}-rev1" for ms in MARKERS.values() for m in ms]
    inst_revs1 = [f"EI-{e[0]}-rev1" for e in EPOCHS]
    trans_revs = [f"ET-{i}-rev1" for i in range(len(EPOCHS) - 1)]
    mark_edges = [f"EM-{st}-{j}-rev1" for st, ms in MARKERS.items()
                  for j in range(len(ms))]

    b1 = stratum("SV_B1",
                 epoch_revs + stype_revs + marker_revs + inst_revs1
                 + trans_revs + mark_edges + ["S-CENTRAL-rev1",
                                              "S-ORDER-rev1",
                                              "S-EVID-rev1"],
                 tau=3)

    # SV_B2: taxonomy rev2 — FRANCE_RESTORATION reclassified; retro marker
    inst_revs2 = [r if r != "EI-FRANCE_RESTORATION-rev1"
                  else "EI-FRANCE_RESTORATION-rev2" for r in inst_revs1]
    b2 = stratum("SV_B2",
                 epoch_revs + stype_revs + marker_revs + inst_revs2
                 + trans_revs + mark_edges
                 + ["EM-Anarchic-retro-rev1", "M-AN-RETRO-rev1",
                    "S-CENTRAL-rev1", "S-ORDER-rev1", "S-EVID-rev1"],
                 tau=6, parent="SV_B1")

    queries = [
        {"q_id": "QS1", "type": "strategy_verdict", "stratum": "SV_B1",
         "strategy_rev": "S-CENTRAL-rev1", "mode": "stratum",
         "gold_verdict": "contradicts",
         "note": "centralized strategy vs Anarchic epoch frame"},
        {"q_id": "QS2a", "type": "strategy_verdict", "stratum": "SV_B1",
         "strategy_rev": "S-ORDER-rev1", "mode": "stratum",
         "gold_verdict": "consistent"},
        {"q_id": "QS2b", "type": "strategy_verdict", "stratum": "SV_B2",
         "strategy_rev": "S-ORDER-rev1", "mode": "stratum",
         "gold_verdict": "contradicts",
         "note": "same data, taxonomy rev2: T5 reclassification flips "
                 "the verdict"},
        {"q_id": "QS3", "type": "strategy_verdict", "stratum": "SV_B1",
         "strategy_rev": "S-EVID-rev1", "mode": "stratum",
         "gold_verdict": "insufficient evidence",
         "note": "required marker has no source (Section 8.5 control)"},
        {"q_id": "QS4", "type": "availability", "stratum": "SV_B2",
         "entity_id": "M-AN-RETRO", "t": 5,
         "mode": "as_available_at_T", "gold_revs": [],
         "note": "retrospective marker (available_at=10) excluded at T=5"},
        {"q_id": "QS5", "type": "config_members", "stratum": "SV_B2",
         "mode": "stratum",
         "gold_revs": ["EI-FRANCE_RESTORATION-rev2",
                       "M-AN-RETRO-rev1"],
         "note": "membership check: taxonomy rev2 members present"},
    ]

    write_jsonl(os.path.join(root, "entities.jsonl"), entities)
    write_jsonl(os.path.join(root, "revisions.jsonl"), revisions)
    write_jsonl(os.path.join(root, "edges.jsonl"), edges)
    write_jsonl(os.path.join(root, "contracts.jsonl"), [contract])
    write_jsonl(os.path.join(root, "strata.jsonl"), [b1, b2])
    write_jsonl(os.path.join(root, "queries.jsonl"), queries)
    return root


if __name__ == "__main__":
    print("sv corpus written to", generate())
