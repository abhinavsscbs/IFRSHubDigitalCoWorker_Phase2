"""Offline DeepEval retrieval metrics for every configured/discovered FAISS index.

Inventory runs need neither a key nor DeepEval. Real runs never substitute
sample answers or source-count heuristics for the requested metrics.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from statistics import mean
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from rag_engine.config import (CONFIG, DB_PATHS, OPENAI_API_KEY, EMBEDDINGS_MODEL,
                               EMBEDDINGS_DIMENSIONS, STAGE_2_PERCENTILE, TRUST_LOCAL_INDEXES,
                               LLM_MODELS)

METRICS = ("contextual_recall", "contextual_precision", "contextual_relevancy")


def load_dataset(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise ValueError("Dataset must be an object with a cases array; see evaluation/eval_dataset.schema.json")
    seen = set()
    for number, row in enumerate(data["cases"], 1):
        if not isinstance(row, dict):
            raise ValueError(f"Case {number} must be an object")
        for key in ("id", "question", "expected_output"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"Case {number}: {key} must be a non-empty string")
        if row["id"] in seen:
            raise ValueError(f"Duplicate case id: {row['id']}")
        seen.add(row["id"])
        targets = row.get("indexes", [])
        if not isinstance(targets, list) or any(not isinstance(item, str) for item in targets):
            raise ValueError(f"Case {row['id']}: indexes must be an array of names")
        overrides = row.get("expected_outputs", {})
        if not isinstance(overrides, dict) or any(not isinstance(v, str) or not v.strip() for v in overrides.values()):
            raise ValueError(f"Case {row['id']}: expected_outputs must map index names to non-empty answers")
        if not isinstance(row.get("actual_output", ""), str):
            raise ValueError(f"Case {row['id']}: actual_output must be a string")
    return data["cases"]


def inventory(root: Path = ROOT, configured=None):
    indexes = [{"name": db["name"], "path": str(Path(db["path"]).resolve()), "configured": True}
               for db in (DB_PATHS if configured is None else configured)]
    paths = {item["path"] for item in indexes}
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in {".venv", "venv", ".git", "node_modules", "__pycache__", "dist"})
        if "index.faiss" in files:
            path = str(Path(current).resolve())
            if path not in paths:
                indexes.append({"name": f"discovered:{Path(current).relative_to(root).as_posix()}",
                                "path": path, "configured": False})
                paths.add(path)
    if len({db['name'] for db in indexes}) != len(indexes):
        raise ValueError("Each configured index must have a unique name")
    for db in indexes:
        path = Path(db["path"])
        db["missing_files"] = [name for name in ("index.faiss", "index.pkl") if not (path / name).is_file()]
        manifest = path / "embedding_manifest.json"
        db["embedding_compatible"] = False
        if manifest.is_file():
            try:
                info = json.loads(manifest.read_text(encoding="utf-8"))
                db["embedding_compatible"] = info.get("provider") == "openai" and info.get("model") == EMBEDDINGS_MODEL and info.get("dimensions") == EMBEDDINGS_DIMENSIONS
            except (ValueError, OSError):
                pass
    return indexes


def percentile95(values):
    return sorted(values)[max(0, math.ceil(len(values) * .95) - 1)] if values else None


async def measure_context(question, expected, context, actual, judge, threshold, semaphore):
    from deepeval.metrics import ContextualRecallMetric, ContextualPrecisionMetric, ContextualRelevancyMetric
    from deepeval.test_case import LLMTestCase
    test_case = LLMTestCase(input=question, actual_output=actual, expected_output=expected, retrieval_context=context)
    classes = (ContextualRecallMetric, ContextualPrecisionMetric, ContextualRelevancyMetric)

    async def measure(name, metric_class):
        async with semaphore:
            metric = metric_class(model=judge, threshold=threshold, include_reason=True, async_mode=True)
            start = time.perf_counter()
            try:
                await metric.a_measure(test_case)
                score = float(metric.score)
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("Judge returned an invalid score")
                return name, {"score": score, "passed": bool(metric.is_successful()), "reason": metric.reason,
                              "duration_sec": round(time.perf_counter() - start, 4)}
            except Exception as exc:
                return name, {"score": None, "passed": False, "error": str(exc),
                              "duration_sec": round(time.perf_counter() - start, 4)}
    return dict(await asyncio.gather(*(measure(name, cls) for name, cls in zip(METRICS, classes))))


async def evaluate(rows, indexes, inventory_only=False):
    settings = CONFIG.get("evaluation", {})
    task = settings.get("judge_task", "mini")
    threshold = float(settings.get("threshold", .7))
    if not 0 <= threshold <= 1:
        raise ValueError("evaluation.threshold must be between 0 and 1")
    known = {db["name"] for db in indexes}
    unknown = {name for row in rows for name in [*row.get("indexes", []), *row.get("expected_outputs", {})] if name not in known}
    if unknown:
        raise ValueError(f"Dataset targets unknown indexes: {', '.join(sorted(unknown))}")
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "inventory_only": inventory_only,
              "dataset_size": len(rows), "judge_model": LLM_MODELS[task], "threshold": threshold,
              "embedding_model": EMBEDDINGS_MODEL, "embedding_dimensions": EMBEDDINGS_DIMENSIONS,
              "retrieval_profile": {"max_k": 50, "top_percentile": STAGE_2_PERCENTILE,
                                    "stage": "per-index retrieval before the cross-index LLM document selector"},
              "indexes": []}
    semaphore = asyncio.Semaphore(max(1, int(settings.get("max_concurrent_metrics", 3))))
    judge = None
    for db in indexes:
        cases = [row for row in rows if not row.get("indexes") or db["name"] in row["indexes"]]
        result = {**db, "case_count": len(cases), "results": [], "summary": {name: None for name in METRICS}}
        blockers = []
        if inventory_only:
            blockers.append("Inventory only; metrics not requested")
        if db["missing_files"]:
            blockers.append("Missing " + ", ".join(db["missing_files"]))
        elif not db["embedding_compatible"]:
            blockers.append("Missing/incompatible embedding_manifest.json; rebuild with OpenAI embeddings")
        if not cases:
            blockers.append("No evaluation cases for this index")
        if not OPENAI_API_KEY:
            blockers.append("OPENAI_API_KEY is not configured")
        if not TRUST_LOCAL_INDEXES:
            blockers.append("rag.trust_local_indexes is false")
        if blockers:
            result.update(status="not_run", reasons=blockers)
            report["indexes"].append(result)
            continue
        try:
            if judge is None:
                from evaluation.judge import OpenAIJudge
                judge = OpenAIJudge(task=task)
            from rag_engine.retrieval import DBConfig, fetch_docs
            cfg = DBConfig(path=db["path"], name=db["name"])
            for row in cases:
                start = time.perf_counter()
                case = {"id": row["id"], "question": row["question"]}
                try:
                    documents = await asyncio.to_thread(fetch_docs, row["question"], cfg)
                    case["retrieval_duration_sec"] = round(time.perf_counter() - start, 4)
                    context = [doc.page_content for doc in documents]
                    case["retrieval_context"] = context
                    case["context_count"] = len(context)
                    expected = row.get("expected_outputs", {}).get(db["name"], row["expected_output"])
                    if not context:
                        # Judge libraries vary in how they handle empty context.
                        # Mark as retrieval failure rather than inventing judge scores.
                        raise ValueError("No context retrieved; metric scores unavailable")
                    case["metrics"] = await measure_context(row["question"], expected, context,
                                                             row.get("actual_output", ""), judge, threshold, semaphore)
                    case["status"] = "completed" if all(m["score"] is not None for m in case["metrics"].values()) else "error"
                except Exception as exc:
                    case.update(status="error", error=str(exc))
                case["total_duration_sec"] = round(time.perf_counter() - start, 4)
                result["results"].append(case)
            for metric in METRICS:
                scores = [case.get("metrics", {}).get(metric, {}).get("score") for case in result["results"]]
                valid = [value for value in scores if value is not None]
                result["summary"][metric] = {"mean": round(mean(valid), 4) if valid else None,
                    "scored_cases": len(valid), "total_cases": len(cases),
                    "pass_rate": round(mean(value >= threshold for value in valid), 4) if valid else None}
            times = [case["retrieval_duration_sec"] for case in result["results"] if "retrieval_duration_sec" in case]
            result["retrieval_latency_sec"] = {"mean": round(mean(times), 4) if times else None, "p95": percentile95(times)}
            result["status"] = "completed" if all(case["status"] == "completed" for case in result["results"]) else "error"
        except Exception as exc:
            result.update(status="error", reasons=[str(exc)])
        report["indexes"].append(result)
    report["complete"] = bool(indexes) and all(db["status"] == "completed" for db in report["indexes"])
    report["passed"] = report["complete"] and all(
        metric["passed"] for db in report["indexes"] for case in db["results"] for metric in case["metrics"].values())
    return report


def markdown_results(report):
    def score(db, name):
        metric = db["summary"][name]
        return f"{metric['mean']:.4f} ({metric['scored_cases']}/{metric['total_cases']})" if metric and metric['mean'] is not None else "Not measured"
    lines = ["<!-- EVAL_RESULTS_START -->", f"Last run (UTC): {report['generated_at']}", "",
             f"Dataset cases: {report['dataset_size']}. Judge: `{report['judge_model']}`. Threshold: {report['threshold']}.", "",
             "| FAISS index | Contextual Recall | Contextual Precision | Contextual Relevancy | Status |",
             "|---|---|---|---|---|"]
    for db in report["indexes"]:
        lines.append(f"| {db['name']} | {score(db, METRICS[0])} | {score(db, METRICS[1])} | {score(db, METRICS[2])} | {db['status']} |")
    lines.extend(["", "Scores are means on a 0–1 scale; parentheses show scored/targeted cases. Partial/error results are not a passing evaluation.", ""])
    for db in report["indexes"]:
        reasons = db.get("reasons", [])
        if reasons:
            lines.append(f"- **{db['name']}**: {'; '.join(reasons)}.")
    lines += ["", "<!-- EVAL_RESULTS_END -->"]
    return "\n".join(lines)


def write_reports(report, output: Path, readme: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    section = markdown_results(report)
    content = readme.read_text(encoding="utf-8") if readme.exists() else "# FAISS retrieval evaluation\n\n"
    start, end = "<!-- EVAL_RESULTS_START -->", "<!-- EVAL_RESULTS_END -->"
    if start in content and end in content:
        content = content[:content.index(start)] + section + content[content.index(end) + len(end):]
    else:
        content += section + "\n"
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / CONFIG.get("evaluation", {}).get("dataset", "evaluation/eval_dataset.json"))
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/reports/deepeval_results.json")
    parser.add_argument("--readme", type=Path, default=ROOT / "EvalReadMe.md")
    parser.add_argument("--inventory-only", action="store_true", help="List indexes/prerequisites without API calls")
    args = parser.parse_args()
    try:
        report = asyncio.run(evaluate(load_dataset(args.dataset), inventory(), args.inventory_only))
        write_reports(report, args.output, args.readme)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Evaluation setup error: {exc}\n")
    print(f"JSON report: {args.output}\nMetric results: {args.readme}")
    if args.inventory_only:
        return 0
    return 0 if report["passed"] else (1 if report["complete"] else 2)


if __name__ == "__main__":
    raise SystemExit(main())
