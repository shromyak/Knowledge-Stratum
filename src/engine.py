"""Run pipeline: admissible retrieval -> generation -> claims -> journal.

Query dispatcher is deterministic by design: the prototype demonstrates
auditability mechanics (which revisions were admissible, supplied, cited),
not LLM answer quality. A real model can replace `TemplateGenerator`
behind the same interface.
"""
import datetime
import json
import os

from contract import admissible_members, check_stratum
from model import latest_asof, read_jsonl


def member_content(store, rev_ids):
    return {r["rev_id"]: store.read_content(r["content_ref"])
            for r in store.revisions() if r["rev_id"] in rev_ids}


def answer_query(store, query, allowed, run_dir=None):
    """Answer one query restricted to `allowed` rev_ids. Returns (answer,
    claims, context_revs, flags)."""
    edges = {e["edge_rev_id"]: e for e in store.edges()}
    revs = {r["rev_id"]: r for r in store.revisions()}
    for e in store.edges():
        revs[e["edge_rev_id"]] = e
    content = member_content(store, allowed)
    claims, flags = [], []

    qtype = query["type"]

    if qtype == "entity_text":
        cand = [rid for rid in allowed
                if revs.get(rid, {}).get("entity_id") == query["entity_id"]]
        cand.sort()
        ctx = cand[:1]
        if not ctx:
            return "insufficient evidence", claims, [], ["UNRESOLVED"]
        text = content[ctx[0]]
        claims.append({"text": text.split(":")[1].strip() if ":" in text
                       else text,
                       "evidence_type": "documented",
                       "source_rev_refs": ctx,
                       "verification": None})
        return text, claims, ctx, flags

    if qtype == "verifiers":
        target = query["entity_id"]
        tests = []
        ctx = []
        for rid in allowed:
            er = edges.get(rid)
            if er and er["type"] == "verifies" \
                    and er["dst_rev"] in allowed \
                    and revs.get(er["dst_rev"], {}).get("entity_id") == target:
                ctx.append(rid)
                tests.append(er["src_rev"])
        ctx = sorted(ctx)
        tests = sorted(t for t in tests if t in allowed)
        edge_of = {edges[r]["src_rev"]: r for r in ctx}
        for t in tests:
            claims.append({"text": f"{t} verifies {target}",
                           "evidence_type": "documented",
                           "source_rev_refs": [t],
                           "edge_rev_ref": edge_of.get(t),
                           "verification": None})
        if not tests:
            return "insufficient evidence", claims, ctx, ["UNRESOLVED"]
        return "verifying tests: " + ", ".join(tests), claims, \
            ctx + tests, flags

    if qtype == "config_members":
        ctx = sorted(allowed)
        return "configuration members: " + ", ".join(ctx), claims, ctx, flags

    if qtype == "asof_latest":
        r = latest_asof(store.revisions(), query["entity_id"], query["t"])
        if not r:
            return "insufficient evidence", claims, [], ["UNRESOLVED"]
        text = store.read_content(r["content_ref"])
        claims.append({"text": text, "evidence_type": "documented",
                       "source_rev_refs": [r["rev_id"]], "verification": None})
        return text, claims, [r["rev_id"]], flags

    if qtype == "record_query":
        # Archive check: was there a recorded run at or before t?
        t = query["t"]
        found = False
        if run_dir and os.path.isdir(run_dir):
            for fn in os.listdir(run_dir):
                if not fn.endswith(".jsonl"):
                    continue
                for rec in read_jsonl(os.path.join(run_dir, fn)):
                    if rec.get("time_unix", 0) and rec["time_unix"] <= t \
                            and rec.get("stratum_id") == query["stratum"]:
                        found = True
        if not found:
            claims.append({"text": "no record exists",
                           "evidence_type": "unresolved",
                           "source_rev_refs": [], "verification": None})
            return "no record exists", claims, [], flags
        return "record exists", claims, [], flags

    if qtype == "availability":
        # 'as available at T': drop members unavailable at t
        t = query["t"]
        vis = {rid for rid in allowed
               if (revs[rid].get("available_at") or 0) <= t}
        cand = [rid for rid in vis
                if revs.get(rid, {}).get("entity_id") == query["entity_id"]]
        cand.sort()
        if not cand:
            claims.append({"text": "no admissible revision at T",
                           "evidence_type": "unresolved",
                           "source_rev_refs": [], "verification": None})
            return "no admissible revision at T", claims, [], flags
        return content[cand[0]], claims, cand, flags

    if qtype == "strategy_verdict":
        # V(S, B, M): verdict of a strategy against an epoch frame
        # (Section 7). Strategy content carries structured directives.
        srev = query["strategy_rev"]
        text = content.get(srev, "")
        fields = {}
        for line in text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fields[k.strip()] = v.strip()
        req_st = fields.get("requires_society_type")
        epoch_id = fields.get("epoch")
        needs = fields.get("needs_marker")
        epoch_rev = f"{epoch_id}-rev1"
        stype, ctx = None, [srev]
        for rid in allowed:
            er = edges.get(rid)
            if er and er["type"] == "instance_of" \
                    and er["src_rev"] == epoch_rev:
                stype, ctx = er["dst_rev"], ctx + [rid, er["dst_rev"]]
        if epoch_rev not in allowed or stype is None:
            claims.append({"text": "epoch frame not in stratum",
                           "evidence_type": "unresolved",
                           "source_rev_refs": ctx, "verification": None})
            return "verdict: insufficient evidence", claims, ctx, flags
        st_name = stype.rsplit("-rev", 1)[0]
        verdict = "consistent" if st_name == req_st else "contradicts"
        if needs and verdict == "consistent":
            mrev = f"{needs}-rev1"
            edge_ok = any(edges[r]["dst_rev"] == mrev
                          and edges[r]["src_rev"] == stype
                          for r in allowed if r in edges)
            marker = revs.get(mrev)
            if not edge_ok or not (marker or {}).get("source_ref"):
                verdict = "insufficient evidence"
                ctx.append(mrev)
        claims.append({"text": f"verdict {verdict} for {srev}",
                       "evidence_type": "derived",
                       "source_rev_refs": ctx, "verification": None})
        return f"verdict: {verdict}", claims, ctx, flags

    if qtype == "mixed_context":
        extra = query["extra_rev"]
        if extra in allowed:
            flags.append("UNEXPECTED")
        else:
            flags.append("MEMBERSHIP_VIOLATION")
            claims.append({"text": f"{extra} is not a stratum member",
                           "evidence_type": "unresolved",
                           "source_rev_refs": [], "verification": None})
        return f"revision {extra} rejected: outside membership", \
            claims, [], flags

    raise ValueError(f"unknown query type {qtype}")


