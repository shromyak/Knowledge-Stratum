# Prototype results (A4 vs. A5 parity)

**Run date:** 2026-10-21. **Corpora:** synthetic Req (§8.3, 10 queries) and Strategy Validator (§7, 5 queries on a real epoch subgraph).

## Parity report

| Metric | A4 (contract service) | A5 (manifest-as-data, SQLite) |
|---|---|---|
| Admissible contexts, divergences | 0 / 10 | 0 / 10 |
| fact_correctness (vs. generator gold) | 1.0 | 1.0 |
| evidential_support | 1.0 | 1.0 |
| correct_abstention | 1.0 | 1.0 |
| membership_violations_flagged | 1 (Q10) | 1 (Q10) |

**Parity conclusion:** membership behavior is identical — a manifest stored as data is sufficient; a stratum is a contract, not a separate product (consistent with the expectation for condition A5 in §8.1).

## Strategy Validator (sv corpus)

| Query | Verdict | What it demonstrates |
|---|---|---|
| QS1 | contradicts | Centralized strategy vs. an Anarchic epoch frame |
| QS2a | consistent | Dynastic-order strategy vs. Rigid_Hierarchical (taxonomy rev1) |
| QS2b | contradicts | **Same data, taxonomy rev2** — FRANCE_RESTORATION reclassified to Legal; the verdict flips (T5 control) |
| QS3 | insufficient evidence | Required marker has no source (§8.5 control) |
| QS4 | filtered out | Retrospective marker (available_at=10) excluded at T=5 |

A4/A5 parity on sv: 5/5, divergent=0, fact=1.0 — the schema generalizes to semantic objects (epochs, markers, taxonomies), not only files.

## Demonstrated mechanics

- **Section 3.2 counterexample confirmed constructively:** `B_counter = {XA-rev1, XB-rev1}` (approved at t=5) is recovered by the manifest; latest-as-of(T=5) returns `XA-rev2` — no single temporal slice restores the membership.
- **Contract checker** rejects a fabricated manifest with specific codes (`MEMBER_MISSING`, `HASH_MISMATCH`, `ENDPOINT_EXTERNAL`, `AVAILABILITY_VIOLATION`, `CONFLICT`); during construction it caught a real corpus bug (stale edges to a superseded revision) — a live illustration of change control.
- **Q8 (record_query):** missing archive → "no record exists", not a reconstruction.
- **Q9 (availability):** a member with `available_at=4` is excluded in "as available at T=2" mode.
- **Q10 (mixed_context):** a genuine but non-member revision → `MEMBERSHIP_VIOLATION`.

## Real-LLM runs (src/run_llm.py)

The suite was also run with live local models (LM Studio, OpenAI-
compatible endpoint; journal `runs/req_llm.jsonl`, `model_id` recorded):

| Model (local) | fact_correctness | Notes |
|---|---|---|
| `openai/gpt-oss-20b` | 1.0 (10/10) | cites member revisions; correct abstentions |
| `meta-llama-3.1-8b-instruct` | 0.9 | one abstention on a membership-enumeration query |
| `ollama/llama3.2` (3B) | 0.4 | over-abstains; occasionally cites edge revs instead of member revs |

Observations: all enforcement happens at candidate generation (the model
never sees non-members), and `MEMBERSHIP_VIOLATION` in the journal is
produced only by the deliberate control query. Small models fail through
citation discipline/abstention, not through inadmissible access — an
informative measurement channel in its own right.

## ECT-QA pilot (Phase 4 / Q9): A2 vs A3

Benchmark: `austinmyc/ECT-QA` (earnings-call transcripts, 2020–2023
subset). Sample: 30 questions (20 answerable + 10 unanswerable) over 11
companies, 176 docs; model `openai/gpt-oss-20b` via LM Studio; journal
`runs/ectqa_llm.jsonl`. Modes: **A2** = as-of slice (company docs with
quarter ≤ window end) vs **A3** = admissible window (gold temporal
scope from `evidence_list`).

| Metric | A2 (as-of slice) | A3 (admissible window) |
|---|---|---|
| Answer correctness | 29/30 (0.97) | 29/30 (0.97) |
| Runs retrieving docs outside the window | 15/30 | 0/30 |
| Runs citing docs outside the window | 1/30 | 1/30 |

Findings (honest reading):

- **No quality gap on this sample** — admissibility filtering did not
  cost answer correctness (recall loss ≈ 0), but half of A2 runs
  carried inadmissible-period documents: audit exposure without a
  quality signal.
- **Hallucinated citations observed (ECT11):** in *both* modes the
  model cited `EPAM_US-2021-q3/q4` — documents it was never shown.
  Correct answer + invalid citations = an audit failure invisible to
  answer-quality metrics; only citation-vs-membership checks catch it.
- **Hallucination probe (ECT28, `unanswerable|nonfact`):** the model
  fabricated guidance numbers in both modes — the only incorrect run.
- Scope limit: ECT-QA has no stratum/membership annotations, so this
  tests temporal admissibility only, not arbitrary approved
  membership — auxiliary evidence for the A2-vs-A3 trade-off.

## ADQAB pilot (Phase 4 / Q9, second dataset)

Benchmark: `kwunhang/TA-RAG` DQABench — 27,037 dated financial-news
docs, 525 MCQA questions with explicit `plot_time_bounds`. Sample: 30
questions, `openai/gpt-oss-20b` via LM Studio, lexical retrieval over
excerpts, deterministic letter grading; journal `runs/adqab_llm.jsonl`.

| Metric | A2 (as-of slice) | A3 (admissible window) |
|---|---|---|
| Overall correctness | 8/30 (0.27) | 11/30 (0.37) |
| Correctness among answered | 8/14 (0.57) | 11/16 (0.69) |
| Runs retrieving out-of-window docs | 13/30 | 0/30 |
| Runs citing out-of-window docs | 1/30 | 0/30 |
| Divergent verdicts | — | all 3 flips favor A3 (ADQ03, ADQ23, ADQ25) |

Findings:

- A3 ≥ A2 on every measure on this harder benchmark (MCQA generated
  from price plots): +10 points overall, +12 among answered runs, and
  every divergent answer flipped toward the admissible window.
- ~half of runs abstained ("insufficient evidence") in *both* modes —
  a retriever-limitation signal (lexical excerpts vs the paper's
  embedding pipeline), not an admissibility effect; measured, not
  hidden.
- Same scope caveat as ECT-QA: publish-date windows test temporal
  admissibility, not arbitrary approved membership.

## Stated limits of the result

- The result concerns the executability of the contract and carrier parity; H2–H4 remain hypotheses — the generator is deterministic and no LLM answer quality was measured.
- The semantic verifier is a stand-in (substring / edge-existence); the NLI/self-critique hook is marked in `engine.verify_claims`.
- The A5 carrier is SQLite (a DVC/LakeFS commit analogue); a bitemporal implementation (XTDB) changes the carrier, not the contract.

## Reproduction

```bash
python3 src/run_all.py      # corpora → checks → A4/A5 → parity_report.json
python3 tests/test_smoke.py # 5 checks
```
