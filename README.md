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
  `rev_id ∈ M_B`; run journal; a deterministic `TemplateGenerator`
  (replaceable by a real model); claim verification (identifier check +
  a semantic-support stand-in for an entailment/verifier pass).
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
  mechanics, not LLM behavior. Testing hypothesis H2 requires a run
  with a real model.
- Semantic claim verification is a stand-in (substring /
  edge-existence); the hook for an NLI/self-critique verifier is
  `engine.verify_claims`.
- The prototype does not prove the empirical benefit of strata
  (H2–H4) — only the executability of the contract and the parity of
  manifest carriers.
- A5-lite (SQLite) is not a bitemporal database; the carrier was chosen
  per the article's logic: a commit/manifest stored as data — the same
  contract.
