# Knowledge-Stratum Prototype

Minimal auditable artifact accompanying the article *Beyond Time Slices:
Configuration Integrity of Knowledge Strata in Financial RAG Systems*.
It demonstrates conditions A4 (a stratum as a contract-checking service)
and A5 (the same manifest stored as data) on two corpora: the synthetic
requirements scenario (Section 8.3) and a Strategy Validator
illustration (Section 7).

## Corpora

- **req** (`src/corpus_req.py`): synthetic requirements project — two
  strata differing in requirement text, edge targets, and test set; the
  Section 3.2 counterexample; 10 queries with generator-defined gold.
- **sv** (`src/corpus_sv.py`): Strategy Validator illustration — a chain
  of 8 real epochs from the epoch taxonomy (France, exported from a
  ~310-node graph), 5 society types with markers, two taxonomy
  revisions (T5: FRANCE_RESTORATION reclassified), V(S,B,M) verdicts,
  and Section 8.5 control cases (a marker without a source, a
  retrospective marker excluded in "as available at T" mode).

## What is implemented

- **Data model** (Table 3 of the article): `Entity`, `Revision`,
  `EdgeRevision`, `Stratum` (manifest + contract + approval),
  `AnalysisRun`, `Claim` — JSONL records + content-addressed blobs
  (sha256).
- **Contract checker** (`src/contract.py`): membership existence, hash
  integrity, admissible member types, edge endpoints / external
  dependencies, `available_at` temporal constraints, contradiction
  rules.
- **Run pipeline** (`src/engine.py`): candidate generation restricted to
  `rev_id ∈ M_B`; run journal; a deterministic `TemplateGenerator` or a
  real LLM (`src/llm.py`, `src/run_llm.py`); claim verification
  (identifier check + a semantic-support stand-in for an
  entailment/verifier pass).
- **A5-lite carrier** (`src/asof_store.py`): the manifest persisted as
  SQLite rows — the git-commit analogue of DVC/LakeFS per the article's
  framing.
- **Parity harness** (`src/parity.py`): the same query suite through A4
  and A5; divergence of admissible contexts must be zero.

## Reproduction

```bash
cd prototype
python3 src/run_all.py        # full run: corpora -> checks -> A4/A5 -> parity
python3 tests/test_smoke.py   # tests (no dependencies)
```

### Running with a real LLM

`src/run_llm.py` replaces `TemplateGenerator` with a live model. The
model sees only the admissible fragments (candidate generation is still
restricted to `rev_id ∈ M_B`); it must cite revision ids, and any
citation outside membership is flagged `MEMBERSHIP_VIOLATION` in the
journal — `model_id`, output, citations, and flags are all recorded.

```bash
# LM Studio (server at localhost:1234, OpenAI-compatible):
OPENAI_BASE_URL=http://localhost:1234/v1 OPENAI_API_KEY=lm-studio \
  python3 src/run_llm.py openai:openai/gpt-oss-20b
# any loaded LM Studio model id works, e.g.
#   openai:meta-llama-3.1-8b-instruct

# Ollama (server at localhost:11434):
python3 src/run_llm.py ollama:llama3.2

# OpenAI or another OpenAI-compatible provider:
OPENAI_API_KEY=sk-... python3 src/run_llm.py openai:gpt-4o-mini

# Strategy Validator corpus:
python3 src/run_llm.py openai:openai/gpt-oss-20b --corpus sv
```

Journal -> `runs/{req,sv}_llm.jsonl`; the same gold evaluation and
Table 6 metrics are printed.

### ECT-QA pilot (external benchmark, A2 vs A3)

`src/run_ectqa.py` downloads a sample of `austinmyc/ECT-QA` (plain
JSON from Hugging Face) and compares an as-of temporal slice (A2) with
admissible-window retrieval (A3): correctness vs gold, inadmissible-doc
usage, citation violations. Journal -> `runs/ectqa_llm.jsonl`.

```bash
OPENAI_BASE_URL=http://localhost:1234/v1 OPENAI_API_KEY=lm-studio \
  python3 src/run_ectqa.py openai:openai/gpt-oss-20b \
  [--n-ans 20] [--n-unans 10] [--k 4]
```

`src/run_adqab.py` does the same A2/A3 comparison on a second
benchmark, `kwunhang/TA-RAG` DQABench (27k dated news docs, MCQA
questions with `plot_time_bounds`; deterministic letter grading).
Journal -> `runs/adqab_llm.jsonl`.

```bash
OPENAI_BASE_URL=http://localhost:1234/v1 OPENAI_API_KEY=lm-studio \
  python3 src/run_adqab.py openai:openai/gpt-oss-20b \
  [--n 30] [--k 6] [--seed 11]
```

Artifacts:

- `data/{req,sv}/` — generated corpora (deterministic, byte-for-byte)
- `runs/{req,sv}_{a4,a5}.jsonl` — run journals
- `checks/<stratum>.json` — contract-check reports
- `checks/{req,sv}_parity_report.json`, `checks/summary.json` — parity
  reports with metrics

## What is demonstrated

1. The Section 3.2 counterexample: stratum `B_counter = {XA-rev1,
   XB-rev1}` approved at t=5; latest-as-of returns `XA-rev2` — the
   configuration cannot be reconstructed by any temporal slice, only by
   a stored manifest.
2. A4/A5 parity: identical membership behavior — a stratum is a
   contract, not a product.
3. Auditability: membership violations are flagged, a missing archive
   yields "no record exists", members unavailable at T are excluded.
4. T5 control: a taxonomy revision alone flips a strategy verdict
   (consistent → contradicts) on unchanged epoch data.

## Limitations (stated openly)

- `TemplateGenerator` is deterministic; it demonstrates audit
  mechanics, not LLM behavior. `src/run_llm.py` runs a real model
  through the same journal/metrics path (LM Studio `gpt-oss-20b`
  reached fact_correctness 1.0 on the 10-query req suite; llama3.2:3B
  over-abstains at 0.4 — small-model citation discipline, not an
  enforcement difference). LLM runs measure the pipeline's audit
  mechanics end-to-end; they do not by themselves test H2.
- Semantic claim verification is a stand-in (substring /
  edge-existence); the hook for an NLI/self-critique verifier is
  `engine.verify_claims`.
- The prototype does not prove the empirical benefit of strata
  (H2–H4) — only the executability of the contract and the parity of
  manifest carriers.
- A5-lite (SQLite) is not a bitemporal database; the carrier was chosen
  per the article's logic: a commit/manifest stored as data — the same
  contract.
