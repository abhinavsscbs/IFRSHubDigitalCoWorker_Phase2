# Evaluation guide and measured results

This is the evaluation reference for **IFRSHubDigitalCoWorker_Phase2**. Read [README.md](README.md) for architecture and [RAGReadme.md](RAGReadme.md) for the runtime pipeline. Evaluation uses the real per-index retrieval implementation, but runs separately from Flask requests.

## What is evaluated

The runner computes DeepEval **Contextual Recall**, **Contextual Precision** and **Contextual Relevancy** independently for each configured FAISS index, plus other LangChain `index.faiss` directories discovered below the checkout. Dependency/build folders are skipped. Indexes outside the checkout must be configured explicitly.

| Metric | Inputs used for judgement | Meaning |
|---|---|---|
| Contextual Recall | Question, reference answer, retrieved context | How much reference information the retrieved evidence supports |
| Contextual Precision | Question, reference answer, ordered context | Whether useful chunks rank before irrelevant chunks |
| Contextual Relevancy | Question, retrieved context | How relevant the retrieved information is to the question |

Each metric is on a 0–1 scale; higher is better. Recall/precision use `expected_output`, not the bot's own answer as ground truth. The optional `actual_output` preserves the observed response but does not turn these metrics into answer-correctness, faithfulness, prompt-injection, or legal/accounting review scores.

The evaluation point is **per-index retrieval before the cross-index document selector**. It does not run the initial semantic relevance gate, the 55-preview selector, main generation or exception workflow. It calls `fetch_docs`: up to 50 candidates, the configured top percentile, source tags and the original ranked order. Different indexes are never merged into a metric's context.

This distinction matters: an offline score cannot be described as a measured quality result for the final multi-corpus answer, or as proof that a runtime guardrail can be removed.

## Available datasets

| Dataset | Cases | Target corpora | Intended use |
|---|---:|---|---|
| [`evaluation/eval_dataset.json`](evaluation/eval_dataset.json) | 1 | All five | Original IFRS 15 principal question, supplied answer and independent starter reference |
| [`evaluation/ifrs15_principal_agent_regression.json`](evaluation/ifrs15_principal_agent_regression.json) | 16 | All five | Control, indicators, role distinctions and illustration-label regression |
| [`evaluation/ifrs16_serviced_office_eval.json`](evaluation/ifrs16_serviced_office_eval.json) | 1 | All five | Full serviced-office contract with its original formatted response |
| `evaluation/sample_eval_set.jsonl` | Historical | Not used by this runner | Earlier lexical/source-count baseline examples |

Dataset guides describe source checks, scope and expert-review status: [IFRS 15 guide](evaluation/ifrs15_principal_agent_dataset.md), [serviced-office guide](evaluation/ifrs16_serviced_office_dataset.md). The reference answers are source-checked starters, not accountant-approved gold standards. The supplied contract and response are intentionally part of the private project dataset; operational chat history and source corpora are excluded from Git.

### Dataset shape

The machine-readable contract is [`evaluation/eval_dataset.schema.json`](evaluation/eval_dataset.schema.json).

```json
{
  "description": "An independently reviewed evaluation set",
  "cases": [
    {
      "id": "unique-case-id",
      "question": "An accounting question or the complete contract and question",
      "expected_output": "An independently prepared reference answer",
      "actual_output": "Optional observed bot answer",
      "indexes": ["IFRS A", "IFRS B", "IFRS C", "EY", "PwC"],
      "expected_outputs": {
        "EY": "Optional reference appropriate specifically to that corpus"
      }
    }
  ]
}
```

`id`, `question` and `expected_output` are required nonempty strings. IDs must be unique. Omitted/empty `indexes` applies a case to every inventoried index, including discovered indexes. Explicit lists select named indexes; unknown names are rejected. `expected_outputs` can override the shared reference for one corpus. A discovered index is named `discovered:relative/path`.

