# Serviced-office contract: recorded IFRS 16 retrieval evaluation

Dataset: [`ifrs16_serviced_office_eval.json`](ifrs16_serviced_office_eval.json). One full-contract question, independently retrieved from each configured index. The supplied bot response is preserved, but these scores do not directly assess its factual accuracy. See the [dataset guide](ifrs16_serviced_office_dataset.md).

<!-- EVAL_RESULTS_START -->
Last run (UTC): 2026-10-22T12:44:40.085742+00:00

Dataset cases: 1. Judge: `gpt-6-luna`. Threshold: 0.7.

| FAISS index | Contextual Recall | Contextual Precision | Contextual Relevancy | Status |
|---|---|---|---|---|
| IFRS A | 0.5455 (1/1) | 0.8972 (1/1) | 0.5500 (1/1) | completed |
| IFRS B | 0.3333 (1/1) | 0.3408 (1/1) | 0.5417 (1/1) | completed |
| IFRS C | 0.5000 (1/1) | 0.5514 (1/1) | 0.8636 (1/1) | completed |
| EY | 0.5000 (1/1) | 0.3388 (1/1) | 0.7000 (1/1) | completed |
| PwC | 0.8333 (1/1) | 0.8501 (1/1) | 0.6613 (1/1) | completed |

Scores are means on a 0–1 scale; parentheses show scored/targeted cases. Partial/error results are not a passing evaluation.


<!-- EVAL_RESULTS_END -->

## Interpretation of this recorded run

All fifteen metric evaluations completed without API or metric errors. The overall evaluation did not pass because every index had at least one score below 0.70. CLI exit code 1 indicates these threshold failures, rather than an execution failure.

- IFRS A returned useful material near the top (precision 0.8972), but the reference required evidence beyond those retrieved passages (recall 0.5455).
- IFRS B and EY received low ranking scores (0.3408 and 0.3388). The judge cited modification and other adjacent-topic examples interspersed with useful guidance.
- IFRS C had high contextual relevancy (0.8636) but incomplete reference coverage (recall 0.5000).
- PwC covered the most reference content (recall 0.8333) with strong ranking (precision 0.8501), but relevancy was 0.6613.

These are observations from one contract and one judge execution, not estimates of average corpus performance. Some explanations are subjective; the detailed JSON includes the exact contexts and reasons for review. For example, the PwC recall judge specifically penalised the reference's request to resolve conflicting notice/evacuation clauses and not invent values, which were not present in the corpus excerpts. Those are contract-assessment cautions in the drafted reference. Treat such deductions as a reference-design limitation as well as a retrieval finding; do not blindly tune retrieval to satisfy them.

No retrieval settings, thresholds, model names, runtime checks or source indexes were altered to improve these scores. Before removing checks, review the source passages, obtain expert approval of the reference and test a wider set of contracts. Full-input retrieval may retrieve different material from a focused lease-term or component-allocation question; that would be a separate experiment.

Detailed report: [`reports/ifrs16_serviced_office_results.json`](reports/ifrs16_serviced_office_results.json). The report includes the retrieved source passages.
