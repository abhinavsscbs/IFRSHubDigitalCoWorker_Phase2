# Offline retrieval evaluation

See [EvalReadMe.md](../EvalReadMe.md) for the DeepEval workflow, dataset format, per-index results and latency assessment.

- Add expert-reviewed cases to `eval_dataset.json`.
- Install `requirements.txt` from this directory via `python -m pip install -r evaluation/requirements.txt` at the project root.
- Run `python evaluation/run_eval.py --inventory-only` to inspect missing prerequisites without API calls.
- Run `python evaluation/run_eval.py` to retrieve and score each configured/discovered FAISS index.

The historical `sample_eval_set.jsonl` is retained for reference. Lexical/source-count baseline scores are not DeepEval metrics and are no longer used by the runner.

The default dataset contains the supplied IFRS 15 principal question and answer. See the [principal-versus-agent dataset guide](ifrs15_principal_agent_dataset.md) for the optional 16-case regression set, source provenance and per-index interpretation.

The separate [serviced-office lease dataset](ifrs16_serviced_office_eval.json) preserves the full contract and original answer. See its [guide](ifrs16_serviced_office_dataset.md) and [recorded results](ifrs16_serviced_office_results.md) for the five-index IFRS 16 evaluation.