Do not populate the retrieved context with the reference answer. The runner must obtain context from FAISS. Align references with corpus scope, distinguish accounting requirements from facts already supplied by the user, and have an expert approve the benchmark. A specialised corpus can legitimately lack an illustration or detailed rule present in another source.

## Install and check readiness

Use Python 3.11 in the project virtual environment:

```bash
source .venv/bin/activate
python3.11 -m pip install -r evaluation/requirements.txt
python3.11 evaluation/run_eval.py --inventory-only
```

Inventory makes no embedding or judge requests. It can still refresh the latest-results table with `not_run` statuses; that is a readiness report, not a new quality measurement. To preserve the root score table during a readiness check, pass separate paths:

```bash
python3.11 evaluation/run_eval.py --inventory-only \
  --output evaluation/reports/inventory.json \
  --readme evaluation/reports/inventory.md
```

Real evaluation requires the server-side `OPENAI_API_KEY`, compatible index artifacts/manifests and explicit trust for your own local pickle files. See the architecture guide for index rebuilding. The source repository excludes corpus artifacts and detailed context-bearing JSON reports; provision the former and regenerate the latter locally.

## Run a scored evaluation

Original principal question:

```bash
python3.11 evaluation/run_eval.py \
  --dataset evaluation/eval_dataset.json \
  --output evaluation/reports/principal_results.json \
  --readme evaluation/reports/principal_results.md
```

Extended principal regression:

```bash
python3.11 evaluation/run_eval.py \
  --dataset evaluation/ifrs15_principal_agent_regression.json \
  --output evaluation/reports/principal_regression.json \
  --readme evaluation/reports/principal_regression.md
```

Serviced-office contract:

```bash
python3.11 evaluation/run_eval.py \
  --dataset evaluation/ifrs16_serviced_office_eval.json \
  --output evaluation/reports/ifrs16_serviced_office_results.json \
  --readme evaluation/ifrs16_serviced_office_results.md
```

Without `--readme`, the runner updates this file's marked results section; without `--output`, it writes `evaluation/reports/deepeval_results.json`. It preserves Markdown outside the markers. Separate paths keep different experiments from replacing one another's result tables. Fixed prose around a recorded historical run should be reviewed if its table is refreshed with a different dataset/configuration.

One case across five indexes requests fifteen metric results; the 16-case regression requests 240. Each metric can make multiple judge calls, so result count is not API-request count. Real runs incur OpenAI embedding and judge usage. The query vector cache is shared across indexes within the process.

### Execution details

1. Validate the dataset and targeted index names.
2. Inventory configured/discovered indexes and check required files and embedding-manifest compatibility.
3. Read `evaluation.judge_task`, `threshold` and `max_concurrent_metrics` from configuration.
4. For each index, select applicable cases and perform real ranked retrieval.
5. Instantiate the three DeepEval metrics with the custom OpenAI judge and execute them concurrently, bounded by a semaphore. Index/case iteration is sequential.
6. Use OpenAI Responses structured parsing for judge schemas. The default judge is the `mini` task (`gpt-6-luna`); selecting `full` uses `gpt-6.1-sol` and its configured token/reasoning settings.
7. Save per-case contexts, scores, reasons, pass flags, errors and timings; compute per-index summaries and publish Markdown.

DeepEval telemetry is opted out in the evaluation modules. No full-model answer generation is required. The runner imports DeepEval only when it needs to score an eligible case.

## Status, thresholds and timing

The default threshold is **0.70**. A metric passes at or above the threshold. An index marked `completed` has finished evaluation; that label does not mean all its scores passed. `complete` and `passed` are separate report fields.

Missing keys/files/trust, incompatible manifests and unmatched cases produce `not_run`, not invented zero scores. Empty retrieved context, judge failures and invalid numeric scores remain errors. Partial means show scored/targeted case counts; incomplete/error runs cannot pass. `--inventory-only` deliberately requests no scores.