LLM_TYPES = {"entity_text", "verifiers", "config_members"}

# task-type hints for the LLM: what the fragment set means and which
# revision ids are the expected citation targets
TYPE_HINTS = {
    "entity_text":
        "Cite the revision id of the fragment that directly states the "
        "requested fact (e.g. R-*-rev*), not relationship edges [E-*].",
    "verifiers":
        "Relationship fragments [E-ver-*] record which test verifies "
        "the requirement; in your answer cite the test revision ids "
        "(T-*-rev*), i.e. the member revisions, not the edges.",
    "config_members":
        "TASK: the fragments below ARE exactly the approved members of "
        "the configuration asked about. Your answer must list all of "
        "their revision ids, e.g. [XA-rev1], [XB-rev1].",
}


def answer_llm(store, query, allowed, gen):
    """Real-LLM path: the model answers from admissible fragments only
    and must cite revision ids. Citations outside membership are
    flagged as MEMBERSHIP_VIOLATION."""
    from llm import cited_revs
    revs = {r["rev_id"]: r for r in store.revisions()}
    for e in store.edges():
        revs[e["edge_rev_id"]] = e
    frags = []
    for rid in sorted(allowed):
        r = revs.get(rid)
        if r:
            text = store.read_content(r["content_ref"]).replace("\n", " ")
            frags.append(f"[{rid}] {text}")
    prompt = (
        f"All admissible fragments below belong to the approved "
        f"configuration named in the question.\n\n"
        f"QUESTION: {query['question']}\n\n"
        f"NOTE: {TYPE_HINTS[query['type']]}\n\n"
        f"ADMISSIBLE FRAGMENTS:\n" + "\n".join(frags))
    out = gen(prompt).strip()
    cited = cited_revs(out)
    viol = [c for c in cited if c not in allowed]
    flags = ["MEMBERSHIP_VIOLATION"] if viol else []
    claims = [{"text": out[:500], "evidence_type": "documented",
               "source_rev_refs": [c], "verification": None,
               "llm_sourced": True}
              for c in cited if c in allowed]
    ctx = [c for c in cited if c in allowed]
    return out, claims, ctx, flags


