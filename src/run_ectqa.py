"""ECT-QA pilot runner (Phase 4 / Q9): A2 vs A3.

Modes per question:
  A2  as-of slice: company docs with quarter <= window_end (everything
      known up to T, periods outside the asked window included)
  A3  admissible window: company docs with window_start <= quarter
      <= window_end

Metrics: answer correctness vs gold (unanswerable -> must abstain;
answerable -> LLM-judge), inadmissible-doc usage (retrieved/cited docs
outside the window), abstention correctness.

Usage:
    OPENAI_BASE_URL=http://localhost:1234/v1 OPENAI_API_KEY=lm-studio \
        python3 src/run_ectqa.py openai:openai/gpt-oss-20b \
        [--n-ans 20] [--n-unans 10] [--k 4]
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ectqa
from llm import make_generator

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

SYSTEM = ("You are a financial analyst. Answer the question using ONLY "
          "the transcript excerpts below, each tagged [doc_id] where "
          "doc_id encodes company, year and quarter. Answer concisely "
          "and cite the doc_id(s) you relied on. If the excerpts do not "
          "contain the answer, reply exactly: unanswerable")

JUDGE = ("Compare a model answer to a reference answer for the same "
         "question. Reply with exactly one word: CORRECT if the model "
         "answer is substantively equivalent (numbers/facts/dates "
         "match, minor phrasing allowed), else INCORRECT.\n\n"
         "QUESTION: {q}\nREFERENCE: {g}\nMODEL: {a}")

DOCID_RE = re.compile(r"\b[a-z_]+-[A-Za-z_]+-\d{4}-q[1-4]\b")


def company_name_map(metas):
    """company_name -> sector-ticker, read from one doc per company."""
    seen, out = set(), {}
    for m in metas:
        key = f"{m['sector']}-{m['ticker']}"
        if key in seen:
            continue
        seen.add(key)
        try:
            d = json.load(open(m["path"]))
            out[(d.get("company_name") or "").lower()] = key
        except Exception:
            pass
    return out


def candidates_for(query, metas, names=None):
    """Company-scoped candidate docs for the question."""
    key = query["company_key"]
    if key:
        return [m for m in metas if
                f"{m['sector']}-{m['ticker']}" == key]
    # unanswerable questions have no evidence/company: match a company
    # name or ticker mentioned in the question text
    ql = query["question"].lower()
    for name, k in (names or {}).items():
        if name and name in ql:
            return [m for m in metas
                    if f"{m['sector']}-{m['ticker']}" == k]
    hit = [m for m in metas
           if m["ticker"].lower().replace("_", " ") in ql]
    if hit:
        tk = {f"{m['sector']}-{m['ticker']}" for m in hit}
        return [m for m in metas if f"{m['sector']}-{m['ticker']}" in tk]
    return metas  # fall back to whole corpus


def run_mode(query, metas, mode, gen, k, names=None):
    """One A2/A3 run: retrieve -> prompt -> answer -> citations."""
    cands = candidates_for(query, metas, names)
    win = query["window"]
    if win and mode == "A3":
        pool = [m for m in cands if win[0] <= m["t"] <= win[1]]
    elif win and mode == "A2":
        pool = [m for m in cands if m["t"] <= win[1]]
    else:
        pool = cands
    frags = ectqa.retrieve(query["question"], pool, k=k)
    prompt = ("QUESTION: " + query["question"] + "\n\n"
              "TRANSCRIPT EXCERPTS:\n" +
              "\n\n".join(f"[{d}] {x}" for d, x in frags))
    answer = gen(prompt).strip()
    cited = sorted(set(DOCID_RE.findall(answer)))
    winset = set()
    if win:
        winset = {m["doc_id"] for m in cands
                  if win[0] <= m["t"] <= win[1]}
    inadmissible_ret = [d for d, _ in frags if win and d not in winset]
    inadmissible_cited = [c for c in cited if win and c not in winset]
    return {"answer": answer, "retrieved": [d for d, _ in frags],
            "cited": cited, "inadmissible_retrieved": inadmissible_ret,
            "inadmissible_cited": inadmissible_cited,
            "pool_size": len(pool)}


ABSTAIN_PHRASES = ("unanswerable", "insufficient evidence",
                   "cannot be determined", "not answerable")


def grade(query, run, judge):
    gold = query["gold_answer"]
    if gold == "unanswerable":
        # substantively correct abstention, any wording
        return any(p in run["answer"].lower() for p in ABSTAIN_PHRASES)
    return "CORRECT" in judge(JUDGE.format(
        q=query["question"], g=gold, a=run["answer"])).upper()


def main():
    spec = sys.argv[1] if len(sys.argv) > 1 else "openai:openai/gpt-oss-20b"
    def arg(flag, default):
        return int(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default
    n_ans, n_un, k = arg("--n-ans", 20), arg("--n-unans", 10), \
        arg("--k", 4)

    queries, metas = ectqa.build(n_ans, n_un)
    names = company_name_map(metas)
    gen, model_id = make_generator(spec)

    outdir = os.path.join(BASE, "runs")
    os.makedirs(outdir, exist_ok=True)
    journal = os.path.join(outdir, "ectqa_llm.jsonl")
    t0 = time.time()
    stats = {m: {"n": 0, "correct": 0, "inad_ret": 0, "inad_cited": 0,
                 "retrieved": 0} for m in ("A2", "A3")}
    with open(journal, "w") as jf:
        for q in queries:
            rec = {"q_id": q["q_id"], "question": q["question"],
                   "gold": q["gold_answer"], "window": q["window"],
                   "model_id": model_id, "modes": {}}
            for mode in ("A2", "A3"):
                run = run_mode(q, metas, mode, gen, k, names)
                ok = grade(q, run, gen)
                run["correct"] = ok
                rec["modes"][mode] = run
                s = stats[mode]
                s["n"] += 1
                s["correct"] += ok
                s["inad_ret"] += bool(run["inadmissible_retrieved"])
                s["inad_cited"] += bool(run["inadmissible_cited"])
                s["retrieved"] += len(run["retrieved"])
            jf.write(json.dumps(rec) + "\n")
            print(f"{q['q_id']} [{q['reasoning_type']}] "
                  f"A2={'OK' if rec['modes']['A2']['correct'] else 'X'} "
                  f"A3={'OK' if rec['modes']['A3']['correct'] else 'X'} "
                  f"inad_ret: "
                  f"A2={len(rec['modes']['A2']['inadmissible_retrieved'])} "
                  f"A3={len(rec['modes']['A3']['inadmissible_retrieved'])}")

    print("\n== ECT-QA pilot (A2 as-of slice vs A3 admissible window) ==")
    for m, s in stats.items():
        n = s["n"]
        print(f"  {m}: correct {s['correct']}/{n} "
              f"({s['correct']/n:.2f}); runs with inadmissible docs "
              f"retrieved {s['inad_ret']}/{n}, cited "
              f"{s['inad_cited']}/{n}")
    print(f"elapsed {time.time()-t0:.0f}s; journal: {journal}")


if __name__ == "__main__":
    main()