| Exit code | Meaning |
|---|---|
| `0` | All requested metrics pass, or inventory-only completed |
| `1` | All evaluations completed but at least one metric is below threshold |
| `2` | Invalid setup or an incomplete evaluation |

JSON reports include retrieval duration, metric duration and total per-case duration. Retrieval p95 is the nearest-rank statistic of that index's recorded case durations. A one-case p95 is just that case's value, not a statistically useful latency percentile. Metric time includes judge requests; it is not the user-facing RAG response time. The first index can include cold embedding/index costs while later indexes benefit from a warm query cache.

## Recorded results and their limits

The table below preserves the actual **October 22, 2026** serviced-office run using `gpt-6-luna` at threshold 0.70. It is not a new October 25 run. All fifteen metric evaluations completed; no index passed all three metrics. See the [dedicated report](evaluation/ifrs16_serviced_office_results.md) for interpretation and the [run fingerprint](evaluation/fixtures/ifrs16_serviced_office_run.json) for the dataset/report hashes.

The reference includes cautions about conflicting contract notices and not inventing values. The judge sometimes treated their absence from standard excerpts as missing evidence. That is a reference-design limitation as well as a retrieval observation. Do not attribute every recall deduction exclusively to the index, compare specialised corpora as interchangeable, or tune settings against one contract until it passes.

A second local report, `evaluation/reports/deepeval_results.json`, records an earlier principal-question execution. It is not silently merged into the latest table, and its complete configuration/reference fingerprint is not recorded by the generic runner. Preserve dataset, configuration, corpus versions, model identifiers and report hashes for controlled comparisons. Neither historical result is a broad accuracy benchmark.

## Latency and runtime-check experiments

The runtime already reuses loaded indexes and query embeddings and parallelises the initial per-index relevance calls. These are implemented optimizations; there is no controlled end-to-end speedup measurement recorded here.

- Compare `rag.relevance_workers: 1` with `5` for the same queries and deployment conditions.
- `rag.relevance_mode: retrieval` removes the five relevance-model calls but retains the document selector. Its current 0.0 threshold admits all nonempty indexes, so validate in-domain/out-of-domain behavior before adopting it.
- `rag.exceptions_enabled: false` skips exception work but can remove important qualifications from accounting answers.
- Evaluate candidate counts, chunking and selection-preview limits separately. The current offline runner does not evaluate the selector or exception branch, so retrieval scores alone cannot validate those changes.

The three DeepEval metrics use judges themselves. Moving them into each API request would add online work; keep them offline or design a separate sampled background workflow. Measure final-answer faithfulness, correctness, rejected-query behavior and exception completeness independently before removing semantic checks. Authentication, authorization and adversarial-input controls are different concerns.

For latency experiments, collect cold/warm `/api/ask` → terminal `/api/updatestatus` times on a representative dataset. Record retries, API rate limits, query length, selected context and exception-path usage. Do not present per-index retrieval timings as the full response latency.

## Validation and references

```bash
python3.11 -m pytest tests -q
```

Those tests validate dataset handling, actual DeepEval integration with a deterministic fixture judge, incomplete-score reporting and real temporary FAISS ranking. They do not generate empirical LLM quality scores.

- [DeepEval Contextual Recall](https://deepeval.com/docs/metrics-contextual-recall)
- [DeepEval Contextual Precision](https://deepeval.com/docs/metrics-contextual-precision)
- [DeepEval Contextual Relevancy](https://deepeval.com/docs/metrics-contextual-relevancy)
- [DeepEval custom LLM interface](https://deepeval.com/guides/guides-using-custom-llms)
- Accounting-reference provenance: [principal/agent](evaluation/ifrs15_principal_agent_dataset.md), [serviced office](evaluation/ifrs16_serviced_office_dataset.md)

## Latest recorded score table

Dataset: [`evaluation/ifrs16_serviced_office_eval.json`](evaluation/ifrs16_serviced_office_eval.json).

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