def verify_claims(store, claims, allowed):
    """Identifier check + naive semantic support check.

    Semantic check: for 'documented' claims, require that the claim text
    (after the first colon) literally appears in the cited revision's
    content. Returns verdicts stored on each claim.
    """
    for c in claims:
        id_ok = (all(ref in allowed for ref in c["source_rev_refs"])
                 if allowed is not None else None)
        c["verification"] = {"identifier_check": id_ok}
        if c.get("llm_sourced"):
            # paraphrased model output: substring check is meaningless;
            # hook for an entailment/self-critique verifier pass
            c["verification"]["semantic"] = "indeterminate"
            continue
        if c["evidence_type"] == "derived":
            # a derived claim is supported when all its declared inputs
            # are admissible members (method/computation = this verdict)
            c["verification"]["semantic"] = (
                "supported" if id_ok is not False else "unsupported")
            continue
        if c["evidence_type"] != "documented":
            c["verification"]["semantic"] = "indeterminate"
            continue
        if not c["source_rev_refs"]:
            c["verification"]["semantic"] = "unsupported"
            continue
        # relation claim: the cited edge must exist in the admissible set
        # and connect the cited revision to the claimed target
        edge_ref = c.get("edge_rev_ref")
        if edge_ref:
            er = {e["edge_rev_id"]: e for e in
                  store.edges()}.get(edge_ref)
            c["verification"]["semantic"] = (
                "supported" if er and (allowed is None
                                       or edge_ref in allowed)
                and er["src_rev"] in c["source_rev_refs"]
                else "unsupported")
            continue
        supported = False
        for ref in c["source_rev_refs"]:
            rev = store.revision(ref)
            if not rev:
                continue
            text = store.read_content(rev["content_ref"])
            frag = c["text"].strip()
            if frag and frag in text:
                supported = True
        # claims built by the dispatcher embed the rev text; the check is
        # a stand-in for an entailment/verifier pass (Section 4.4)
        c["verification"]["semantic"] = (
            "supported" if supported and id_ok is not False
            else "unsupported")
    return claims


def run_suite(store, queries, mode, journal_path, run_dir=None, T=None,
              gen=None, gen_id=None):
    """Run all queries under one enforcement mode.

    mode: 'A4' (contract service) or 'A5' (manifest-as-data resolver).
    gen: optional real-LLM callable(prompt)->text; queries of LLM_TYPES
    with a 'question' are answered by the model, the rest by the
    deterministic dispatcher.
    """
    runs = []
    for q in queries:
        if q["type"] in ("asof_latest", "record_query"):
            # these modes deliberately bypass stratum enforcement
            allowed, report = None, None
        elif mode == "A5":
            allowed, report = _a5_resolver(store, q["stratum"], T)
        else:
            st = store.stratum(q["stratum"])
            allowed, report = admissible_members(store, st, T=T)

        use_llm = gen and q["type"] in LLM_TYPES and q.get("question")
        if use_llm:
            answer, claims, ctx, flags = answer_llm(
                store, q, allowed if allowed is not None else set(), gen)
        else:
            answer, claims, ctx, flags = answer_query(
                store, q, allowed if allowed is not None else set(),
                run_dir)
        claims = verify_claims(store, claims, allowed)

        run = {
            "q_id": q["q_id"], "mode": mode,
            "historicity_mode": q.get("mode"),
            "stratum_id": q.get("stratum"),
            "context_revs": ctx,
            "answer": answer,
            "claims": claims,
            "flags": flags,
            "contract_report_ok": report["ok"] if report else None,
            "time": datetime.datetime.now().isoformat(timespec="seconds"),
            "time_unix": int(datetime.datetime.now().timestamp()),
            "model_id": gen_id if use_llm else "TemplateGenerator/0.1",
            "generation_controls": {"decoding": "deterministic",
                                    "parametric_mitigation": None},
        }
        runs.append(run)
    with open(journal_path, "w", encoding="utf-8") as f:
        for r in runs:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return runs


def _a5_resolver(store, stratum_id, T=None):
    """A5 path: the manifest stored as data (SQLite rows) resolved by an
    as-of-style query — see asof_store.py."""
    from asof_store import members_from_db
    db = os.path.join(store.root, "a5.db")
    members = members_from_db(db, stratum_id)
    if T is not None:
        revs = {r["rev_id"]: r for r in store.revisions()}
        members = {m for m in members
                   if (revs[m].get("available_at") or 0) <= T}
    return members, {"ok": True,
                     "checks": [{"check": "a5_membership", "ok": True}]}
