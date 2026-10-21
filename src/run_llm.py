"""Run the suite with a real LLM as the generator.

Usage:
    python3 src/run_llm.py ollama:llama3.1:8b
    python3 src/run_llm.py openai:gpt-4o-mini      # needs OPENAI_API_KEY
    python3 src/run_llm.py ollama:qwen2.5:7b --corpus sv

Journal -> runs/{corpus}_llm.jsonl ; gold evaluation printed.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import corpus_req
import corpus_sv
from asof_store import load_strata_to_db
from engine import run_suite
from llm import make_generator
from model import Store, read_jsonl
from parity import evaluate_run, metrics

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    spec = sys.argv[1] if len(sys.argv) > 1 else "ollama:llama3.1:8b"
    name = "sv" if "--corpus" in sys.argv and "sv" in sys.argv else "req"
    root = (corpus_sv.generate() if name == "sv"
            else corpus_req.generate())
    store = Store(root)
    queries = read_jsonl(os.path.join(root, "queries.jsonl"))
    load_strata_to_db(store, os.path.join(root, "a5.db"))

    gen, model_id = make_generator(spec)
    out = os.path.join(BASE, "runs")
    os.makedirs(out, exist_ok=True)
    journal = os.path.join(out, f"{name}_llm.jsonl")
    runs = run_suite(store, queries, "A4", journal,
                     gen=gen, gen_id=model_id)

    qmap = {q["q_id"]: q for q in queries}
    print(f"model: {model_id}")
    for r in runs:
        ev = evaluate_run(r, qmap[r["q_id"]])
        print(f"  {r['q_id']}: ok={ev['ok']} flags={r['flags']} "
              f"answer={r['answer'][:90]!r}")
    print(json.dumps(metrics(runs, queries), indent=2))
    print("journal:", journal)


if __name__ == "__main__":
    main()
