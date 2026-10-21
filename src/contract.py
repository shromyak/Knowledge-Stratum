"""Contract checker for a stratum (Section 4.2 of the article).

Checks implemented:
  members_exist        -- every rev_id in the manifest exists in the store
  hash_integrity       -- stored content hash matches the blob
  member_types         -- entity type of each member is admissible
  edge_endpoints       -- included edge endpoints are members or declared
                          external deps with exact revisions
  temporal_constraints -- available_at <= max_available_at (unknown flagged)
  contradiction_rules  -- multiple revisions of one entity require explicit roles

check_stratum(store, stratum, mode) -> report dict with verdicts and codes.
"""
import os

from model import read_jsonl, sha256_text


def _rev_index(store):
    """revisions.jsonl plus edge revisions keyed by edge_rev_id."""
    idx = {r["rev_id"]: r for r in store.revisions()}
    for e in store.edges():
        idx[e["edge_rev_id"]] = e
    return idx


def check_stratum(store, stratum, T=None):
    """Return a machine-readable check report for one stratum.

    If T is given, the historical mode 'as available at T' is also checked.
    """
    contract = store.contract(stratum["contract_rev"])
    report = {
        "stratum_id": stratum["stratum_id"],
        "contract_rev": stratum["contract_rev"],
        "checks": [],
        "ok": True,
    }
    if contract is None:
        report["ok"] = False
        report["checks"].append(
            {"check": "contract_present", "ok": False,
             "code": "CONTRACT_MISSING",
             "detail": f"contract {stratum['contract_rev']} not found"})
        return report

    checks = set(contract.get("consistency_checks", []))
    revs = _rev_index(store)
    manifest = stratum["members_manifest"]
    member_ids = {m["rev_id"] for m in manifest}

    # --- members_exist -------------------------------------------------
    missing = [m["rev_id"] for m in manifest if m["rev_id"] not in revs]
    report["checks"].append({
        "check": "members_exist", "ok": not missing,
        "code": "MEMBER_MISSING" if missing else None,
        "detail": missing})

    # --- hash_integrity -------------------------------------------------
    bad_hash = []
    if "hash_integrity" in checks:
        for m in manifest:
            r = revs.get(m["rev_id"])
            if not r:
                continue
            try:
                text = store.read_content(r["content_ref"])
            except OSError:
                bad_hash.append({"rev_id": m["rev_id"], "code": "CONTENT_UNREADABLE"})
                continue
            if sha256_text(text) != r["content_hash"]:
                bad_hash.append({"rev_id": m["rev_id"], "code": "HASH_MISMATCH"})
    report["checks"].append({
        "check": "hash_integrity", "ok": not bad_hash,
        "code": "HASH_MISMATCH" if bad_hash else None,
        "detail": bad_hash})

    # --- member_types ---------------------------------------------------
    entities = {e["entity_id"]: e for e in
                read_jsonl(os.path.join(store.root, "entities.jsonl"))}
    allowed = set(contract.get("member_types", []))
    bad_type = []
    if allowed:
        for m in manifest:
            r = revs.get(m["rev_id"])
            if not r:
                continue
            ent = entities.get(r.get("entity_id") or r.get("edge_id"), {})
            if ent.get("type") not in allowed:
                bad_type.append({"rev_id": m["rev_id"], "type": ent.get("type")})
    report["checks"].append({
        "check": "member_types", "ok": not bad_type,
        "code": "TYPE_INADMISSIBLE" if bad_type else None,
        "detail": bad_type})

    # --- edge_endpoints ---------------------------------------------------
    edge_revs = {e["edge_rev_id"]: e for e in store.edges()}
    ext = {d["ref"] for d in contract.get("external_deps", [])}
    bad_ep = []
    if "edge_endpoints" in checks:
        for m in manifest:
            er = edge_revs.get(m["rev_id"])
            if not er:
                continue
            for end in ("src_rev", "dst_rev"):
                v = er[end]
                if v not in member_ids and v not in ext:
                    bad_ep.append({"edge_rev": m["rev_id"], "end": end,
                                   "rev": v, "code": "ENDPOINT_EXTERNAL"})
    report["checks"].append({
        "check": "edge_endpoints", "ok": not bad_ep,
        "code": "ENDPOINT_EXTERNAL" if bad_ep else None,
        "detail": bad_ep})

    # --- temporal_constraints --------------------------------------------
    tc = contract.get("temporal_constraints", {})
    violations, unknown = [], []
    bound = T if T is not None else tc.get("max_available_at")
    if bound is not None:
        for m in manifest:
            r = revs.get(m["rev_id"])
            if not r:
                continue
            av = r.get("available_at")
            if av is None:
                unknown.append(m["rev_id"])
            elif av > bound:
                violations.append({"rev_id": m["rev_id"], "available_at": av})
    report["checks"].append({
        "check": "temporal_constraints", "ok": not violations,
        "code": "AVAILABILITY_VIOLATION" if violations else None,
        "detail": violations, "unknown_availability": unknown})

    # --- contradiction_rules ----------------------------------------------
    cr = contract.get("contradiction_rules", {})
    conflicts = []
    if cr.get("require_explicit_roles") or not cr.get(
            "allow_multiple_revisions_per_entity", False):
        per_entity = {}
        for m in manifest:
            r = revs.get(m["rev_id"])
            if not r or m["rev_id"] in edge_revs:
                continue
            per_entity.setdefault(
                r.get("entity_id") or r.get("edge_id"), []).append(m)
        for ent, ms in per_entity.items():
            if len(ms) <= 1:
                continue
            if not cr.get("allow_multiple_revisions_per_entity", False):
                conflicts.append({"entity_id": ent, "code": "DUPLICATE_REVISION"})
            elif any(not mm.get("role") for mm in ms):
                conflicts.append({"entity_id": ent, "code": "ROLE_MISSING"})
    report["checks"].append({
        "check": "contradiction_rules", "ok": not conflicts,
        "code": "CONFLICT" if conflicts else None, "detail": conflicts})

    report["ok"] = all(c["ok"] for c in report["checks"])
    return report


def admissible_members(store, stratum, T=None):
    """Member rev_ids passing the contract; availability filter at T when given."""
    report = check_stratum(store, stratum, T=T)
    ok_checks = {c["check"]: c for c in report["checks"]}
    viol = {d["rev_id"] for d in
            ok_checks.get("temporal_constraints", {}).get("detail", [])}
    missing = set(ok_checks.get("members_exist", {}).get("detail", []))
    return {m["rev_id"] for m in stratum["members_manifest"]
            if m["rev_id"] not in viol and m["rev_id"] not in missing}, report
