"""ADQAB/DQABench pilot runner (Phase 4 / Q9, second dataset).

Modes per question (MCQA, deterministic letter grading):
  A2  as-of slice: docs published <= window end (all earlier history)
  A3  admissible window: docs published inside plot_time_bounds

Usage:
    OPENAI_BASE_URL=http://localhost:1234/v1 OPENAI_API_KEY=lm-studio \
        python3 src/run_adqab.py openai:openai/gpt-oss-20b \
        [--n 30] [--k 4] [--seed 11]
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import adqab
from llm import make_generator

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

SYSTEM = ("You are a financial analyst answering a multiple-choice "
          "question. Use ONLY the news excerpts below, each tagged "
          "[doc_id|date]. Reply on the first line with exactly the "
          "letter of the BEST choice (A, B, C or D) — always pick one, "
          "even if the evidence is weak — then on the next line cite "
          "the doc_id(s) you relied on.")

LETTER_RE = re.compile(r"\b([A-D])\b")
DOCID_RE = re.compile(r"\bdoc_\d+\b")


def run_mode(q, docs, metas, mode, gen, k):
    lo, hi = q["window"]
    if mode == "A3":
        pool = [m for m in metas if lo <= m["date"] <= hi]
    else:  # A2: as-of slice at window end
        pool = [m for m in metas if m["date"] <= hi]
    frags = adqab.retrieve(q["question"], q["ticker"], docs, pool, k=k)
    choices = "\n".join(f"{k2}. {v}" for k2, v in q["choices"].items())
    prompt = (f"QUESTION: {q['question']}\n\nCHOICES:\n{choices}\n\n"
              f"NEWS EXCERPTS:\n" +
              "\n\n".join(f"[{d}|{dt}] {x}" for d, dt, x in frags))
    answer = gen(prompt).strip()
    m = LETTER_RE.search(answer)
    cited = sorted(set(DOCID_RE.findall(answer)))
    winset = {mm["doc_id"] for mm in metas if lo <= mm["date"] <= hi}
    return {"answer": answer, "letter": m.group(1) if m else None,
            "retrieved": [d for d, _, _ in frags],
            "cited": cited,
            "inadmissible_retrieved":
                [d for d, _, _ in frags if d not in winset],
            "inadmissible_cited": [c for c in cited if c not in winset],
            "pool_size": len(pool)}


def main():
    spec = sys.argv[1] if len(sys.argv) > 1 else "openai:openai/gpt-oss-20b"
    def arg(flag, default):
        return int(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default
    n, k, seed = arg("--n", 30), arg("--k", 4), arg("--seed", 11)

    print("loading ADQAB corpus (127MB on first run, cached after)...")
    docs = adqab.load_docs()
    dates = adqab.load_dates()
    metas = [{"doc_id": i, "date": d} for i, d in dates.items()
             if i in docs]
    queries = adqab.sample_questions(n, seed)
    gen, model_id = make_generator(spec)
    print(f"{len(queries)} questions, {len(metas)} dated docs, "
          f"model {model_id}")

    outdir = os.path.join(BASE, "runs")
    os.makedirs(outdir, exist_ok=True)
    journal = os.path.join(outdir, "adqab_llm.jsonl")
    t0 = time.time()
    stats = {m: {"n": 0, "correct": 0, "inad_ret": 0,
                 "inad_cited": 0} for m in ("A2", "A3")}
    with open(journal, "w") as jf:
        for q in queries:
            rec = {"q_id": q["q_id"], "question": q["question"],
                   "ticker": q["ticker"], "gold": q["gold_answer"],
                   "window": q["window"], "model_id": model_id,
                   "modes": {}}
            for mode in ("A2", "A3"):
                run = run_mode(q, docs, metas, mode, gen, k)
                run["correct"] = run["letter"] == q["gold_answer"]
                rec["modes"][mode] = run
                s = stats[mode]
                s["n"] += 1
                s["correct"] += run["correct"]
                s["inad_ret"] += bool(run["inadmissible_retrieved"])
                s["inad_cited"] += bool(run["inadmissible_cited"])
            jf.write(json.dumps(rec) + "\n")
            print(f"{q['q_id']} {q['ticker']:<6} {q['window'][0][:7]}.."
                  f"{q['window'][1][:7]} "
                  f"A2={rec['modes']['A2']['letter'] or '?'}"
                  f"{'OK' if rec['modes']['A2']['correct'] else 'X'} "
                  f"A3={rec['modes']['A3']['letter'] or '?'}"
                  f"{'OK' if rec['modes']['A3']['correct'] else 'X'} "
                  f"gold={q['gold_answer']} inad_ret: "
                  f"A2={len(rec['modes']['A2']['inadmissible_retrieved'])}"
                  f" A3={len(rec['modes']['A3']['inadmissible_retrieved'])}")

    print("\n== ADQAB pilot (A2 as-of slice vs A3 admissible window) ==")
    for m, s in stats.items():
        n2 = s["n"]
        print(f"  {m}: correct {s['correct']}/{n2} "
              f"({s['correct']/n2:.2f}); runs with inadmissible docs "
              f"retrieved {s['inad_ret']}/{n2}, cited "
              f"{s['inad_cited']}/{n2}")
    print(f"elapsed {time.time()-t0:.0f}s; journal: {journal}")


if __name__ == "__main__":
    main()
