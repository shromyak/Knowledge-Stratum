"""ECT-QA pilot adapter (Phase 4 / Q9): temporal admissibility A2 vs A3.

Downloads the HF dataset austinmyc/ECT-QA (plain JSON via resolve URLs),
samples questions, and materializes a small corpus where each
transcript is a Revision tagged with a quarter index as its temporal
coordinate.

Honest scope (per Prototype_Plan): this benchmark tests TEMPORAL
admissibility (does retrieval stay inside the question's time window /
does it use inadmissible periods), not arbitrary approved membership —
the dataset has no stratum annotations. It is auxiliary evidence for
A2-vs-A3 trade-offs only.
"""
import json
import os
import random
import re
import urllib.request

HF = ("https://huggingface.co/datasets/austinmyc/ECT-QA/resolve/main/")
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "data", "ectqa", "raw")
DOCS = os.path.join(RAW, "docs")


def fetch(path):
    """Download a dataset file into the local cache; return its path."""
    dst = os.path.join(RAW, path.replace("/", "_"))
    if not os.path.exists(dst):
        url = HF + urllib.request.quote(path)
        with urllib.request.urlopen(url, timeout=120) as r:
            data = r.read()
        with open(dst, "wb") as f:
            f.write(data)
    return dst


def load_questions(name="local_questions_old"):
    path = fetch(f"questions/{name}.json")
    return json.load(open(path))


def tindex(year, quarter):
    """Quarter index: 2020q1 -> 8081, ... 2024q4 -> 8096."""
    return int(year) * 4 + int(quarter.lstrip("qQ"))


def doc_meta(fname):
    """'energy-EOG-2021-q4.json' -> sector, ticker, year, quarter, t."""
    base = fname.rsplit("/", 1)[-1].replace(".json", "")
    sector, ticker, year, quarter = base.split("-")
    return {"doc_id": base, "sector": sector, "ticker": ticker,
            "year": year, "quarter": quarter,
            "t": tindex(year, quarter)}


def sample_questions(n_answerable=20, n_unans=10, seed=7):
    qs = load_questions()
    ev = [q for q in qs if q["answer"] != "unanswerable"
          and q["evidence_list"]]
    un = [q for q in qs if q["answer"] == "unanswerable"]
    rnd = random.Random(seed)
    rnd.shuffle(ev)
    rnd.shuffle(un)
    picked = ev[:n_answerable] + un[:n_unans]

    queries = []
    tickers = set()
    for i, q in enumerate(picked, 1):
        evl = q["evidence_list"]
        if evl:
            ts = [tindex(e["year"], e["quarter"]) for e in evl]
            win = [min(ts), max(ts)]
            tk = evl[0]["sector"] + "-" + \
                evl[0]["ect_filename"].split("-")[1]
            gold_docs = [e["ect_filename"].replace(".json", "")
                         for e in evl]
        else:
            # unanswerable questions carry no evidence; they are
            # out-of-scope probes -> admissible window empty
            win, tk, gold_docs = None, None, []
        queries.append({
            "q_id": f"ECT{i:02d}", "type": "ect_qa",
            "question": q["question"], "gold_answer": q["answer"],
            "reasoning_type": q["reasoning_type"],
            "question_type": q["question_type"],
            "company_key": tk, "window": win,
            "gold_docs": gold_docs})
        if tk:
            tickers.add(tk)
    return queries, tickers


def download_docs(tickers, years=("2020", "2021", "2022", "2023")):
    """Fetch all 'old' docs (2020-2023) for the sampled companies."""
    metas = []
    for tk in sorted(tickers):
        sector, ticker = tk.split("-")
        for y in years:
            for qn in range(1, 5):
                fname = f"data/old/{sector}-{ticker}-{y}-q{qn}.json"
                try:
                    p = fetch(fname)
                except Exception:
                    continue
                m = doc_meta(fname)
                m["path"] = p
                metas.append(m)
    return metas


def build(n_answerable=20, n_unans=10, seed=7):
    """Materialize the pilot corpus; returns (queries, doc_metas)."""
    os.makedirs(DOCS, exist_ok=True)
    queries, tickers = sample_questions(n_answerable, n_unans, seed)
    metas = download_docs(tickers)
    outp = os.path.join(RAW, "pilot_queries.jsonl")
    with open(outp, "w") as f:
        for q in queries:
            f.write(json.dumps(q) + "\n")
    print(f"sampled {len(queries)} questions over {len(tickers)} "
          f"companies; {len(metas)} docs downloaded -> {outp}")
    return queries, metas


STOP = set("the a an of in on for to and or is are was were be been by "
           "at as it its this that with from what which when how did "
           "does do each per vs than between during over".split())


def qterms(question):
    return [w for w in re.findall(r"[a-z0-9]+", question.lower())
            if w not in STOP and len(w) > 2]


def doc_text(meta):
    d = json.load(open(meta["path"]))
    return d.get("cleaned_content") or d.get("raw_content") or ""


def retrieve(question, metas, k=4, max_chars=6000):
    """Lexical retrieval: score docs by question-term hits, return
    (doc_id, excerpt) pairs — excerpt = best-matching text windows,
    not whole transcripts (context budget)."""
    terms = qterms(question)
    scored = []
    for m in metas:
        text = doc_text(m).lower()
        s = sum(text.count(t) for t in terms)
        if s:
            scored.append((s, m))
    scored.sort(key=lambda x: -x[0])
    out = []
    for s, m in scored[:k]:
        text = doc_text(m)
        # pick up to 3 best ~1500-char windows by term density
        chunks = [text[i:i + 1500] for i in range(0, len(text), 1200)]
        ranked = sorted(
            chunks,
            key=lambda c: -sum(c.lower().count(t) for t in terms))
        excerpt = "\n...\n".join(ranked[:3])[:max_chars]
        out.append((m["doc_id"], excerpt))
    return out
