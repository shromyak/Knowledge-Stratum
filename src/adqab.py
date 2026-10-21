"""ADQAB/DQABench pilot adapter (Phase 4 / Q9, second dataset).

Source: github.com/kwunhang/TA-RAG (DQABench) — 27k real+synthetic
financial-news docs with publish dates + 525 MCQA questions with
explicit plot_time_bounds. Temporal admissibility pilot A2 vs A3 —
same honest scope as the ECT-QA pilot: the benchmark tests temporal
relevance, not arbitrary approved membership.
"""
import json
import os
import random
import re
import urllib.request

GH = "https://media.githubusercontent.com/media/kwunhang/TA-RAG/main/"
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "data", "adqab", "raw")


def fetch(path):
    os.makedirs(RAW, exist_ok=True)
    dst = os.path.join(RAW, path.replace("/", "_"))
    if not os.path.exists(dst):
        url = GH + urllib.request.quote(path)
        with urllib.request.urlopen(url, timeout=300) as r:
            data = r.read()
        with open(dst, "wb") as f:
            f.write(data)
    return dst


def load_questions():
    return json.load(open(fetch("DQABench/dqabench_MCQA.json")))


def load_dates():
    """doc_id -> publish_date (ISO yyyy-mm-dd)."""
    import csv
    dates = {}
    for name in ("C_real_metadata.csv", "C_synth_metadata.csv"):
        p = fetch(f"DQABench/external_metadata/{name}")
        with open(p) as f:
            for row in csv.DictReader(f):
                # real: publish_date; synthetic: derived_publish_date
                dates[row["global_id"]] = (
                    row.get("publish_date")
                    or row.get("derived_publish_date"))
    return dates


def load_docs():
    """doc_id -> text (lazy-ish: one pass over 127MB jsonl)."""
    docs = {}
    with open(fetch("DQABench/C_final.jsonl")) as f:
        for line in f:
            d = json.loads(line)
            docs[d["id"]] = d["text"]
    return docs


def sample_questions(n=30, seed=11):
    qs = load_questions()
    rnd = random.Random(seed)
    rnd.shuffle(qs)
    out = []
    for i, q in enumerate(qs[:n], 1):
        b = q["plot_time_bounds"]
        out.append({
            "q_id": f"ADQ{i:02d}", "type": "adqab_mcqa",
            "question": q["question"],
            "choices": q["choices"],
            "gold_answer": q["correct_answer_key"],
            "ticker": q["ticker"],
            "granularity": q["query_type_info"]["granularity"],
            "window": [b["start_date"], b["end_date"]],
        })
    return out


STOP = set("the a an of in on for to and or is are was were be been by "
           "at as it its this that with from what which when how did "
           "does do each per vs than between during over was will "
           "would could general movement trend stock price".split())


def qterms(question):
    return [w for w in re.findall(r"[a-z0-9]+", question.lower())
            if w not in STOP and len(w) > 2]


def retrieve(question, ticker, docs, metas, k=4, max_chars=2500):
    """Lexical retrieval over candidate metas; returns
    (doc_id, date, excerpt) triples (excerpt: best windows)."""
    terms = qterms(question)
    tick_re = re.compile(r"\b" + re.escape(ticker) + r"\b")
    scored = []
    for m in metas:
        text = docs.get(m["doc_id"], "")
        if not tick_re.search(text):
            continue
        low = text.lower()
        s = sum(low.count(t) for t in terms)
        scored.append((s, m, text))
    scored.sort(key=lambda x: -x[0])
    out = []
    for s, m, text in scored[:k]:
        chunks = [text[i:i + 1200] for i in range(0, len(text), 1000)]
        ranked = sorted(
            chunks,
            key=lambda c: -sum(c.lower().count(t) for t in terms))
        excerpt = "\n...\n".join(ranked[:2])[:max_chars]
        out.append((m["doc_id"], m["date"], excerpt))
    return out
