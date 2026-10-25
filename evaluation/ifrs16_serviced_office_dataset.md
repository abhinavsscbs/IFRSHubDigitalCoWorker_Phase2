# Serviced office agreement: IFRS 16 evaluation

Dataset: [`ifrs16_serviced_office_eval.json`](ifrs16_serviced_office_eval.json).

The case preserves the full user-supplied contract and the matching original answer, including Markdown, from the completed local interaction `IFRS-20261022-C60500E7`. It does not paraphrase the contract or substitute a generated answer. Source text hashes are recorded in [`fixtures/ifrs16_serviced_office_provenance.json`](fixtures/ifrs16_serviced_office_provenance.json).

The supplied response is `actual_output`, and an independently drafted accounting reference is `expected_output`. The reference is a source-checked starter awaiting accounting expert approval, not a certified interpretation of Saudi contract law. It is deliberately concise, focusing on principles rather than expecting the vector store to reproduce contract-specific prices, locations and other facts already present in the query.

One full-contract case targets **IFRS A, IFRS B, IFRS C, EY and PwC** independently: five case/index pairs and fifteen metric results. Each corpus supplies its own ranked retrieval context. None of the earlier IFRS 15 dataset files are changed by this evaluation.

## What this tests

The reference covers lease identification, bundled services, component allocation and the lessee election, equipment components, lessor-only termination, conflicting contractual periods, commencement, advance payments, discounting and conditional lessor accounting. It does not require a fabricated discount rate, tax rate or completed numerical valuation.

Sources checked on 22 October 2026:

- [NZ IFRS 16, incorporating IFRS 16 and amendments through December 2023](https://standards.xrb.govt.nz/standards-navigator/nz-ifrs-16/): paragraphs 9, 12–17, 22–27, 61–62 and 81, and Appendix B9–B35. Only the IFRS-equivalent requirements are used, not local disclosure concessions. These support the lease, component, measurement and lessor principles in the reference.
- [IFRS Foundation, November 2019 agenda decision: Lease Term and Useful Life of Leasehold Improvements](https://www.ifrs.org/content/dam/ifrs/supporting-implementation/agenda-decisions/2019/ifrs-16-ias-16-lease-term-and-useful-life-of-leasehold-improvements.pdf): enforceability requires consideration of the contract's broader economics and both parties' termination rights. It does not determine the legal meaning of this agreement's conflicting clauses.

The inference that this specific contract needs clarification of its inconsistent notices is based on the supplied contract. It is not a legal determination that any particular notice provision overrides another. The record's extensive final answer is preserved for later answer evaluation; it is not used as ground truth.

## Reproduce

From the project root, with the virtual environment active:

```bash
python3.11 evaluation/run_eval.py \
  --dataset evaluation/ifrs16_serviced_office_eval.json \
  --output evaluation/reports/ifrs16_serviced_office_results.json \
  --readme evaluation/ifrs16_serviced_office_results.md
```

The command uses the configured judge task and threshold. It calls OpenAI for query embedding and DeepEval judgements. No new answer generation is needed. The result Markdown and JSON report are separate from the previous scenario; the root `EvalReadMe.md` also receives the recorded latest-run summary when this run is completed in this session.

## Interpretation limits

These are **retrieval metrics**: Contextual Recall measures evidence for the reference, Precision measures chunk ordering, and Relevancy measures how relevant retrieved material is to the full input. [DeepEval's recall documentation](https://deepeval.com/docs/metrics-contextual-recall) distinguishes the reference from the actual answer.

The stored `actual_output` does not itself turn these into answer-correctness or faithfulness scores. Corpus specialisation can also explain low scores, especially where an individual index lacks rules available elsewhere. One contract is a diagnostic example, not a representative benchmark. Reading the metric reasons and actual chunks is necessary before changing thresholds or removing runtime checks.

This run retrieves again using the current indexes. It does not claim to reconstruct the exact contexts used by the original bot response, which were not supplied as a complete ordered retrieval trace.
