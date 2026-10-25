# IFRS 15 principal-versus-agent starter dataset

Two ready-to-run files use the existing evaluation schema:

| Dataset | Cases | Indexes per case | Case/index pairs | Requested metric results |
|---|---:|---:|---:|---:|
| `eval_dataset.json` | 1 | 5 | 5 | 15 |
| `ifrs15_principal_agent_regression.json` | 16 | 5 | 80 | 240 |

The first file keeps your exact question and the supplied bot answer as `actual_output`. Its `expected_output` is an independently drafted reference. The extended file includes that same case plus focused follow-up questions. Unanswered follow-ups do not invent bot responses. These are source-checked starter references, **not accountant-approved gold answers**; obtain expert sign-off before using their scores as an acceptance benchmark.

Every case explicitly targets `IFRS A`, `IFRS B`, `IFRS C`, `EY`, and `PwC`. The runner retrieves context from each index separately and never mixes index contexts for these metrics. It uses the same reference across indexes, allowing a consistent topic-coverage comparison. A specialised corpus may legitimately omit a particular illustration or a cross-standard distinction; low recall then indicates missing corpus coverage, rather than necessarily a broken retriever. Review the retrieved chunks and corpus scope before interpreting a score. Do not copy expected answers into retrieval context or insert web evidence into the indexes just to improve the benchmark.

## Run from the project root

With the project virtual environment active:

```bash
# Readiness check; no OpenAI requests or quality scores.
python3.11 evaluation/run_eval.py --inventory-only

# Your exact question, independently evaluated against all five indexes.
python3.11 evaluation/run_eval.py --dataset evaluation/eval_dataset.json

# Optional extended regression run, also against all five indexes.
python3.11 evaluation/run_eval.py \
  --dataset evaluation/ifrs15_principal_agent_regression.json \
  --output evaluation/reports/ifrs15_principal_agent_regression.json
```

Both scored commands update the latest-results section of `EvalReadMe.md`; use `--readme evaluation/reports/ifrs15_regression.md` for a separate extended Markdown report if desired. Each metric may require multiple judge requests, so 240 metric results do **not** mean exactly 240 API requests. The extended run costs more than the single-question run. No scored evaluation was run while creating these files.

## Coverage and reference provenance

The last part of each case ID identifies the tested issue. Reference paragraphs are supplied here, outside the answer strings, to avoid requiring a judge to find a bibliography in every retrieved chunk. Sources were checked on 22 October 2026; source editions are identified below.

| Case suffix | Retrieval target | Source |
|---|---|---|
| `001-original-query` | Overall principal test | IFRS 15 B34–B37A; source 1 and source 2 |
| `002-specified-item` | Identify the distinct promised item | B34–B34A; source 1 |
| `003-indicators` | Three supporting indicators | B37; source 2 |
| `004-not-a-checklist` | Indicators cannot replace control | BC385H; source 3 |
| `005-pricing-alone` | Pricing discretion is not conclusive | B37(c); source 2 |
| `006-inventory-risk` | Risk before and after transfer | B37(b); source 1 |
| `007-momentary-title` | Brief title does not establish control | B35; source 1 |
| `008-subcontracted-service` | Service-right control and subcontracting | B35–B35A(b); source 1 |
| `009-gross-versus-net` | Revenue presentation follows the role | B35B–B36; source 1; BC385J(c), source 3 |
| `010-mixed-roles` | Separate assessment of specified items | B34; source 1 |
| `011-ifrs10-confusion` | Revenue analysis versus consolidation | B34–B38, source 1; source 5 for IFRS 10 scope |
| `012-example46a` | Office maintenance services | IE238A–IE238G; source 4 |
| `013-example47` | Airline-ticket rights | IE239–IE243; source 4 |
| `014-example48a` | Recruitment work and database access | IE248A–IE248F; source 4 |
| `015-example-number-check` | Correct illustration identifiers | Examples 46, 46A and 47; sources 3 and 4 |
| `016-credit-risk` | Removal of the old credit-risk indicator | BC385J(d); source 3 |

1. [AASB 15, December 2022 compilation incorporating IFRS 15](https://aasb.gov.au/admin/file/content105/c9/AASB15_12-14_COMPdec22_01-23.pdf), Appendix B. Only the corresponding IFRS paragraphs are used; Australian-specific paragraphs are excluded. This is an identified historical compilation, not a claim that it is the current Australian compilation.
2. [IFRS Foundation: final Software Reseller agenda decision, published May 2022 in the April 2022 IFRIC Update](https://www.ifrs.org/news-and-events/updates/ifric/2022/ifric-update-april-2022/).
3. [IFRS 15 Basis for Conclusions, January 2022 edition](https://aasb.gov.au/admin/file/content105/c9/IFRS15_BC_1-22.pdf), BC385H–BC385O.
4. [IFRS Foundation illustrative-example amendments, April 2016, hosted by AASB](https://www.aasb.gov.au/admin/file/content105/c9/IFRS15_IE_04-16.pdf). Example labels were also cross-checked against [IASB staff paper 6B, February 2024](https://www.ifrs.org/content/dam/ifrs/meetings/2024/february/iasb/ap6b-ifrs-15-pir-principal-vs-agent-considerations.pdf), paragraph 41. The staff paper is explanatory material, not an authoritative amendment.
5. [IFRIC Update June 2026: Control Assessment for a Single-investor Fund (IFRS 10)](https://www.ifrs.org/news-and-events/updates/ifric/2026/ifric-update-june-2026/). This discussion is used only to identify consolidation/investee scope; its tentative discussion is not treated as a new requirement for IFRS 15.

## How to interpret the supplied bot answer

The answer's principal definition captures the core control concept, but its illustration labels are unreliable: **46A is office maintenance; 47 is airline tickets**. The reference answers do not repeat those label errors. Indicators should support the control conclusion, rather than become independent mandatory conditions. The IFRS 10 statement should not replace the IFRS 15 revenue framework. These issues are covered by dedicated regression questions.

The existing runner measures **Contextual Recall, Contextual Precision and Contextual Relevancy**. Those scores concern retrieved evidence; they do **not** directly grade the truth or faithfulness of the supplied bot answer. Saving it as `actual_output` preserves the observation, but cannot by itself make the retrieval metrics detect its incorrect labels. Final-answer factual accuracy requires a separate answer-correctness/faithfulness evaluation or expert review. The extended questions instead test whether each index retrieves evidence for the corresponding correct distinctions.
