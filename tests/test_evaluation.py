import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock
import pytest
from pydantic import BaseModel
from evaluation import run_eval as runner


def test_dataset_rejects_missing_references_and_duplicate_ids(tmp_path):
    path = tmp_path / 'dataset.json'
    path.write_text(json.dumps({'cases': [{'id': 'q', 'question': 'Question'}]}))
    with pytest.raises(ValueError, match='expected_output'):
        runner.load_dataset(path)
    row = {'id': 'q', 'question': 'Q', 'expected_output': 'Expert answer'}
    path.write_text(json.dumps({'cases': [row, row]}))
    with pytest.raises(ValueError, match='Duplicate'):
        runner.load_dataset(path)


def test_inventory_discovers_additional_index_and_reports_incomplete(tmp_path):
    extra = tmp_path / 'extra'
    extra.mkdir()
    (extra / 'index.faiss').touch()
    indexes = runner.inventory(tmp_path, [{'name': 'IFRS A', 'path': str(tmp_path / 'missing')}])
    assert [item['name'] for item in indexes] == ['IFRS A', 'discovered:extra']
    assert indexes[1]['missing_files'] == ['index.pkl']


def test_missing_prerequisites_never_produce_zero_scores(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'OPENAI_API_KEY', '')
    report = asyncio.run(runner.evaluate([], runner.inventory(tmp_path, [{'name': 'Missing', 'path': str(tmp_path)}])))
    assert not report['complete'] and not report['passed']
    assert report['indexes'][0]['status'] == 'not_run'
    assert all(value is None for value in report['indexes'][0]['summary'].values())
    readme = tmp_path / 'EvalReadMe.md'
    readme.write_text('Instructions\n<!-- EVAL_RESULTS_START -->\nold\n<!-- EVAL_RESULTS_END -->\nKeep this too')
    runner.write_reports(report, tmp_path / 'report.json', readme)
    content = readme.read_text()
    assert content.startswith('Instructions') and content.endswith('Keep this too')
    assert 'Not measured' in content


def test_unknown_index_target_rejected():
    with pytest.raises(ValueError, match='unknown indexes'):
        asyncio.run(runner.evaluate([{'id': 'q', 'indexes': ['Typo']}], []))


def test_judge_routes_structured_sync_and_async_to_configured_model(monkeypatch):
    from evaluation import judge
    class Verdict(BaseModel):
        reason: str
    response = SimpleNamespace(status='completed', output_text='{"reason":"ok"}', output_parsed=Verdict(reason='ok'), incomplete_details=None, error=None)
    parse = Mock(return_value=response)
    async_parse = AsyncMock(return_value=response)
    monkeypatch.setattr(judge, 'get_openai_client', lambda: SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    monkeypatch.setattr(judge, 'get_async_openai_client', lambda: SimpleNamespace(responses=SimpleNamespace(parse=async_parse)))
    model = judge.OpenAIJudge('mini')
    assert model.generate('Evaluate', Verdict).reason == 'ok'
    assert asyncio.run(model.a_generate('Evaluate', Verdict)).reason == 'ok'
    assert parse.call_args.kwargs['model'] == 'gpt-6-luna'
    assert async_parse.call_args.kwargs['text_format'] is Verdict


def test_real_deepeval_metrics_with_deterministic_judge():
    # Exercise DeepEval's actual schemas/formulas without calling a live model.
    from deepeval.models import DeepEvalBaseLLM
    class FixtureJudge(DeepEvalBaseLLM):
        def load_model(self):
            return self
        def get_model_name(self):
            return 'deterministic-test-fixture'
        def generate(self, prompt, schema=None):
            fields = schema.model_fields
            if 'verdicts' in fields:
                annotation = fields['verdicts'].annotation
                verdict_class = annotation.__args__[0]
                verdict = {name: ('yes' if name == 'verdict' else 'Test statement supported by context')
                           for name in verdict_class.model_fields}
                return schema(verdicts=[verdict])
            if 'statements' in fields:
                return schema(statements=['A supported statement'])
            return schema(reason='Fixture context supports the reference')
        async def a_generate(self, prompt, schema=None):
            return self.generate(prompt, schema)
    scores = asyncio.run(runner.measure_context('Question', 'Expert answer', ['Supported source'], '',
                                               FixtureJudge(), .7, asyncio.Semaphore(3)))
    assert set(scores) == set(runner.METRICS)
    assert all(value['score'] == 1 and value['passed'] for value in scores.values()), scores


def test_per_index_results_keep_partial_judge_failures_visible(monkeypatch):
    from evaluation import judge
    from rag_engine import retrieval
    from langchain_core.documents import Document
    monkeypatch.setattr(runner, 'OPENAI_API_KEY', 'test-not-a-real-key')
    monkeypatch.setattr(runner, 'TRUST_LOCAL_INDEXES', True)
    monkeypatch.setattr(judge, 'OpenAIJudge', lambda **kwargs: object())
    monkeypatch.setattr(retrieval, 'fetch_docs', lambda question, cfg: [Document(page_content=f'{cfg.name} context')])
    async def metrics(question, expected, context, *args):
        assert expected == ('Corpus B expert answer' if context == ['B context'] else 'Shared expert answer')
        return {name: {'score': None if context == ['B context'] and name == 'contextual_precision' else .8,
                       'passed': context != ['B context'], 'reason': 'Fixture'} for name in runner.METRICS}
    monkeypatch.setattr(runner, 'measure_context', metrics)
    indexes = [{'name': name, 'path': '/test', 'missing_files': [], 'embedding_compatible': True} for name in ['A', 'B']]
    rows = [{'id': 'q', 'question': 'Question', 'expected_output': 'Shared expert answer',
             'expected_outputs': {'B': 'Corpus B expert answer'}}]
    report = asyncio.run(runner.evaluate(rows, indexes))
    assert report['indexes'][0]['status'] == 'completed'
    partial = report['indexes'][1]
    assert partial['status'] == 'error'
    assert partial['summary']['contextual_precision']['scored_cases'] == 0
    assert partial['summary']['contextual_precision']['mean'] is None
    assert not report['complete'] and not report['passed']
